"""
Configuration centralisée de l'agent.

Accès Gemini via l'API Gemini directe (google-genai + GEMINI_API_KEY), pas Vertex AI :
gemini-3.5-flash a été mesuré indisponible sur Vertex AI pour ce projet (404, testé sur
plusieurs régions avec l'ancien SDK vertexai et le nouveau google-genai en mode Vertex),
mais fonctionne via l'API Gemini. Décidé avec Aissatou le 2026-08-18.
"""

MODEL_NAME = "gemini-3.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
