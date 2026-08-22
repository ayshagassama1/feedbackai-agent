"""
Tool : generate_insights
Génère un rapport actionnable à partir des clusters et feedbacks d'un projet.
"""

import os
import json
from datetime import datetime, timezone, timedelta

from google import genai
from google.genai import types

from db import get_mongo_client, get_team_language
from config import MODEL_NAME

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

RECOMMENDATIONS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "reason": {"type": "string"},
            "impact": {"type": "string", "enum": ["élevé", "moyen", "faible"]},
        },
        "required": ["action", "reason", "impact"],
    },
}


async def generate_insights(project_id: str) -> dict:
    """
    Analyse les feedbacks et clusters pour générer un rapport actionnable.

    Returns:
        dict avec stats, top_issues, recommendations, generated_at
    """
    db = get_mongo_client()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    team_language = get_team_language(project_id)
    language_name = "français" if team_language == "fr" else "English"

    # ── Stats de base ────────────────────────────────────────────────────────
    total       = db.feedbacks.count_documents({"project_id": project_id})
    this_week   = db.feedbacks.count_documents({"project_id": project_id, "created_at": {"$gte": week_ago}})
    cluster_count = db.clusters.count_documents({"project_id": project_id})

    # Sentiment moyen
    pipeline = [
        {"$match": {"project_id": project_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$sentiment"}}},
    ]
    sent_result = list(db.feedbacks.aggregate(pipeline))
    avg_sentiment = round(sent_result[0]["avg"], 3) if sent_result else 0.0

    # ── Top issues (par catégorie + volume) ─────────────────────────────────
    category_pipeline = [
        {"$match": {"project_id": project_id}},
        {"$group": {
            "_id":           "$category",
            "count":         {"$sum": 1},
            "avg_sentiment": {"$avg": "$sentiment"},
            "samples":       {"$push": "$text"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 5},
    ]
    categories = list(db.feedbacks.aggregate(category_pipeline))

    top_issues = []
    for cat in categories:
        samples = cat["samples"][:3]
        priority = "high" if cat["avg_sentiment"] < -0.3 or cat["count"] > 10 else \
                   "medium" if cat["count"] > 3 else "low"

        top_issues.append({
            "category":    cat["_id"],
            "count":       cat["count"],
            "priority":    priority,
            "label":       _category_label(cat["_id"], team_language),
            "sample":      samples[0] if samples else "",
            "avg_sentiment": round(cat["avg_sentiment"], 2),
        })

    # ── Recommandations Gemini ───────────────────────────────────────────────
    clusters = list(
        db.clusters.find({"project_id": project_id})
        .sort("feedback_count", -1)
        .limit(5)
    )

    clusters_summary = "\n".join(
        f"- {c['label']} ({c['feedback_count']} feedbacks, sentiment: {c['avg_sentiment']:.2f})"
        for c in clusters
    )

    rec_prompt = f"""
Tu es un Product Manager expert. Voici les données de feedback d'un produit SaaS.

Stats :
- {total} feedbacks au total, {this_week} cette semaine
- Sentiment moyen : {avg_sentiment}

Clusters principaux :
{clusters_summary}

Top catégories :
{chr(10).join(f"- {i['category']}: {i['count']} feedbacks" for i in top_issues)}

Génère exactement 3 recommandations actionnables pour cette semaine, rédigées en {language_name}
(quelle que soit la langue des feedbacks d'origine).
"""

    rec_response = await _client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=rec_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RECOMMENDATIONS_SCHEMA,
        ),
    )
    recommendations = json.loads(rec_response.text)

    # ── Sauvegarder l'insight ────────────────────────────────────────────────
    insight_doc = {
        "project_id": project_id,
        "type":       "weekly",
        "stats": {
            "total":         total,
            "this_week":     this_week,
            "avg_sentiment": avg_sentiment,
            "clusters":      cluster_count,
        },
        "top_issues":      top_issues,
        "recommendations": recommendations,
        "generated_at":    now,
    }

    db.insights.insert_one(insight_doc)
    insight_doc["_id"] = str(insight_doc["_id"])
    insight_doc["generated_at"] = now.isoformat()

    return insight_doc


def _category_label(category: str, team_language: str) -> str:
    labels = {
        "fr": {
            "bug":             "Bugs signalés",
            "feature_request": "Fonctionnalités demandées",
            "ux":              "Problèmes d'expérience utilisateur",
            "pricing":         "Retours sur les prix",
            "other":           "Autres retours",
        },
        "en": {
            "bug":             "Reported bugs",
            "feature_request": "Requested features",
            "ux":              "User experience issues",
            "pricing":         "Pricing feedback",
            "other":           "Other feedback",
        },
    }
    return labels.get(team_language, labels["fr"]).get(category, category)
