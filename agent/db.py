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
