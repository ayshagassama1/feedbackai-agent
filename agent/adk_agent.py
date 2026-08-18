"""
Définition de l'agent ADK et de ses tools.
"""

from google.adk.agents import LlmAgent

from config import MODEL_NAME
from tools.search_feedback import search_feedback
from tools.generate_insights import generate_insights
from tools.cluster_feedback import cluster_feedback

APP_NAME = "feedback_agent"


async def create_ticket(cluster_label: str, project_id: str) -> dict:
    """
    Crée un ticket dans le tracker externe pour un cluster de feedback prioritaire.
    Stub — implémenté en PHASE 2 (agent/tools/create_ticket.py, GitHub Issues).

    Args:
        cluster_label : label du cluster concerné
        project_id    : identifiant du projet

    Returns:
        dict indiquant que l'action n'est pas encore implémentée
    """
    return {
        "status": "not_implemented",
        "message": "create_ticket sera implémenté en PHASE 2 (GitHub Issues).",
    }


SYSTEM_INSTRUCTION = """
Tu es un agent d'analyse de feedback produit pour des équipes SaaS early-stage.
Tu as accès à des outils pour rechercher, analyser et clusteriser des feedbacks, et pour créer
des tickets dans un tracker externe.
Réponds toujours dans la langue de l'utilisateur (français ou anglais). Sois concis, actionnable
et précis.
"""

root_agent = LlmAgent(
    name=APP_NAME,
    model=MODEL_NAME,
    instruction=SYSTEM_INSTRUCTION,
    tools=[search_feedback, generate_insights, cluster_feedback, create_ticket],
)
