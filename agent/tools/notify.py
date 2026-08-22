"""
Tool : notify
Notification simple (log structuré) — pas de dépendance externe pour la démo. Le message est
produit dans la langue de l'équipe (team_language) par l'appelant. Un webhook Slack entrant
peut remplacer ce log plus tard sans changer la signature du tool (voir README).
"""

import logging

logger = logging.getLogger("feedback_agent.notify")


async def notify(project_id: str, message: str, language: str) -> dict:
    """
    Notifie l'équipe d'un événement (ex. nouveau ticket créé).

    Args:
        project_id : identifiant du projet concerné
        message    : message déjà rédigé dans la langue de l'équipe
        language   : langue du message ('fr' ou 'en'), pour traçabilité dans les logs

    Returns:
        dict confirmant l'envoi
    """
    logger.info("[NOTIFY] project=%s language=%s message=%s", project_id, language, message)
    return {"sent": True, "channel": "log", "message": message, "language": language}
