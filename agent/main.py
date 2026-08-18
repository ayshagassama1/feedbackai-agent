"""
Feedback Agent — orchestrateur principal
Basé sur Google Cloud Agent Builder (Gemini Enterprise Agent Platform SDK)
"""

import os
from google import genai
from google.genai import types
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from config                  import MODEL_NAME
from tools.ingest_feedback   import ingest_feedback
from tools.cluster_feedback  import cluster_feedback
from tools.generate_insights import generate_insights
from tools.search_feedback   import search_feedback
from db                      import get_mongo_client

# ── Init client Gemini (API Gemini directe) ─────────────────────────────────
_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_INSTRUCTION = """
Tu es un agent d'analyse de feedback produit pour des équipes SaaS early-stage.
Tu as accès à des outils pour ingérer, clusteriser, analyser et rechercher des feedbacks.
Réponds toujours en français. Sois concis, actionnable, et précis.
"""

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

@app.post("/api/ingest")
async def api_ingest(req: IngestTextRequest):
    """Ingère un feedback texte ou URL."""
    try:
        result = await ingest_feedback(
            project_id=req.project_id,
            source=req.source,
            content=req.content,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """Point d'entrée du chat agent — orchestre les tools selon la question."""
    tools = [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="search_feedback",
                description="Recherche des feedbacks par similarité sémantique ou mots-clés",
                parameters={
                    "type": "object",
                    "properties": {
                        "query":      {"type": "string", "description": "La question ou les mots-clés à rechercher"},
                        "project_id": {"type": "string"},
                        "limit":      {"type": "integer", "default": 10},
                    },
                    "required": ["query", "project_id"],
                },
            ),
            types.FunctionDeclaration(
                name="generate_insights",
                description="Génère ou rafraîchit les insights et recommandations pour un projet",
                parameters={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                    },
                    "required": ["project_id"],
                },
            ),
            types.FunctionDeclaration(
                name="cluster_feedback",
                description="Lance le reclustering des feedbacks d'un projet",
                parameters={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string"},
                    },
                    "required": ["project_id"],
                },
            ),
        ])
    ]

    # Construire l'historique pour Gemini
    history = [
        types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
        for m in req.history
    ]

    chat = _client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=tools,
        ),
        history=history,
    )
    response = chat.send_message(req.message + f"\n[project_id: {req.project_id}]")

    # Gérer les appels de tools
    while response.candidates[0].content.parts[0].function_call:
        call = response.candidates[0].content.parts[0].function_call
        fn_name = call.name
        fn_args = dict(call.args)

        if fn_name == "search_feedback":
            tool_result = await search_feedback(**fn_args)
        elif fn_name == "generate_insights":
            tool_result = await generate_insights(**fn_args)
        elif fn_name == "cluster_feedback":
            tool_result = await cluster_feedback(**fn_args)
        else:
            tool_result = {"error": f"Tool inconnu : {fn_name}"}

        response = chat.send_message(
            types.Part.from_function_response(
                name=fn_name,
                response={"content": str(tool_result)},
            )
        )

    return {"response": response.text}


@app.post("/api/insights/refresh")
async def api_refresh_insights(project_id: str):
    """Force la régénération des insights."""
    result = await generate_insights(project_id=project_id)
    result["_id"] = str(result.get("_id", ""))
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
