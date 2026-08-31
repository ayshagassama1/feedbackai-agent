"""
Tool : create_ticket
Crée un ticket GitHub Issues à partir d'un cluster de feedback prioritaire. Idempotent :
un cluster déjà ticketé (issue_url en base) ne génère jamais de doublon.
"""

import os
import json
import logging
import httpx
from bson import ObjectId

from google import genai
from google.genai import types

from db import get_mongo_client, get_team_language
from config import MODEL_NAME, TICKET_MIN_FEEDBACK_COUNT, TICKET_SENTIMENT_THRESHOLD
from tools.notify import notify

_client = genai.Client()  # mode Vertex AI via GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION (voir .env)
logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"

TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body":  {"type": "string"},
    },
    "required": ["title", "body"],
}

TICKET_PROMPT_TEMPLATE = """Tu es un Product Manager qui rédige un ticket GitHub pour l'équipe engineering.

Cluster de feedback : "{label}"
Nombre de feedbacks : {feedback_count}
Sentiment moyen : {avg_sentiment:.2f} (entre -1 très négatif et +1 très positif)

Feedbacks représentatifs (dans leur langue d'origine) :
{samples}

Rédige un ticket structuré en markdown, entièrement en {language_name} (titre, sections,
narration), avec ces sections : Contexte, Feedbacks représentatifs, Impact, Proposition d'action.
Dans la section Feedbacks représentatifs, cite 2-3 extraits **mot pour mot, dans leur langue
d'origine, sans les traduire** — seule la narration autour (Contexte, Impact, Proposition) est
en {language_name}. Le titre doit être court et actionnable (pas de préfixe type "Bug:" ou "[FR]").
"""


def _repo_for_project(project_id: str) -> str:
    """Résout le repo GitHub cible ('owner/repo') pour un project_id, via GITHUB_REPO_MAP."""
    repo_map = json.loads(os.environ.get("GITHUB_REPO_MAP", "{}"))
    repo = repo_map.get(project_id)
    if not repo:
        raise ValueError(
            f"Aucun repo GitHub configuré pour project_id={project_id!r} "
            f"(variable GITHUB_REPO_MAP)."
        )
    return repo


async def create_ticket(project_id: str, cluster_id: str) -> dict:
    """
    Crée un ticket GitHub Issues pour un cluster de feedback prioritaire.

    Args:
        project_id : identifiant du projet SaaS
        cluster_id : identifiant du cluster (db.clusters._id, forme string)

    Returns:
        dict avec issue_url, issue_number, created (False si le cluster était déjà ticketé ou
        si le seuil de déclenchement n'est pas atteint — voir `skipped`/`reason`)
    """
    db = get_mongo_client()
    cluster = db.clusters.find_one({"_id": ObjectId(cluster_id), "project_id": project_id})
    if not cluster:
        raise ValueError(f"Cluster introuvable : project_id={project_id!r}, cluster_id={cluster_id!r}")

    # ── Idempotence : ne pas recréer un ticket pour un cluster déjà ticketé ──────
    if cluster.get("issue_url"):
        return {
            "issue_url": cluster["issue_url"],
            "issue_number": cluster["issue_number"],
            "created": False,
        }

    # ── Seuil de déclenchement : évite le bruit (étape 2.2) ──────────────────────
    feedback_count = cluster["feedback_count"]
    avg_sentiment  = cluster.get("avg_sentiment", 0.0)
    if feedback_count < TICKET_MIN_FEEDBACK_COUNT or avg_sentiment > TICKET_SENTIMENT_THRESHOLD:
        return {
            "created": False,
            "skipped": True,
            "reason": (
                f"seuil non atteint (feedback_count={feedback_count} < {TICKET_MIN_FEEDBACK_COUNT} "
                f"ou avg_sentiment={avg_sentiment:.2f} > {TICKET_SENTIMENT_THRESHOLD})"
            ),
        }

    # ── Claim atomique ────────────────────────────────────────────────────────
    # La vérification "issue_url" ci-dessus (lecture) et l'écriture finale d'issue_url sont
    # deux opérations séparées : entre les deux, un second appel concurrent sur le même
    # cluster (Pub/Sub redélivre le message si le premier traitement dépasse le délai
    # d'accusé de réception de la subscription, plus probable depuis que le cycle enchaîne
    # plusieurs appels Vertex/Gemini) voit lui aussi "issue_url" vide et part créer son propre
    # ticket. Mesuré le 2026-08-30 : deux tickets créés à 11 secondes d'intervalle pour le même
    # cluster. Cette écriture conditionnelle réserve le cluster de façon atomique : un seul
    # appel concurrent peut réussir ce find_one_and_update, les autres voient le filtre échouer
    # et s'arrêtent avant même d'appeler Gemini ou GitHub.
    claimed = db.clusters.find_one_and_update(
        {"_id": cluster["_id"], "issue_url": {"$exists": False}},
        {"$set": {"issue_url": "pending"}},
    )
    if claimed is None:
        return {
            "created": False,
            "skipped": True,
            "reason": "création déjà en cours pour ce cluster (appel concurrent détecté)",
        }

    try:
        samples = list(
            db.feedbacks.find({"project_id": project_id, "cluster_id": cluster_id}, {"text": 1}).limit(5)
        )
        samples_text = "\n".join(f"- {s['text']}" for s in samples) or "(aucun extrait disponible)"

        team_language = get_team_language(project_id)
        language_name = "français" if team_language == "fr" else "English"

        prompt = TICKET_PROMPT_TEMPLATE.format(
            label=cluster["label"],
            feedback_count=cluster["feedback_count"],
            avg_sentiment=cluster.get("avg_sentiment", 0.0),
            samples=samples_text,
            language_name=language_name,
        )

        try:
            response = await _client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TICKET_SCHEMA,
                ),
            )
            ticket = json.loads(response.text)
            # Filet mesuré le 2026-08-28 : Gemini double-échappe parfois le corps sous
            # response_schema (le JSON contient le texte littéral "\n" au lieu d'un vrai saut de
            # ligne) — intermittent, pas systématique (3 tickets précédents corrects, celui-ci non).
            # Sans ce nettoyage, le ticket GitHub affiche des "\n" visibles au lieu d'un markdown
            # correctement formaté.
            ticket["body"] = ticket["body"].replace("\\n", "\n")
        except Exception as e:
            # Gemini indisponible/rate-limité : reporter la création du ticket au prochain cycle
            # plutôt que de planter tout /api/agent/run-cycle (qui bloquerait aussi les autres
            # clusters de la même boucle). Le claim est levé dans le except englobant ci-dessous
            # (même chemin que tout autre échec après le claim), donc create_ticket retentera au
            # cycle suivant plutôt que de rester bloqué sur "pending". Mesuré le 2026-08-28.
            raise RuntimeError(f"Gemini indisponible : {e}") from e

        repo = _repo_for_project(project_id)
        token = os.environ["GITHUB_TOKEN"]

        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{GITHUB_API_URL}/repos/{repo}/issues",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"title": ticket["title"], "body": ticket["body"]},
                timeout=15.0,
            )
            resp.raise_for_status()
            issue = resp.json()

        issue_url = issue["html_url"]
        issue_number = issue["number"]

        db.clusters.update_one(
            {"_id": cluster["_id"]},
            {"$set": {"issue_url": issue_url, "issue_number": issue_number}},
        )

        if team_language == "en":
            message = (
                f'New ticket created for cluster "{cluster["label"]}" '
                f"({feedback_count} feedbacks, avg sentiment {avg_sentiment:.2f}): {issue_url}"
            )
        else:
            message = (
                f"Nouveau ticket créé pour le cluster « {cluster['label']} » "
                f"({feedback_count} feedbacks, sentiment moyen {avg_sentiment:.2f}) : {issue_url}"
            )

        await notify(project_id=project_id, message=message, language=team_language)

        return {"issue_url": issue_url, "issue_number": issue_number, "created": True}

    except Exception as e:
        # Tout échec après le claim (Gemini, GitHub, réseau) doit lever la réservation
        # "pending", sinon ce cluster resterait bloqué indéfiniment : la vérification
        # d'idempotence au tout début de cette fonction le verrait comme "déjà ticketé" pour
        # toujours, sans jamais avoir réellement créé de ticket.
        db.clusters.update_one({"_id": cluster["_id"]}, {"$unset": {"issue_url": ""}})
        logger.warning("Création du ticket reportée pour ce cluster (%s).", e)
        return {"created": False, "skipped": True, "reason": str(e)}
