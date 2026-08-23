import os
import sys
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
 
load_dotenv()  
 
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME     = os.environ.get("MONGODB_DB", "feedbackai")


def get_db():
    client = MongoClient(MONGODB_URI, server_api=ServerApi("1"))
    client.admin.command("ping")
    print(f"Connecté à MongoDB ({MONGODB_URI[:40]}…)")
    return client[DB_NAME]


# ── Validators JSON Schema ───────────────────────────────────────────────────

USERS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["email", "name", "plan", "created_at"],
        "properties": {
            "email":      {"bsonType": "string",  "description": "Email unique de l'utilisateur"},
            "name":       {"bsonType": "string",  "description": "Nom complet"},
            "plan":       {"bsonType": "string",  "enum": ["free", "basic", "premium"], "description": "Plan souscrit"},
            "created_at": {"bsonType": "date",    "description": "Date d'inscription"},
        },
    }
}

PROJECTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        # Clé applicative : project_id (chaîne libre, ex. "demo"), pas l'_id Mongo. Le modèle
        # multi-tenant (user_id/widget_key) est un vestige hors périmètre hackathon (SPECS §14,
        # Décisions de cadrage) : champs gardés optionnels pour compat, jamais requis.
        "required": ["project_id", "created_at"],
        "properties": {
            "project_id":     {"bsonType": "string",  "description": "Identifiant applicatif du projet"},
            "team_language":  {"bsonType": "string",  "enum": ["fr", "en"], "description": "Langue des artefacts destinés à l'équipe (étape 4.2)"},
            "feedback_count": {"bsonType": "int",     "description": "Compteur dénormalisé"},
            "created_at":     {"bsonType": "date"},
            "user_id":        {"bsonType": "string",  "description": "Hérité, non utilisé"},
            "name":           {"bsonType": "string",  "description": "Hérité, non utilisé"},
            "widget_key":     {"bsonType": "string",  "description": "Hérité, non utilisé"},
            "url":            {"bsonType": "string",  "description": "Hérité, non utilisé"},
        },
    }
}

FEEDBACKS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["project_id", "text", "category", "sentiment", "source", "created_at"],
        "properties": {
            "project_id":  {"bsonType": "string"},
            "text":        {"bsonType": "string",  "description": "Texte nettoyé du feedback"},
            "summary":     {"bsonType": "string",  "description": "Résumé 1 phrase généré par Gemini"},
            "category":    {"bsonType": "string",  "enum": ["bug", "feature_request", "ux", "pricing", "other"]},
            "sentiment":   {"bsonType": "double",  "minimum": -1, "maximum": 1},
            "priority":    {"bsonType": "string",  "enum": ["high", "medium", "low"]},
            "source":      {"bsonType": "string",  "enum": ["widget", "csv", "url", "manual", "text"]},
            "language":    {"bsonType": "string"},
            "fingerprint": {"bsonType": "string",  "description": "Hash SHA256 pour déduplication"},
            "cluster_id":  {"bsonType": ["string", "null"]},
            "embedding":   {"bsonType": "array",   "description": "Vecteur 768 dims généré par Gemini"},
            "created_at":  {"bsonType": "date"},
        },
    }
}

CLUSTERS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["project_id", "label", "feedback_count", "updated_at"],
        "properties": {
            "project_id":     {"bsonType": "string"},
            "label":          {"bsonType": "string",  "description": "Label généré par Gemini"},
            "feedback_count": {"bsonType": "int"},
            "avg_sentiment":  {"bsonType": "double"},
            "centroid":       {"bsonType": "array",   "description": "Moyenne des embeddings du cluster"},
            "updated_at":     {"bsonType": "date"},
        },
    }
}

INSIGHTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["project_id", "type", "stats", "generated_at"],
        "properties": {
            "project_id":      {"bsonType": "string"},
            "type":            {"bsonType": "string",  "enum": ["weekly", "monthly", "on_demand"]},
            "stats":           {"bsonType": "object",  "description": "total, this_week, avg_sentiment, clusters"},
            "top_issues":      {"bsonType": "array"},
            "recommendations": {"bsonType": "array"},
            "generated_at":    {"bsonType": "date"},
        },
    }
}


# ── Création des collections ─────────────────────────────────────────────────

def create_collections(db):
    existing = db.list_collection_names()

    specs = [
        ("users",     USERS_VALIDATOR),
        ("projects",  PROJECTS_VALIDATOR),
        ("feedbacks", FEEDBACKS_VALIDATOR),
        ("clusters",  CLUSTERS_VALIDATOR),
        ("insights",  INSIGHTS_VALIDATOR),
    ]

    for name, validator in specs:
        if name in existing:
            # Mettre à jour le validator si la collection existe déjà
            db.command("collMod", name, validator=validator)
            print(f"{name} - validator mis à jour")
        else:
            db.create_collection(name, validator=validator)
            print(f"{name} - créée")


# ── Indexes ──────────────────────────────────────────────────────────────────

def create_indexes(db):
    # users
    db.users.create_index("email", unique=True, name="idx_users_email")

    # projects
    # idx_projects_project_id : la vraie clé applicative (project_id), utilisée partout dans le
    # code depuis l'étape 4.2. idx_projects_user/idx_projects_widget_key : vestiges de l'ancien
    # modèle multi-tenant, hors périmètre — gardés en sparse pour ne jamais bloquer un upsert
    # par project_id qui ne renseigne pas ces champs (bug réel rencontré à l'étape 5.1 : un index
    # unique non-sparse sur un champ absent traite "absent" comme null, et refuse plus d'un
    # document sans ce champ).
    db.projects.create_index("project_id", unique=True, name="idx_projects_project_id")
    db.projects.create_index([("user_id", ASCENDING)], sparse=True, name="idx_projects_user")
    db.projects.create_index("widget_key", unique=True, sparse=True, name="idx_projects_widget_key")

    # feedbacks
    db.feedbacks.create_index(
        [("project_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_feedbacks_project_date",
    )
    db.feedbacks.create_index(
        [("project_id", ASCENDING), ("category", ASCENDING)],
        name="idx_feedbacks_project_category",
    )
    db.feedbacks.create_index(
        [("project_id", ASCENDING), ("cluster_id", ASCENDING)],
        name="idx_feedbacks_cluster",
    )
    db.feedbacks.create_index(
        [("project_id", ASCENDING), ("sentiment", ASCENDING)],
        name="idx_feedbacks_sentiment",
    )
    db.feedbacks.create_index(
        [("project_id", ASCENDING), ("fingerprint", ASCENDING)],
        unique=True,
        name="idx_feedbacks_fingerprint",
    )

    # clusters
    db.clusters.create_index(
        [("project_id", ASCENDING), ("feedback_count", DESCENDING)],
        name="idx_clusters_project_count",
    )

    # insights
    db.insights.create_index(
        [("project_id", ASCENDING), ("generated_at", DESCENDING)],
        name="idx_insights_project_date",
    )

    print("Tous les indexes créés")


# ── Données de démonstration ─────────────────────────────────────────────────

def insert_demo_data(db):
    now = datetime.now(timezone.utc)

    # User démo
    user_result = db.users.update_one(
        {"email": "demo@feedbackai.dev"},
        {"$setOnInsert": {
            "email":      "demo@feedbackai.dev",
            "name":       "Demo Founder",
            "plan":       "free",
            "created_at": now,
        }},
        upsert=True,
    )

    # Project démo
    db.projects.update_one(
        {"widget_key": "demo-key-001"},
        {"$setOnInsert": {
            "user_id":        "demo",
            "name":           "Mon SaaS",
            "widget_key":     "demo-key-001",
            "url":            "https://example.com",
            "feedback_count": 0,
            "created_at":     now,
        }},
        upsert=True,
    )

    # Feedbacks démo (sans embedding - à générer via l'agent)
    demo_feedbacks = [
        {"text": "L'onboarding est vraiment trop compliqué, j'ai abandonné au milieu",   "category": "ux",             "sentiment": -0.75, "priority": "high",   "source": "manual"},
        {"text": "Super produit mais il manque un export CSV de mes données",              "category": "feature_request","sentiment":  0.30, "priority": "medium", "source": "manual"},
        {"text": "Bug critique : l'application crash quand j'uploade un fichier > 5MB",   "category": "bug",            "sentiment": -0.90, "priority": "high",   "source": "manual"},
        {"text": "Le prix est trop élevé pour une startup early-stage",                   "category": "pricing",        "sentiment": -0.55, "priority": "medium", "source": "manual"},
        {"text": "J'adore la simplicité de l'interface, c'est exactement ce qu'il faut", "category": "ux",             "sentiment":  0.85, "priority": "low",    "source": "manual"},
        {"text": "Impossible de me connecter depuis Safari sur iPhone",                   "category": "bug",            "sentiment": -0.80, "priority": "high",   "source": "manual"},
        {"text": "Pourriez-vous ajouter une intégration avec Slack ?",                    "category": "feature_request","sentiment":  0.20, "priority": "medium", "source": "manual"},
        {"text": "L'onboarding devrait avoir une vidéo de démonstration",                 "category": "ux",             "sentiment":  0.10, "priority": "low",    "source": "manual"},
    ]

    import hashlib
    for fb in demo_feedbacks:
        fp = hashlib.sha256(fb["text"].lower().encode()).hexdigest()[:16]
        db.feedbacks.update_one(
            {"project_id": "demo", "fingerprint": fp},
            {"$setOnInsert": {
                "project_id":  "demo",
                "text":        fb["text"],
                "summary":     fb["text"][:80],
                "category":    fb["category"],
                "sentiment":   fb["sentiment"],
                "priority":    fb["priority"],
                "source":      fb["source"],
                "language":    "fr",
                "fingerprint": fp,
                "cluster_id":  None,
                "embedding":   [],   # sera rempli par l'agent
                "created_at":  now,
            }},
            upsert=True,
        )

    count = db.feedbacks.count_documents({"project_id": "demo"})
    print(f"{count} feedbacks démo insérés (project_id='demo')")


# ── Vector Search index (instructions) ──────────────────────────────────────

VECTOR_INDEX_CONFIG = """
{
  "name": "feedback_vector_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "embedding",
        "numDimensions": 768,
        "similarity": "cosine"
      },
      {
        "type": "filter",
        "path": "project_id"
      },
      {
        "type": "filter",
        "path": "category"
      },
      {
        "type": "filter",
        "path": "sentiment"
      }
    ]
  }
}
"""

def print_vector_index_instructions():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          INDEX VECTOR SEARCH - Action manuelle requise       ║
╠══════════════════════════════════════════════════════════════╣
║  L'index Vector Search ne peut pas être créé via PyMongo.    ║
║  Il doit être créé dans Atlas UI ou via l'API Atlas Admin.   ║
║                                                              ║
║  Atlas UI :                                                  ║
║  1. Ouvrir ton cluster dans atlas.mongodb.com                ║
║  2. Onglet "Atlas Search" → "Create Search Index"            ║
║  3. Choisir "Vector Search" (JSON editor)                    ║
║  4. Database : feedbackai  |  Collection : feedbacks         ║
║  5. Coller le JSON ci-dessous et valider                     ║
╚══════════════════════════════════════════════════════════════╝
""")
    print(VECTOR_INDEX_CONFIG)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\nInitialisation de la base MongoDB - '{DB_NAME}'\n")

    try:
        db = get_db()
    except Exception as e:
        print(f"Connexion échouée : {e}")
        print("Vérifie que MONGODB_URI est correct dans ton .env")
        sys.exit(1)

    print("\nCollections :")
    create_collections(db)

    print("\nIndexes :")
    create_indexes(db)

    print("\nDonnées de démo :")
    insert_demo_data(db)

    print_vector_index_instructions()

    print("Setup terminé. Lance maintenant l'agent avec : uvicorn agent:app --reload\n")


if __name__ == "__main__":
    main()