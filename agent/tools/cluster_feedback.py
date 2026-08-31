"""
Tool : cluster_feedback
Utilise MongoDB Atlas Vector Search pour regrouper les feedbacks par similarité sémantique.
"""

import os
import json
import logging
import numpy as np
from collections import Counter
from datetime import datetime, timezone

from bson import ObjectId
from google import genai
from google.genai import types

from db import get_mongo_client, get_team_language
from config import MODEL_NAME

_client = genai.Client()  # mode Vertex AI via GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION (voir .env)
logger = logging.getLogger(__name__)

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
            {"_id": 1, "text": 1, "embedding": 1, "category": 1, "sentiment": 1, "cluster_id": 1},
        )
    )

    if len(feedbacks) < MIN_CLUSTER_SIZE:
        return {"clusters_updated": 0, "message": "Pas assez de feedbacks pour clusteriser."}

    team_language = get_team_language(project_id)
    language_name = "français" if team_language == "fr" else "English"

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
    claimed_cluster_ids: set[str] = set()
    for cluster in clusters:
        sample_texts = [m["text"] for m in cluster["members"][:5]]
        avg_sentiment = float(np.mean([m.get("sentiment", 0) for m in cluster["members"]]))

        label_prompt = f"""
Ces feedbacks parlent tous du même sujet. Génère un label court (3-6 mots max) en {language_name}
qui résume le thème commun, sans ponctuation finale. Les feedbacks eux-mêmes peuvent être dans
n'importe quelle langue — le label doit être en {language_name} quoi qu'il arrive.

Feedbacks :
{chr(10).join(f'- {t}' for t in sample_texts)}
"""
        try:
            label_response = await _client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=label_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LABEL_SCHEMA,
                ),
            )
            label = json.loads(label_response.text)["label"][:60]
        except Exception as e:
            # Gemini indisponible/rate-limité (429 fréquent sur le palier gratuit, 5 req/min) :
            # un label de repli déterministe, plutôt que de faire planter tout le cycle — le
            # comptage, le seuil et la création de ticket ne dépendent pas du label lui-même.
            # Mesuré le 2026-08-28 : sans ce filet, un simple 429 sur l'étiquetage suffisait à
            # faire échouer /api/agent/run-cycle en 500, que Pub/Sub relançait alors en boucle.
            categories = [m.get("category") for m in cluster["members"] if m.get("category")]
            top_category = Counter(categories).most_common(1)
            label = top_category[0][0].replace("_", " ").capitalize() if top_category else "Feedback cluster"
            logger.warning("Étiquetage Gemini indisponible (%s), label de repli %r utilisé.", e, label)

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

        # Identité du cluster : PAS le label (régénéré par Gemini à chaque appel, donc jamais
        # garanti identique d'un run à l'autre pour le même groupe de feedbacks — un upsert par
        # label créait un nouveau document de cluster à chaque cycle, et cassait l'idempotence
        # de create_ticket qui vérifie "issue_url" sur ce document). À la place, on réutilise le
        # cluster déjà associé à ces feedbacks si la majorité des membres le partagent déjà.
        # Un cluster précédent peut avoir été scindé par cette passe (le clustering glouton est
        # sensible à l'ordre de traitement) : plusieurs nouveaux groupes calculés ici peuvent
        # alors partager la même majorité de cluster_id d'origine. Sans garde-fou, chacun
        # réutiliserait le même document Mongo, le dernier du lot écrasant les stats
        # (feedback_count, avg_sentiment) des groupes précédents sans jamais détacher leurs
        # membres — le document affiche alors un compte inférieur au nombre réel de feedbacks
        # qui portent encore son cluster_id. Mesuré le 2026-08-30 : un cluster à 5 membres réels
        # affichait feedback_count=2. `claimed_cluster_ids` empêche un même _id d'être réutilisé
        # deux fois dans la même passe ; le groupe suivant crée son propre document à la place.
        existing_cluster_ids = [
            m["cluster_id"] for m in cluster["members"] if m.get("cluster_id")
        ]
        reuse_id = None
        if existing_cluster_ids:
            candidate, count = Counter(existing_cluster_ids).most_common(1)[0]
            if count >= len(cluster["members"]) / 2 and candidate not in claimed_cluster_ids:
                reuse_id = candidate

        if reuse_id:
            claimed_cluster_ids.add(reuse_id)
            result = db.clusters.find_one_and_update(
                {"_id": ObjectId(reuse_id), "project_id": project_id},
                {"$set": cluster_doc},
                return_document=True,
            )
        else:
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
