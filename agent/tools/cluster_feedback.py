"""
Tool : cluster_feedback
Utilise MongoDB Atlas Vector Search pour regrouper les feedbacks par similarité sémantique.
"""

import os
import json
import numpy as np
from datetime import datetime, timezone

from google import genai
from google.genai import types

from db import get_mongo_client
from config import MODEL_NAME

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SIMILARITY_THRESHOLD = 0.82   # seuil de similarité cosine pour regrouper
MIN_CLUSTER_SIZE     = 2      # nb minimum de feedbacks pour former un cluster

LABEL_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
}


def _cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _centroid(vectors: list) -> list:
    arr = np.array(vectors)
    return (arr.mean(axis=0)).tolist()


async def cluster_feedback(project_id: str) -> dict:
    """
    Regroupe les feedbacks non-clusterisés d'un projet par similarité sémantique.

    Returns:
        dict avec nb de clusters créés/mis à jour
    """
    db = get_mongo_client()

    # Récupérer tous les feedbacks avec leur embedding
    feedbacks = list(
        db.feedbacks.find(
            {"project_id": project_id},
            {"_id": 1, "text": 1, "embedding": 1, "category": 1, "sentiment": 1},
        )
    )

    if len(feedbacks) < MIN_CLUSTER_SIZE:
        return {"clusters_updated": 0, "message": "Pas assez de feedbacks pour clusteriser."}

    # Algorithme de clustering simple (greedy nearest-centroid)
    clusters: list[dict] = []

    for fb in feedbacks:
        vec = fb.get("embedding")
        if not vec:
            continue

        best_cluster = None
        best_score   = 0.0

        for cluster in clusters:
            score = _cosine_similarity(vec, cluster["centroid"])
            if score > best_score and score >= SIMILARITY_THRESHOLD:
                best_score   = score
                best_cluster = cluster

        if best_cluster:
            best_cluster["members"].append(fb)
            # Recalculer le centroïde
            best_cluster["centroid"] = _centroid([m["embedding"] for m in best_cluster["members"] if m.get("embedding")])
        else:
            clusters.append({"centroid": vec, "members": [fb]})

    # Filtrer les clusters trop petits
    clusters = [c for c in clusters if len(c["members"]) >= MIN_CLUSTER_SIZE]

    # Générer les labels avec Gemini
    updated = 0
    for cluster in clusters:
        sample_texts = [m["text"] for m in cluster["members"][:5]]
        avg_sentiment = float(np.mean([m.get("sentiment", 0) for m in cluster["members"]]))

        label_prompt = f"""
Ces feedbacks parlent tous du même sujet. Génère un label court (3-6 mots max) en français
qui résume le thème commun, sans ponctuation finale.

Feedbacks :
{chr(10).join(f'- {t}' for t in sample_texts)}
"""
        label_response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=label_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LABEL_SCHEMA,
            ),
        )
        label = json.loads(label_response.text)["label"][:60]

        member_ids = [str(m["_id"]) for m in cluster["members"]]

        # Upsert du cluster dans MongoDB
        cluster_doc = {
            "project_id":     project_id,
            "label":          label,
            "feedback_count": len(cluster["members"]),
            "avg_sentiment":  round(avg_sentiment, 3),
            "centroid":       cluster["centroid"],
            "updated_at":     datetime.now(timezone.utc),
        }

        result = db.clusters.find_one_and_update(
            {"project_id": project_id, "label": label},
            {"$set": cluster_doc},
            upsert=True,
            return_document=True,
        )
        cluster_id = str(result["_id"])

        # Mettre à jour le cluster_id sur chaque feedback
        db.feedbacks.update_many(
            {"_id": {"$in": [m["_id"] for m in cluster["members"]]}},
            {"$set": {"cluster_id": cluster_id}},
        )
        updated += 1

    return {
        "clusters_updated": updated,
        "total_feedbacks_processed": len(feedbacks),
    }
