"""
Script jetable vérifie l'accès Vertex AI et la disponibilité de gemini-2.5-flash.

gemini-3.5-flash (décision de cadrage initiale) a été mesuré indisponible (404) sur le
projet feedbackai-497622, testé sur us-central1/europe-west1/europe-west4. Seuls
gemini-2.5-flash et gemini-2.5-pro répondent réellement à ce jour ; gemini-2.5-flash a été
retenu (corrigé avec Aissatou le 2026-08-18).

Usage : python scripts/check_model.py
Prérequis : GCP_PROJECT_ID (et optionnellement GCP_REGION) en variables d'environnement,
Application Default Credentials configurées (gcloud auth application-default login).
"""

import os
import vertexai
from vertexai.generative_models import GenerativeModel

MODEL_NAME = "gemini-2.5-flash"


def main():
    project = os.environ["GCP_PROJECT_ID"]
    region = os.environ.get("GCP_REGION", "us-central1")

    vertexai.init(project=project, location=region)
    model = GenerativeModel(MODEL_NAME)

    response = model.generate_content("Réponds uniquement par : ok")
    print(f"Modèle   : {MODEL_NAME}")
    print(f"Projet   : {project}")
    print(f"Région   : {region}")
    print(f"Réponse  : {response.text.strip()}")


if __name__ == "__main__":
    main()
