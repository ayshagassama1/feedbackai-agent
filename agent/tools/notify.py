"""
Tool : notify
Notification simple (log structuré) — pas de dépendance externe pour la démo. Message
bilingue FR/EN. Un webhook Slack entrant peut remplacer ce log plus tard sans changer la
signature du tool (voir README).
"""

import logging

logger = logging.getLogger("feedback_agent.notify")


async def notify(project_id: str, message_fr: str, message_en: str) -> dict:
    """
    Notifie l'équipe d'un événement (ex. nouveau ticket créé). Message bilingue FR/EN.

    Args:
        project_id : identifiant du projet concerné
        message_fr : message en français
        message_en : message en anglais

    Returns:
        dict confirmant l'envoi
    """
    logger.info("[NOTIFY] project=%s | FR: %s | EN: %s", project_id, message_fr, message_en)
    return {"sent": True, "channel": "log", "message_fr": message_fr, "message_en": message_en}
