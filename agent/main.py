"""
Feedback Agent — orchestrateur principal
Basé sur Google Cloud Agent Builder (Gemini Enterprise Agent Platform SDK)
"""

import os
import logging

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.events import Event
from google.genai import types

from adk_agent                import root_agent, APP_NAME
from tools.ingest_feedback    import ingest_feedback
from tools.cluster_feedback   import cluster_feedback
from tools.generate_insights  import generate_insights
from tools.create_ticket      import create_ticket
from db                       import get_mongo_client

logger = logging.getLogger("feedback_agent.main")

RUN_CYCLE_SECRET = os.environ.get("RUN_CYCLE_SECRET", "")

# ── Runner ADK ───────────────────────────────────────────────────────────────
_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=_session_service)

# ── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="Feedback Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.post("/api/ingest/csv")
async def api_ingest_csv(project_id: str, file: bytes):
    """Ingère un fichier CSV de feedbacks."""
    import csv, io
    reader = csv.DictReader(io.StringIO(file.decode("utf-8")))
    results = []
    for row in reader:
        text = row.get("text") or row.get("feedback") or row.get("content") or ""
        if text.strip():
            r = await ingest_feedback(
                project_id=project_id,
                source="csv",
                content=text.strip(),
            )
            results.append(r)
    return {"ingested": len(results), "results": results}


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


class RunCycleRequest(BaseModel):
    project_id: str


@app.post("/api/agent/run-cycle")
async def api_run_cycle(
    req: RunCycleRequest,
    x_run_cycle_secret: Optional[str] = Header(None, alias="X-Run-Cycle-Secret"),
):
    """
    Cycle autonome complet pour un projet : (re)clustering -> insights -> pour chaque cluster
    éligible et non ticketé, création de ticket + notification.

    Protégé par un secret partagé (RUN_CYCLE_SECRET) en en-tête, jamais public — destiné à être
    déclenché par Cloud Scheduler -> Pub/Sub (PHASE 3, étape 3.2), pas par un client ouvert.
    """
    if not RUN_CYCLE_SECRET or x_run_cycle_secret != RUN_CYCLE_SECRET:
        raise HTTPException(status_code=401, detail="Secret invalide ou manquant.")

    project_id = req.project_id

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
