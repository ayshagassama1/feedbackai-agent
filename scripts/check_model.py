"""
Script jetable — vérifie l'accès à gemini-3.5-flash via l'API Gemini directe.

Décision de cadrage : gemini-3.5-flash (exigé par le règlement du hackathon) a été mesuré
indisponible sur Vertex AI pour ce projet (404, testé sur plusieurs régions, avec l'ancien
SDK vertexai et le nouveau google-genai en mode Vertex), mais fonctionne via l'API Gemini
directe (google-genai + clé API). Confirmé end-to-end (chat, function calling, embeddings
768 dims) avec Aissatou le 2026-08-18.

Usage : python scripts/check_model.py
Prérequis : GEMINI_API_KEY en variable d'environnement.
"""

import os
from google import genai

MODEL_NAME = "gemini-3.5-flash"


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    response = client.models.generate_content(model=MODEL_NAME, contents="Réponds uniquement par : ok")

    print(f"Modèle   : {MODEL_NAME}")
    print(f"Réponse  : {response.text.strip()}")


if __name__ == "__main__":
    main()
