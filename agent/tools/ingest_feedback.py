"""
Tool : ingest_feedback
Étapes : nettoyage → classification Gemini → vectorisation → stockage MongoDB
"""

import os
import re
import hashlib
from datetime import datetime, timezone

from google import genai
from google.genai import types

from db import get_mongo_client
from config import MODEL_NAME, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

CATEGORIES = ["bug", "feature_request", "ux", "pricing", "other"]
PRIORITIES  = ["high", "medium", "low"]

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category":  {"type": "string", "enum": CATEGORIES},
        "sentiment": {"type": "number"},
        "priority":  {"type": "string", "enum": PRIORITIES},
        "summary":   {"type": "string"},
    },
    "required": ["category", "sentiment", "priority", "summary"],
}


def _clean(text: str) -> str:
    """Normalise le texte brut."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,!?;:()\-'\"àâäéèêëîïôùûüçæœ]", "", text, flags=re.UNICODE)
    return text


def _fingerprint(text: str) -> str:
    """Hash pour déduplication."""
    return hashlib.sha256(text.lower().encode()).hexdigest()[:16]


async def ingest_feedback(
    project_id: str,
    source: str,
    content: str,
) -> dict:
    """
    Ingère un feedback texte dans le pipeline complet.

    Args:
        project_id : identifiant du projet SaaS
        source     : "text" | "csv" | "url" | "manual"
        content    : texte brut du feedback

    Returns:
        dict avec _id, category, sentiment, priority
    """
    db = get_mongo_client()

    # ── 1. Nettoyage ────────────────────────────────────────────────────────
    text = _clean(content)
    if len(text) < 5:
        raise ValueError("Feedback trop court après nettoyage.")

    # ── 2. Déduplication ────────────────────────────────────────────────────
    fp = _fingerprint(text)
    existing = db.feedbacks.find_one({"project_id": project_id, "fingerprint": fp})
    if existing:
        return {"_id": str(existing["_id"]), "duplicate": True}

    # ── 3. Détection de la langue ───────────────────────────────────────────
    # Simplifié — en production, utiliser langdetect ou l'API Translate
    language = "fr" if any(c in text for c in "àâäéèêëîïôùûüçæœ") else "en"

    # ── 4. Classification Gemini (sortie JSON structurée et contrainte) ──────
    classification_prompt = f"""
Analyse ce feedback utilisateur.

Sentiment : float entre -1.0 (très négatif) et +1.0 (très positif)
Summary   : résumé en 1 phrase max (même langue que le feedback)

Feedback : "{text}"
"""

    response = _client.models.generate_content(
        model=MODEL_NAME,
        contents=classification_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CLASSIFICATION_SCHEMA,
        ),
    )

    import json
    parsed = json.loads(response.text)

    category  = parsed["category"]
    sentiment = float(parsed["sentiment"])
    priority  = parsed["priority"]
    summary   = parsed["summary"]

    # ── 5. Vectorisation (embeddings Gemini) ─────────────────────────────────
    embed_response = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    vector = embed_response.embeddings[0].values  # liste de 768 floats

    # ── 6. Stockage MongoDB ──────────────────────────────────────────────────
    doc = {
        "project_id":  project_id,
        "text":        text,
        "summary":     summary,
        "category":    category,
        "sentiment":   sentiment,
        "priority":    priority,
        "source":      source,
        "language":    language,
        "fingerprint": fp,
        "embedding":   vector,
        "cluster_id":  None,
        "created_at":  datetime.now(timezone.utc),
    }

    result = db.feedbacks.insert_one(doc)
    inserted_id = str(result.inserted_id)

    # Mise à jour des stats du projet
    db.projects.update_one(
        {"_id": project_id},
        {"$inc": {"feedback_count": 1}},
    )

    return {
        "_id":      inserted_id,
        "category": category,
        "sentiment": sentiment,
        "priority": priority,
        "summary":  summary,
        "duplicate": False,
    }
