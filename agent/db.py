"""
Connexion MongoDB Atlas.
"""

import os
from functools import lru_cache
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
DB_NAME     = os.environ.get("MONGODB_DB", "feedbackai")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI manquant - vérifie ton fichier .env")


@lru_cache(maxsize=1)
def get_mongo_client():
    """Retourne la base de données MongoDB (singleton)."""
    client = MongoClient(MONGODB_URI, server_api=ServerApi("1"))
    return client[DB_NAME]


DEFAULT_TEAM_LANGUAGE = "fr"


def get_team_language(project_id: str) -> str:
    """
    Langue des artefacts destinés à l'équipe (labels, insights, tickets, notifications)
    pour un projet — 'fr' ou 'en'. 'fr' par défaut si le projet n'a jamais été configuré.
    """
    db = get_mongo_client()
    proj = db.projects.find_one({"project_id": project_id}, {"team_language": 1})
    return (proj or {}).get("team_language", DEFAULT_TEAM_LANGUAGE)
