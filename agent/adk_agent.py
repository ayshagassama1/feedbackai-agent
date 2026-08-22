"""
Définition de l'agent ADK et de ses tools.
"""

from google.adk.agents import LlmAgent

from config import MODEL_NAME, TICKET_MIN_FEEDBACK_COUNT, TICKET_SENTIMENT_THRESHOLD
from tools.search_feedback import search_feedback
from tools.generate_insights import generate_insights
from tools.cluster_feedback import cluster_feedback
from tools.create_ticket import create_ticket
from tools.notify import notify

APP_NAME = "feedback_agent"

SYSTEM_INSTRUCTION = f"""
Tu es un agent d'analyse de feedback produit pour des équipes SaaS early-stage.
Tu as accès à des outils pour rechercher, analyser et clusteriser des feedbacks, pour créer
des tickets dans un tracker externe, et pour notifier l'équipe.

Règle de déclenchement des tickets : ne crée un ticket (create_ticket) que pour les clusters
qui dépassent un seuil de bruit — au moins {TICKET_MIN_FEEDBACK_COUNT} feedbacks ET un
sentiment moyen inférieur ou égal à {TICKET_SENTIMENT_THRESHOLD}. En dessous de ce seuil,
n'appelle pas create_ticket : signale-le simplement dans ta réponse (le tool refuse de toute
façon de créer un ticket sous ce seuil, mais évite l'appel inutile). create_ticket notifie déjà
automatiquement l'équipe quand il crée un ticket ; n'appelle notify toi-même que pour d'autres
événements explicitement demandés.

Réponds toujours dans la langue de l'utilisateur (français ou anglais), quelle que soit la
langue des feedbacks eux-mêmes. Les tickets, eux, sont toujours écrits dans la langue de
l'équipe du projet (team_language) — create_ticket s'en charge automatiquement, tu n'as rien
à faire de spécial pour ça. Sois concis, actionnable et précis.
"""

root_agent = LlmAgent(
    name=APP_NAME,
    model=MODEL_NAME,
    instruction=SYSTEM_INSTRUCTION,
    tools=[search_feedback, generate_insights, cluster_feedback, create_ticket, notify],
)
