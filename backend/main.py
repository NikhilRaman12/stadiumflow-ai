"""

StadiumIQ FastAPI Main Application

===================================

FIFA World Cup 2026 - GenAI Operations Platform

LangGraph · MCP · A2A · GraphRAG · Gemini 1.5 Pro

"""

import os

import json

import asyncio

import logging

from contextlib import asynccontextmanager

from typing import AsyncGenerator



from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request

from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse, FileResponse

from fastapi.middleware.trustedhost import TrustedHostMiddleware

from pydantic import BaseModel

from dotenv import load_dotenv

from middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware



load_dotenv()



# Internal modules

from graph_rag.graph_builder   import StadiumKnowledgeGraph

from graph_rag.graph_retriever import GraphRAGRetriever

from mcp.stadium_server        import StadiumMCPServer

from mcp.crowd_server          import CrowdMCPServer

from mcp.transport_server      import TransportMCPServer

from mcp.eco_server            import EcoMCPServer

from a2a.a2a_server            import A2ARouter

from a2a.agent_cards           import get_all_agent_cards

from agents.fan_agent          import FanAssistantGraph

from agents.crowd_agent        import CrowdIntelligenceGraph

from agents.incident_agent     import IncidentResponseGraph

from agents.transport_agent    import TransportOptimizerGraph

from agents.eco_agent          import EcoScoringGraph

from agents.ops_agent          import OpsCommandGraph

from services.crowd_simulator  import CrowdSimulator

from services.transport_optimizer import TransportOptimizer

from services.incident_manager import IncidentManager

from api import chat, crowd, incidents, transport, eco, analytics



log = logging.getLogger("stadiumiq")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s - %(message)s")



# ── Global singletons (initialised at startup) ──────────────────────

kg:            StadiumKnowledgeGraph | None = None

retriever:     GraphRAGRetriever     | None = None

fan_graph:     FanAssistantGraph     | None = None

crowd_graph:   CrowdIntelligenceGraph| None = None

incident_graph:IncidentResponseGraph | None = None

transport_graph:TransportOptimizerGraph | None = None

eco_graph:     EcoScoringGraph       | None = None

ops_graph:     OpsCommandGraph       | None = None

crowd_sim:     CrowdSimulator        | None = None

transport_opt: TransportOptimizer    | None = None

incident_mgr:  IncidentManager       | None = None

connected_ws:  list[WebSocket]       = []





# ── Lifespan (startup / shutdown) ────────────────────────────────────

@asynccontextmanager

async def lifespan(app: FastAPI) -> AsyncGenerator:

    global kg, retriever, fan_graph, crowd_graph, incident_graph

    global transport_graph, eco_graph, ops_graph

    global crowd_sim, transport_opt, incident_mgr



    log.info("🏟️  StadiumIQ starting up …")



    # 1. Build GraphRAG knowledge graph

    log.info("📊 Building GraphRAG knowledge graph …")

    kg = StadiumKnowledgeGraph()

    await kg.build()

    retriever = GraphRAGRetriever(kg)

    await retriever.build_index()

    log.info("✅ GraphRAG ready - %d nodes, %d edges", kg.graph.number_of_nodes(), kg.graph.number_of_edges())



    # 2. Initialize MCP servers (in-process, stdio transport simulation)

    log.info("🔌 Starting MCP tool servers …")

    StadiumMCPServer.start(kg)

    CrowdMCPServer.start()

    TransportMCPServer.start()

    EcoMCPServer.start()

    log.info("✅ MCP servers ready")



    # 3. Compile LangGraph StateGraphs for all agents

    log.info("🤖 Compiling LangGraph StateGraphs …")

    fan_graph      = FanAssistantGraph(retriever).compile()

    crowd_graph    = CrowdIntelligenceGraph(retriever).compile()

    incident_graph = IncidentResponseGraph(retriever).compile()

    transport_graph= TransportOptimizerGraph(retriever).compile()

    eco_graph      = EcoScoringGraph(retriever).compile()

    ops_graph      = OpsCommandGraph(retriever, {

        "fan":       fan_graph,

        "crowd":     crowd_graph,

        "incident":  incident_graph,

        "transport": transport_graph,

        "eco":       eco_graph,

    }).compile()

    log.info("✅ All 6 LangGraph agents compiled")



    # 4. Attach graphs to route handlers via app.state

    app.state.fan_graph       = fan_graph

    app.state.crowd_graph     = crowd_graph

    app.state.incident_graph  = incident_graph

    app.state.transport_graph = transport_graph

    app.state.eco_graph       = eco_graph

    app.state.ops_graph       = ops_graph

    app.state.retriever       = retriever

    app.state.kg              = kg



    # 5. Start simulation services

    crowd_sim     = CrowdSimulator()

    transport_opt = TransportOptimizer()

    incident_mgr  = IncidentManager()

    app.state.crowd_sim     = crowd_sim

    app.state.transport_opt = transport_opt

    app.state.incident_mgr  = incident_mgr



    # 6. Start real-time broadcast loop

    asyncio.create_task(broadcast_loop())



    log.info("🚀 StadiumIQ is LIVE - port %s", os.getenv("PORT", 8000))



    yield  # ── Application runs ──────────────────────────────────────



    log.info("🛑 StadiumIQ shutting down …")

    StadiumMCPServer.stop()

    CrowdMCPServer.stop()

    TransportMCPServer.stop()

    EcoMCPServer.stop()





# ── Create FastAPI app ────────────────────────────────────────────────

app = FastAPI(

    title="StadiumIQ GenAI Platform",

    description="FIFA World Cup 2026 - LangGraph · MCP · A2A · GraphRAG",

    version="2.0.0",

    lifespan=lifespan,

    docs_url="/api/docs",

    redoc_url="/api/redoc",

)



# ── Middleware ────────────────────────────────────────────────────────

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["testserver", "localhost", "127.0.0.1", "*.onrender.com", "*.trycloudflare.com", "*.ngrok-free.app"])

# Configure CORS dynamically to support credentials correctly without wildcard issues
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_env and allowed_origins_env != "*":
    origins = allowed_origins_env.split(",")
else:
    origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "https://nikhilraman12.github.io"
    ]
app.add_middleware(CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom security and rate limiting middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=120)



# ── Static Frontend ───────────────────────────────────────────────────
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")
    if os.path.exists(os.path.join(frontend_path, "css")):
        app.mount("/css", StaticFiles(directory=os.path.join(frontend_path, "css")), name="css")
    if os.path.exists(os.path.join(frontend_path, "js")):
        app.mount("/js", StaticFiles(directory=os.path.join(frontend_path, "js")), name="js")
    if os.path.exists(os.path.join(frontend_path, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")



# ── API Routers ────────────────────────────────────────────────────────

app.include_router(chat.router,      prefix="/api/chat",      tags=["ARIA AI Chat"])

app.include_router(crowd.router,     prefix="/api/crowd",     tags=["Crowd Intelligence"])

app.include_router(incidents.router, prefix="/api/incidents", tags=["Incident Management"])

app.include_router(transport.router, prefix="/api/transport", tags=["Transport Optimizer"])

app.include_router(eco.router,       prefix="/api/eco",       tags=["EcoScore"])

app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])



# ── A2A Agent Bus ──────────────────────────────────────────────────────

a2a_router = A2ARouter()

app.include_router(a2a_router.router, prefix="/a2a", tags=["A2A Agent Protocol"])





# ── Health Check ──────────────────────────────────────────────────────

@app.get("/api/health")

async def health(request: Request):

    return {

        "status": "operational",

        "platform": "StadiumIQ - FIFA World Cup 2026",

        "version": "2.0.0",

        "architecture": {

            "llm":       "Google Gemini 1.5 Pro (via LangChain)",

            "agents":    "LangGraph StateGraph (6 specialized agents)",

            "retrieval": "GraphRAG (NetworkX + FAISS)",

            "tools":     "MCP Protocol (4 servers)",

            "comms":     "A2A Agent-to-Agent Protocol",

        },

        "services": {

            "gemini_ai":     "connected" if os.getenv("GEMINI_API_KEY") else "no_key",

            "graphrag":      f"{request.app.state.kg.graph.number_of_nodes()} nodes" if hasattr(request.app.state, "kg") and request.app.state.kg else "initializing",

            "langgraph":     "6 agents compiled" if hasattr(request.app.state, "fan_graph") else "initializing",

            "mcp_servers":   "4 active",

            "a2a_bus":       "active",

            "websocket":     f"{len(connected_ws)} clients",

        },

        "agents": [c.model_dump() for c in get_all_agent_cards()],

    }





@app.get("/")
async def root():
    index = os.path.join(frontend_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "StadiumIQ API - visit /api/docs"}

@app.get("/fan")
async def fan_app():
    f = os.path.join(frontend_path, "fan-app.html")
    if os.path.exists(f):
        return FileResponse(f)
    return JSONResponse(status_code=404, content={"error": "fan-app.html not found"})

@app.get("/ops")
async def ops_dash():
    f = os.path.join(frontend_path, "ops-dashboard.html")
    if os.path.exists(f):
        return FileResponse(f)
    return JSONResponse(status_code=404, content={"error": "ops-dashboard.html not found"})





# ── WebSocket Real-time Feed ──────────────────────────────────────────

@app.websocket("/ws")

async def websocket_endpoint(ws: WebSocket):

    await ws.accept()

    connected_ws.append(ws)

    log.info("WS client connected - total: %d", len(connected_ws))

    try:

        # Send initial state

        if crowd_sim:

            await ws.send_json({"type": "crowd:state",     "data": crowd_sim.get_full_state()})

        if transport_opt:

            await ws.send_json({"type": "transport:state", "data": transport_opt.get_full_state()})

        if incident_mgr:

            await ws.send_json({"type": "incidents:state", "data": incident_mgr.get_active()})



        while True:

            msg = await ws.receive_json()

            await handle_ws_message(ws, msg)

    except WebSocketDisconnect:

        connected_ws.remove(ws)

        log.info("WS client disconnected - total: %d", len(connected_ws))

    except Exception as e:

        log.error("WS error: %s", e)

        if ws in connected_ws:

            connected_ws.remove(ws)





async def handle_ws_message(ws: WebSocket, msg: dict):

    """Handle incoming WebSocket messages from clients."""

    msg_type = msg.get("type", "")

    if msg_type == "subscribe:venue":

        venue_id = msg.get("venue_id")

        if crowd_sim and venue_id:

            await ws.send_json({"type": "venue:state", "data": crowd_sim.get_venue_state(venue_id)})

    elif msg_type == "incident:report":

        if incident_mgr:

            incident = incident_mgr.create_incident(msg.get("data", {}))

            await broadcast({"type": "incident:new", "data": incident})

    elif msg_type == "ping":

        await ws.send_json({"type": "pong", "ts": asyncio.get_event_loop().time()})





async def broadcast(payload: dict):

    """Broadcast to all connected WebSocket clients."""

    dead = []

    for ws in connected_ws:

        try:

            await ws.send_json(payload)

        except Exception:

            dead.append(ws)

    for ws in dead:

        connected_ws.remove(ws)





async def broadcast_loop():

    """Periodic real-time data push to all WebSocket clients."""

    tick = 0

    while True:

        await asyncio.sleep(10)

        tick += 1

        try:

            if crowd_sim:

                await broadcast({"type": "crowd:update",     "data": crowd_sim.tick()})

            if tick % 2 == 0 and transport_opt:

                await broadcast({"type": "transport:update", "data": transport_opt.tick()})

            if tick % 3 == 0 and crowd_sim and transport_opt and incident_mgr:

                await broadcast({"type": "kpi:snapshot", "data": {

                    "crowd":     crowd_sim.get_kpis(),

                    "transport": transport_opt.get_kpis(),

                    "incidents": incident_mgr.get_kpis(),

                }})

        except Exception as e:

            log.error("Broadcast loop error: %s", e)





# ── Global exception handler ──────────────────────────────────────────

@app.exception_handler(Exception)

async def global_exception_handler(request: Request, exc: Exception):

    log.error("Unhandled error: %s", exc, exc_info=True)

    return JSONResponse(status_code=500, content={"error": str(exc), "type": type(exc).__name__})

