"""
Tool : search_feedback
Recherche sémantique via MongoDB Atlas Vector Search + filtre par catégorie/sentiment.
"""

import os
from google import genai
from google.genai import types

from db import get_mongo_client
from config import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS

_client = genai.Client()  # mode Vertex AI via GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION (voir .env)

# Nom de l'index Vector Search créé dans Atlas
VECTOR_INDEX_NAME = "feedback_vector_index"


async def search_feedback(
    query: str,
    project_id: str,
    limit: int = 10,
    category: str = None,
    min_sentiment: float = None,
    max_sentiment: float = None,
) -> dict:
    """
    Recherche des feedbacks par similarité sémantique.

    Args:
        query          : question ou mots-clés en langage naturel
        project_id     : identifiant du projet
        limit          : nombre de résultats max
        category       : filtrer par catégorie (optionnel)
        min_sentiment  : sentiment minimum (optionnel)
        max_sentiment  : sentiment maximum (optionnel)

    Returns:
        dict avec results (liste de feedbacks) et total
    """
    db = get_mongo_client()

    # ── Vectoriser la requête ────────────────────────────────────────────────
    embed_response = await _client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    query_vector = embed_response.embeddings[0].values

    # ── Construire le filtre MongoDB ─────────────────────────────────────────
    pre_filter = {"project_id": {"$eq": project_id}}
    if category:
        pre_filter["category"] = {"$eq": category}
    if min_sentiment is not None or max_sentiment is not None:
        pre_filter["sentiment"] = {}
        if min_sentiment is not None:
            pre_filter["sentiment"]["$gte"] = min_sentiment
        if max_sentiment is not None:
            pre_filter["sentiment"]["$lte"] = max_sentiment

    # ── Pipeline Atlas Vector Search ─────────────────────────────────────────
    pipeline = [
        {
            "$vectorSearch": {
                "index":          VECTOR_INDEX_NAME,
                "path":           "embedding",
                "queryVector":    query_vector,
                "numCandidates":  limit * 10,
                "limit":          limit,
                "filter":         pre_filter,
            }
        },
        {
            "$project": {
                "embedding": 0,   # ne pas retourner les vecteurs
                "score":     {"$meta": "vectorSearchScore"},
            }
        },
    ]

    results = list(db.feedbacks.aggregate(pipeline))

    # Sérialiser les ObjectIds
    for r in results:
        r["_id"] = str(r["_id"])

    return {
        "query":   query,
        "results": results,
        "total":   len(results),
    }
