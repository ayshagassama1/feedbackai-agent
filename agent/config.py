"""
Configuration centralisée de l'agent.

Accès Gemini via Vertex AI (GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION,
voir .env), plus l'API Gemini directe (GEMINI_API_KEY). Historique :
- 2026-08-18 : gemini-3.5-flash mesuré indisponible sur Vertex AI pour ce projet (404, testé
  sur plusieurs régions avec l'ancien SDK vertexai et le nouveau google-genai en mode Vertex).
  Bascule sur l'API Gemini directe.
- 2026-08-30 : redevenu disponible sur Vertex AI, mais uniquement sur la location "global"
  (toujours 404 sur us-central1). Rebasculé sur Vertex pour consommer les crédits GCP du
  hackathon plutôt que le palier gratuit de l'API Gemini directe (5 req/min, 20 req/jour, trop
  restrictif en usage réel). GEMINI_API_KEY n'est donc plus consulté par aucun appel Gemini du
  code (tous les clients `genai.Client()` sont construits sans argument, auto-détection par
  variables d'environnement) — gardé en variable/secret par précaution, pas activement utilisé.
"""

MODEL_NAME = "gemini-3.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

# Seuil de déclenchement pour create_ticket — évite le bruit (PHASE 2, étape 2.2). Un cluster
# doit atteindre les deux conditions pour être ticketé : assez de volume ET un sentiment
# suffisamment négatif.
TICKET_MIN_FEEDBACK_COUNT = 3
TICKET_SENTIMENT_THRESHOLD = -0.3
