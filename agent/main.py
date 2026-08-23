"""
Feedback Agent — orchestrateur principal
Basé sur Google Cloud Agent Builder (Gemini Enterprise Agent Platform SDK)
"""

import os
import json
import base64
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.events import Event
from google.genai import types
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

from adk_agent                import root_agent, APP_NAME
from tools.ingest_feedback    import ingest_feedback
from tools.cluster_feedback   import cluster_feedback
from tools.generate_insights  import generate_insights
from tools.create_ticket      import create_ticket
from db                       import get_mongo_client, get_team_language, DEFAULT_TEAM_LANGUAGE

logger = logging.getLogger("feedback_agent.main")

RUN_CYCLE_SECRET = os.environ.get("RUN_CYCLE_SECRET", "")

# ── Auth Pub/Sub push (jeton OIDC) — étape 3.2 ───────────────────────────────
PUBSUB_PUSH_SERVICE_ACCOUNT = os.environ.get("PUBSUB_PUSH_SERVICE_ACCOUNT", "")
RUN_CYCLE_AUDIENCE = os.environ.get("RUN_CYCLE_AUDIENCE", "")
_google_auth_request = google_auth_requests.Request()


def _verify_pubsub_oidc(authorization_header: Optional[str]) -> bool:
    """Vérifie un jeton OIDC signé par Google, émis pour le compte de service de la
    subscription push Pub/Sub, avec l'audience attendue (URL de cet endpoint)."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return False
    if not PUBSUB_PUSH_SERVICE_ACCOUNT or not RUN_CYCLE_AUDIENCE:
        return False
    token = authorization_header[len("Bearer "):]
    try:
        claims = google_id_token.verify_oauth2_token(
            token, _google_auth_request, audience=RUN_CYCLE_AUDIENCE
        )
    except Exception as e:
        logger.warning("Jeton OIDC invalide sur /api/agent/run-cycle : %s", e)
        return False
    return claims.get("email") == PUBSUB_PUSH_SERVICE_ACCOUNT and claims.get("email_verified")

# ── Runner ADK ───────────────────────────────────────────────────────────────
_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)

# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="Feedback Agent API")

# Resserré sur l'origine réelle du frontend déployé (étape 5.1) — plus de wildcard "*".
# FRONTEND_ORIGINS : liste d'origines séparées par des virgules.
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Schemas ─────────────────────────────────────────────────────────────────
class IngestTextRequest(BaseModel):
    project_id: str
    source: str       # "text" | "url"
    content: str

class ChatRequest(BaseModel):
    project_id: str
    message: str
    history: Optional[List[dict]] = []

class ProjectSettingsRequest(BaseModel):
    team_language: str  # "fr" | "en"

# ── Routes ──────────────────────────────────────────────────────────────────

async def _ingest_feedback_background(project_id: str, source: str, content: str) -> None:
    """Exécute l'ingestion complète (classification, embedding, écriture) en tâche de fond."""
    try:
        await ingest_feedback(project_id=project_id, source=source, content=content)
    except Exception as e:
        logger.error("Échec de l'ingestion en tâche de fond (project=%s) : %s", project_id, e)


@app.post("/api/ingest", status_code=202)
async def api_ingest(req: IngestTextRequest, background_tasks: BackgroundTasks):
    """Accepte un feedback texte ou URL et l'ingère en tâche de fond (réponse immédiate)."""
    background_tasks.add_task(_ingest_feedback_background, req.project_id, req.source, req.content)
    return {"status": "queued", "project_id": req.project_id}


async def _ingest_csv_background(project_id: str, content: bytes) -> None:
    """Ingère chaque ligne valide d'un CSV en tâche de fond."""
    import csv, io
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        ingested = 0
        for row in reader:
            text = row.get("text") or row.get("feedback") or row.get("content") or ""
            if text.strip():
                await ingest_feedback(project_id=project_id, source="csv", content=text.strip())
                ingested += 1
        logger.info("Ingestion CSV terminée (project=%s) : %d ligne(s) ingérée(s).", project_id, ingested)
    except Exception as e:
        logger.error("Échec de l'ingestion CSV en tâche de fond (project=%s) : %s", project_id, e)


@app.post("/api/ingest/csv", status_code=202)
async def api_ingest_csv(
    background_tasks: BackgroundTasks,
    project_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Accepte un fichier CSV de feedbacks et l'ingère en tâche de fond (réponse immédiate)."""
    content = await file.read()
    background_tasks.add_task(_ingest_csv_background, project_id, content)
    return {"status": "queued", "project_id": project_id}


@app.get("/api/insights")
async def api_insights(project_id: str):
    """Retourne les derniers insights générés pour un projet."""
    db = get_mongo_client()
    insight = db.insights.find_one(
        {"project_id": project_id},
        sort=[("generated_at", -1)],
    )
    if not insight:
        # Génération à la volée si aucun insight existant
        insight = await generate_insights(project_id=project_id)
    insight["_id"] = str(insight["_id"])
    return insight


@app.get("/api/clusters")
async def api_clusters(project_id: str):
    """Retourne les clusters d'un projet."""
    db = get_mongo_client()
    clusters = list(
        db.clusters.find({"project_id": project_id}).sort("feedback_count", -1)
    )
    for c in clusters:
        c["_id"] = str(c["_id"])
        c.pop("centroid", None)   # ne pas exposer les vecteurs bruts
    return {"clusters": clusters}


@app.get("/api/feedbacks")
async def api_feedbacks(project_id: str, cluster_id: Optional[str] = None):
    """Retourne les feedbacks d'un projet, optionnellement filtrés par cluster."""
    db = get_mongo_client()
    query = {"project_id": project_id}
    if cluster_id:
        query["cluster_id"] = cluster_id
    feedbacks = list(
        db.feedbacks.find(query, {"embedding": 0}).sort("created_at", -1).limit(50)
    )
    for f in feedbacks:
        f["_id"] = str(f["_id"])
    return {"feedbacks": feedbacks}


@app.get("/api/projects/{project_id}/settings")
async def api_get_project_settings(project_id: str):
    """Retourne les réglages d'un projet (aujourd'hui : team_language uniquement)."""
    return {"project_id": project_id, "team_language": get_team_language(project_id)}


@app.put("/api/projects/{project_id}/settings")
async def api_update_project_settings(project_id: str, req: ProjectSettingsRequest):
    """
    Définit team_language ('fr' ou 'en') — la langue dans laquelle les artefacts destinés à
    l'équipe (labels de cluster, insights, tickets, notifications) sont produits.
    """
    if req.team_language not in ("fr", "en"):
        raise HTTPException(status_code=400, detail="team_language doit être 'fr' ou 'en'.")

    db = get_mongo_client()
    db.projects.update_one(
        {"project_id": project_id},
        {
            "$set": {"team_language": req.team_language},
            "$setOnInsert": {"project_id": project_id, "created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
    return {"project_id": project_id, "team_language": req.team_language}


@app.post("/api/agent/chat")
async def api_agent_chat(req: ChatRequest):
    """Point d'entrée du chat agent — orchestré par le Runner ADK (plus de dispatch manuel)."""
    session = await _session_service.create_session(app_name=APP_NAME, user_id=req.project_id)

    # Reprendre l'historique court envoyé par le front (AgentChat.jsx, 6 derniers messages)
    for m in req.history:
        await _session_service.append_event(
            session,
            Event(
                author="user" if m["role"] == "user" else root_agent.name,
                content=types.Content(role=m["role"], parts=[types.Part(text=m["content"])]),
            ),
        )

    new_message = types.Content(
        role="user",
        parts=[types.Part(text=req.message + f"\n[project_id: {req.project_id}]")],
    )

    final_text = ""
    async for event in _runner.run_async(
        user_id=session.user_id, session_id=session.id, new_message=new_message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text

    return {"response": final_text}


@app.post("/api/agent/run-cycle")
async def api_run_cycle(
    request: Request,
    x_run_cycle_secret: Optional[str] = Header(None, alias="X-Run-Cycle-Secret"),
    authorization: Optional[str] = Header(None),
):
    """
    Cycle autonome complet pour un projet : (re)clustering -> insights -> pour chaque cluster
    éligible et non ticketé, création de ticket + notification.

    Jamais public. Deux façons d'authentifier une requête :
    - Jeton OIDC (Authorization: Bearer ...) émis pour la subscription push Pub/Sub
      (PHASE 3, étape 3.2) — le corps est alors l'enveloppe standard Pub/Sub push
      ({"message": {"data": "<project_id en JSON, base64>", ...}}).
    - Secret partagé (X-Run-Cycle-Secret) pour un appel direct (tests, débogage) — le corps
      est alors {"project_id": "..."} directement.
    """
    body = await request.json()

    if _verify_pubsub_oidc(authorization):
        message = body.get("message", {})
        data_b64 = message.get("data", "")
        if not data_b64:
            raise HTTPException(status_code=400, detail="Message Pub/Sub sans champ data.")
        try:
            payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"Message Pub/Sub illisible : {e}")
        project_id = payload.get("project_id")
    elif RUN_CYCLE_SECRET and x_run_cycle_secret == RUN_CYCLE_SECRET:
        project_id = body.get("project_id")
    else:
        raise HTTPException(status_code=401, detail="Requête non authentifiée.")

    if not project_id:
        raise HTTPException(status_code=400, detail="project_id manquant.")

    clustering_result = await cluster_feedback(project_id=project_id)
    insights_result = await generate_insights(project_id=project_id)

    db = get_mongo_client()
    clusters = list(db.clusters.find({"project_id": project_id}))

    ticket_results = []
    for c in clusters:
        result = await create_ticket(project_id=project_id, cluster_id=str(c["_id"]))
        ticket_results.append({"cluster_id": str(c["_id"]), "label": c["label"], **result})

    return {
        "project_id": project_id,
        "clustering": clustering_result,
        "insights": {
            "stats": insights_result.get("stats"),
            "recommendations": insights_result.get("recommendations"),
        },
        "tickets": ticket_results,
    }


@app.post("/api/insights/refresh")
async def api_refresh_insights(project_id: str):
    """Force la régénération des insights."""
    result = await generate_insights(project_id=project_id)
    result["_id"] = str(result.get("_id", ""))
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
