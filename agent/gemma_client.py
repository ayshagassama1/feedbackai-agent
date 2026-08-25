"""
Client Gemma — appelle un endpoint Vertex AI (Model Garden, conteneur vLLM) déployé en point
de terminaison dédié. Aucun SDK ni endpoint OpenAI : appel HTTP direct authentifié par les
Application Default Credentials, sur l'API Vertex native.

Variables d'env : GEMMA_ENDPOINT_ID, GEMMA_LOCATION, GCP_PROJECT_ID (jamais en dur).
Aucune n'est requise au démarrage de l'app : si elles manquent ou que l'endpoint ne répond
pas, gemma_generate lève GemmaUnavailableError et l'appelant bascule sur le fallback Gemini
(PHASE 1.4, obligatoire — l'app doit tourner sans l'endpoint Gemma déployé).

Historique des essais (étape 1.4, mesuré le 2026-08-25, contre un déploiement réel
"vLLM 32K context" gemma-3-1b-it / NVIDIA_L4) :
1. PredictionServiceAsyncClient (gRPC, domaine régional partagé) → 400 : les points de
   terminaison dédiés (dedicatedEndpointEnabled, activé par défaut sur les déploiements
   Model Garden "one-click") exigent leur propre domaine *.prediction.vertexai.goog.
2. Même client sur le domaine dédié → 404/UNIMPLEMENTED : ce domaine n'accepte pas le gRPC.
3. transport="rest_asyncio" → erreur de type d'identifiants (google.auth.aio.credentials
   requis, incompatible avec les Application Default Credentials standard — rugosité connue
   de cette partie encore jeune du SDK).
4. transport="rest" (client synchrone) → 400 : le transport REST généré du SDK ajoute ses
   propres paramètres de requête (ex. $alt=json;enum-encoding=int) que la passerelle du point
   de terminaison dédié ne reconnaît pas.
5. Appel HTTP direct (ci-dessous) → fonctionne, en reproduisant exactement l'exemple de
   requête généré par la console elle-même (curl + jeton d'accès + JSON brut).

Format d'instance : ce conteneur n'accepte que le format Vertex "@requestFormat":
"chatCompletions" (messages role/content) — c'est le format imposé par Google pour ce type de
conteneur vLLM, pas un choix arbitraire. Décidé avec Aissatou le 2026-08-25 après mesure
(aucun format alternatif documenté pour ce conteneur).

Format de réponse : avec ce requestFormat, "predictions" n'est pas une liste d'instances comme
sur l'API Vertex classique, mais directement l'objet chat.completion
({"choices": [{"message": {"content": ...}}], "usage": {...}, ...}) — également mesuré le
2026-08-25 sur la réponse réelle (KeyError sur predictions[0] avant correction).
"""

import os
import asyncio

import httpx
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud.aiplatform.gapic import EndpointServiceAsyncClient

_credentials = None
_dedicated_dns_cache: dict[str, str] = {}


class GemmaUnavailableError(Exception):
    """Endpoint Gemma non configuré ou injoignable — à charge de l'appelant de basculer sur Gemini."""


def _get_access_token() -> str:
    """Jeton d'accès via les Application Default Credentials (appel bloquant, à exécuter
    dans un thread depuis le code async — voir asyncio.to_thread ci-dessous)."""
    global _credentials
    if _credentials is None:
        _credentials, _ = google_auth_default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if not _credentials.valid:
        _credentials.refresh(GoogleAuthRequest())
    return _credentials.token


async def _resolve_api_endpoint(endpoint_resource: str, location: str) -> str:
    """
    Résout le domaine à utiliser pour appeler cet endpoint : le domaine dédié
    (dedicatedEndpointDns) si le déploiement l'a activé, sinon le domaine régional partagé.
    Mis en cache par ressource d'endpoint.
    """
    if endpoint_resource in _dedicated_dns_cache:
        return _dedicated_dns_cache[endpoint_resource]

    shared_domain = f"{location}-aiplatform.googleapis.com"
    try:
        admin_client = EndpointServiceAsyncClient(
            client_options={"api_endpoint": shared_domain}
        )
        endpoint = await admin_client.get_endpoint(name=endpoint_resource, timeout=10.0)
        resolved = endpoint.dedicated_endpoint_dns or shared_domain
    except Exception:
        # Résolution impossible : on retente avec le domaine partagé, l'appel predict()
        # suivant échouera proprement (GemmaUnavailableError) s'il faut vraiment le domaine dédié.
        resolved = shared_domain

    _dedicated_dns_cache[endpoint_resource] = resolved
    return resolved


async def gemma_generate(prompt: str, max_tokens: int = 256, timeout: float = 10.0) -> str:
    """
    Génère du texte via l'endpoint Gemma déployé sur Vertex AI.

    Lève GemmaUnavailableError si GEMMA_ENDPOINT_ID/GCP_PROJECT_ID manquent, si l'endpoint ne
    répond pas dans le délai imparti, ou si la réponse n'a pas la forme attendue.
    """
    endpoint_id = os.environ.get("GEMMA_ENDPOINT_ID", "")
    location    = os.environ.get("GEMMA_LOCATION", "us-central1")
    project_id  = os.environ.get("GCP_PROJECT_ID", "")

    if not endpoint_id or not project_id:
        raise GemmaUnavailableError("GEMMA_ENDPOINT_ID ou GCP_PROJECT_ID manquant.")

    endpoint_resource = f"projects/{project_id}/locations/{location}/endpoints/{endpoint_id}"

    payload = {
        "instances": [
            {
                "@requestFormat": "chatCompletions",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
        ]
    }

    try:
        api_endpoint = await _resolve_api_endpoint(endpoint_resource, location)
        token = await asyncio.to_thread(_get_access_token)

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://{api_endpoint}/v1/{endpoint_resource}:predict",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise GemmaUnavailableError(f"Endpoint Gemma injoignable : {e}") from e

    # Avec "@requestFormat": "chatCompletions", "predictions" n'est pas une liste d'instances
    # mais directement l'objet chat.completion ({"choices": [...], "usage": {...}, ...}) —
    # mesuré le 2026-08-25 sur la réponse réelle de ce conteneur.
    prediction = data.get("predictions")
    if not prediction:
        raise GemmaUnavailableError("Réponse Gemma vide.")
    if isinstance(prediction, list):
        prediction = prediction[0] if prediction else {}

    text = None
    choices = prediction.get("choices")
    if choices:
        text = (choices[0].get("message") or {}).get("content")
    text = text or prediction.get("text") or prediction.get("generated_text") or prediction.get("content")

    if not text:
        raise GemmaUnavailableError(f"Format de réponse Gemma inattendu : {prediction}")
    return text.strip()
