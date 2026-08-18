"""
Client Gemma — appelle un endpoint Vertex AI (Model Garden, conteneur vLLM) via
PredictionServiceAsyncClient. Pas de format OpenAI : instances au format natif Vertex/vLLM.

Variables d'env : GEMMA_ENDPOINT_ID, GEMMA_LOCATION, GCP_PROJECT_ID (jamais en dur).
Aucune n'est requise au démarrage de l'app : si elles manquent ou que l'endpoint ne répond
pas, gemma_generate lève GemmaUnavailableError et l'appelant bascule sur le fallback Gemini
(PHASE 1.4, obligatoire — l'app doit tourner sans l'endpoint Gemma déployé).

NOTE : le format exact des instances/réponses dépend du conteneur de service choisi au
déploiement (Model Garden vLLM). Le format ci-dessous (prompt/max_tokens en entrée,
predictions[0].text en sortie) est celui des déploiements vLLM standards sur Vertex — à
vérifier/ajuster une fois l'endpoint réel déployé (voir README, section Gemma).
"""

import os

from google.cloud.aiplatform.gapic import PredictionServiceAsyncClient
from google.cloud.aiplatform_v1.types import PredictRequest
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value

_client: PredictionServiceAsyncClient | None = None


class GemmaUnavailableError(Exception):
    """Endpoint Gemma non configuré ou injoignable — à charge de l'appelant de basculer sur Gemini."""


def _get_client(location: str) -> PredictionServiceAsyncClient:
    global _client
    if _client is None:
        _client = PredictionServiceAsyncClient(
            client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        )
    return _client


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

    endpoint = f"projects/{project_id}/locations/{location}/endpoints/{endpoint_id}"

    instance = json_format.ParseDict({"prompt": prompt, "max_tokens": max_tokens}, Value())
    request = PredictRequest(endpoint=endpoint)
    request.instances.append(instance)

    try:
        response = await _get_client(location).predict(request=request, timeout=timeout)
    except Exception as e:
        raise GemmaUnavailableError(f"Endpoint Gemma injoignable : {e}") from e

    if not response.predictions:
        raise GemmaUnavailableError("Réponse Gemma vide.")

    prediction = json_format.MessageToDict(response.predictions[0])
    text = prediction.get("text") or prediction.get("generated_text") or prediction.get("content")
    if not text:
        raise GemmaUnavailableError(f"Format de réponse Gemma inattendu : {prediction}")
    return text
