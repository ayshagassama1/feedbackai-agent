"""
Tool : create_ticket
Crée un ticket GitHub Issues à partir d'un cluster de feedback prioritaire. Idempotent :
un cluster déjà ticketé (issue_url en base) ne génère jamais de doublon.
"""

import os
import json
import httpx
from bson import ObjectId

from google import genai
from google.genai import types

from db import get_mongo_client
from config import MODEL_NAME, TICKET_MIN_FEEDBACK_COUNT, TICKET_SENTIMENT_THRESHOLD
from tools.notify import notify

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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

Feedbacks représentatifs :
{samples}

Rédige un ticket structuré en markdown avec ces sections : Contexte, Feedbacks représentatifs
(citer 2-3 extraits), Impact, Proposition d'action. Le titre doit être court et actionnable
(pas de préfixe type "Bug:" ou "[FR]").
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

    samples = list(
        db.feedbacks.find({"project_id": project_id, "cluster_id": cluster_id}, {"text": 1}).limit(5)
    )
    samples_text = "\n".join(f"- {s['text']}" for s in samples) or "(aucun extrait disponible)"

    prompt = TICKET_PROMPT_TEMPLATE.format(
        label=cluster["label"],
        feedback_count=cluster["feedback_count"],
        avg_sentiment=cluster.get("avg_sentiment", 0.0),
        samples=samples_text,
    )

    response = await _client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TICKET_SCHEMA,
        ),
    )
    ticket = json.loads(response.text)

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

    await notify(
        project_id=project_id,
        message_fr=(
            f"Nouveau ticket créé pour le cluster « {cluster['label']} » "
            f"({feedback_count} feedbacks, sentiment moyen {avg_sentiment:.2f}) : {issue_url}"
        ),
        message_en=(
            f'New ticket created for cluster "{cluster["label"]}" '
            f"({feedback_count} feedbacks, avg sentiment {avg_sentiment:.2f}): {issue_url}"
        ),
    )

    return {"issue_url": issue_url, "issue_number": issue_number, "created": True}
