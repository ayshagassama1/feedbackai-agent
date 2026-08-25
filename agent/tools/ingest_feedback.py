"""
Tool : ingest_feedback
Étapes : nettoyage → scrub PII → triage par item (Gemma, fallback Gemini) → vectorisation →
stockage MongoDB
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timezone

import py3langid as langid
from google import genai
from google.genai import types

from db import get_mongo_client, DEFAULT_TEAM_LANGUAGE
from config import MODEL_NAME, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
from gemma_client import gemma_generate, GemmaUnavailableError

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
logger = logging.getLogger(__name__)

# Produit bilingue FR/EN (cf. team_language) : on restreint les langues candidates pour la
# détection plutôt que de couvrir l'ensemble des langues supportées par py3langid — mesuré le
# 2026-08-25, ça améliore nettement la précision sur du français court (ex. "Génial, merci !",
# détecté hongrois sans restriction). Accepté comme compromis : un feedback dans une langue
# tierce serait classé fr/en par erreur, jugé acceptable pour ce produit.
langid.set_languages(["fr", "en"])

CATEGORIES = ["bug", "feature_request", "ux", "pricing", "other"]
PRIORITIES  = ["high", "medium", "low"]

# Schéma du triage par item — même forme quel que soit le modèle (Gemma ou fallback Gemini),
# pour un comportement identique côté appelant. La langue n'y figure pas : elle est détectée
# séparément par py3langid (déterministe, sans appel modèle) plutôt que devinée par le LLM —
# mesuré le 2026-08-25 : gemma-3-1b-it détectait "fr" sur un feedback anglais.
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "category":  {"type": "string", "enum": CATEGORIES},
        "sentiment": {"type": "number"},
        "summary":   {"type": "string"},
    },
    "required": ["category", "sentiment", "summary"],
}

TRIAGE_PROMPT_TEMPLATE = """Analyse ce feedback utilisateur (en langue "{language}") et réponds UNIQUEMENT en JSON valide, sans markdown.
Format : {{"category": "...", "sentiment": 0.0, "summary": "..."}}

Catégories possibles : {categories}
Sentiment  : float entre -1.0 (très négatif) et +1.0 (très positif)
Summary    : résumé en 1 phrase max, en langue "{language}"

Feedback : "{text}"
"""

# ── Scrub PII (garde-fou, pas une anonymisation complète) ───────────────────
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\d[\s.-]?){8,14}\d")


def _scrub_pii(text: str) -> str:
    """Masque emails et numéros de téléphone avant tout usage (modèle ou stockage)."""
    text = _EMAIL_RE.sub("[email masqué]", text)
    text = _PHONE_RE.sub("[téléphone masqué]", text)
    return text


def _derive_priority(sentiment: float) -> str:
    """Dérive la priorité par règle à partir du sentiment — pas d'appel modèle."""
    if sentiment <= -0.5:
        return "high"
    if sentiment <= 0.0:
        return "medium"
    return "low"


def _clean(text: str) -> str:
    """Normalise le texte brut."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,!?;:()\-'\"àâäéèêëîïôùûüçæœ]", "", text, flags=re.UNICODE)
    return text


def _fingerprint(text: str) -> str:
    """Hash pour déduplication."""
    return hashlib.sha256(text.lower().encode()).hexdigest()[:16]


_MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_markdown_fence(raw: str) -> str:
    """Retire les balises ```json ... ``` que gemma-3-1b-it ajoute parfois malgré la consigne
    du prompt (mesuré le 2026-08-25 : le JSON renvoyé est correct, seulement enveloppé)."""
    return _MARKDOWN_FENCE_RE.sub("", raw.strip()).strip()


async def _triage(text: str) -> dict:
    """
    Triage par item (langue, catégorie, sentiment, résumé) — langue détectée par py3langid,
    reste (catégorie/sentiment/résumé) en un seul appel modèle. Essaie Gemma (Vertex, coût
    maîtrisé) en premier, bascule sur Gemini si l'endpoint Gemma n'est pas configuré, ne
    répond pas, ou renvoie un JSON invalide.
    """
    language, _ = langid.classify(text)
    prompt = TRIAGE_PROMPT_TEMPLATE.format(categories=", ".join(CATEGORIES), text=text, language=language)

    try:
        raw = await gemma_generate(prompt)
        parsed = json.loads(_strip_markdown_fence(raw))
        if parsed.get("category") not in CATEGORIES:
            raise ValueError(f"catégorie hors-schéma renvoyée par Gemma : {parsed.get('category')!r}")
        parsed["language"] = language
        parsed["_triage_model"] = "gemma"
        return parsed
    except (GemmaUnavailableError, json.JSONDecodeError, ValueError) as e:
        logger.info("Gemma indisponible ou réponse invalide (%s), fallback Gemini.", e)

    response = await _client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TRIAGE_SCHEMA,
        ),
    )
    parsed = json.loads(response.text)
    parsed["language"] = language
    parsed["_triage_model"] = "gemini_fallback"
    return parsed


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

    # ── 1. Nettoyage + scrub PII ──────────────────────────────────────────────
    text = _clean(content)
    text = _scrub_pii(text)
    if len(text) < 5:
        raise ValueError("Feedback trop court après nettoyage.")

    # ── 2. Déduplication ────────────────────────────────────────────────────
    fp = _fingerprint(text)
    existing = db.feedbacks.find_one({"project_id": project_id, "fingerprint": fp})
    if existing:
        return {"_id": str(existing["_id"]), "duplicate": True}

    # ── 3. Triage par item (langue + catégorie + sentiment + résumé) ─────────
    triage = await _triage(text)
    language  = triage["language"]
    category  = triage["category"] if triage["category"] in CATEGORIES else "other"
    sentiment = float(triage["sentiment"])
    summary   = triage["summary"]
    priority  = _derive_priority(sentiment)

    logger.info(
        "triage feedback project=%s modèle=%s language=%s category=%s sentiment=%.2f",
        project_id, triage.get("_triage_model"), language, category, sentiment,
    )

    # ── 4. Vectorisation (embeddings Gemini) ─────────────────────────────────
    embed_response = await _client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    vector = embed_response.embeddings[0].values  # liste de 768 floats

    # ── 5. Stockage MongoDB ──────────────────────────────────────────────────
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
    # NOTE : filtrer par {"project_id": project_id}, pas {"_id": project_id} — le _id Mongo
    # est un ObjectId auto-généré, jamais égal à la chaîne project_id (ex. "demo"). L'ancien
    # filtre par _id ne correspondait donc jamais à aucun document (bug silencieux découvert
    # à l'étape 4.2, en implémentant team_language qui a besoin d'un lookup fiable par projet).
    db.projects.update_one(
        {"project_id": project_id},
        {
            "$inc": {"feedback_count": 1},
            "$setOnInsert": {
                "project_id": project_id,
                "team_language": DEFAULT_TEAM_LANGUAGE,
                "created_at": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    return {
        "_id":      inserted_id,
        "category": category,
        "sentiment": sentiment,
        "priority": priority,
        "summary":  summary,
        "duplicate": False,
    }
