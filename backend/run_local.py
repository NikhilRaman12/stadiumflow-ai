"""
StadiumIQ -- Slim Local Runner
==============================
Lightweight FastAPI server that works with or without all heavy deps.
Serves the frontend and provides functional API endpoints.
Run: python run_local.py
"""
import sys, io, os, json, random, uuid, asyncio, logging
# Force UTF-8 output on Windows to avoid cp1252 emoji encoding errors
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Prevent langchain-google-genai from fighting over which key to use
# We always use GEMINI_API_KEY; unset GOOGLE_API_KEY if both are set
if os.environ.get('GOOGLE_API_KEY') and os.environ.get('GEMINI_API_KEY'):
    del os.environ['GOOGLE_API_KEY']

from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# ── Optional heavy deps ──────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
    from pydantic import BaseModel, Field
    FASTAPI_OK = True
except ImportError:
    print("ERROR: FastAPI not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

# Optional Gemini (using new google.genai SDK)
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if GEMINI_API_KEY:
        _genai_client = google_genai.Client(api_key=GEMINI_API_KEY)
        GEMINI_OK = True
        print("[OK] Gemini 2.0 Flash connected")
    else:
        _genai_client = None
        GEMINI_OK = False
        print("[INFO] No GEMINI_API_KEY -- running in demo mode (add key to backend/.env)")
except ImportError:
    _genai_client = None
    GEMINI_OK = False
    print("[INFO] google-genai not installed -- demo mode active")

# Optional LangGraph
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_OK = True
    print("[OK] LangGraph available")
except ImportError:
    LANGGRAPH_OK = False
    print("[INFO] LangGraph not installed -- install deps for full agent mode")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
log = logging.getLogger("stadiumiq")

# ── Data ─────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
def load_json(f):
    p = DATA_DIR / f
    return json.load(open(p)) if p.exists() else []

STADIUMS = load_json("stadiums.json")
MATCHES  = load_json("matches.json")
STADIUM_MAP = {s["id"]: s for s in STADIUMS}

connected_ws: list[WebSocket] = []

# ── Simulated Responses ───────────────────────────────────────────
SIM_RESPONSES = {
    "navigation":     "🎯 **Navigation Guide**\nFollow the colored floor pathways from your entry gate. Check your ticket QR code for Gate → Section → Row → Seat. Staff stationed at every junction! Average walk to seat: 3-5 min.",
    "crowd":          "👥 **Crowd Status**\n🟢 Level 2 Concourse: 44% (Low)\n🟡 Gate D: 78% (Medium-High)\n🔴 Field Level: 91% (Critical)\n\n💡 Recommendation: Use Gate E concourse (38% load) for quicker movement.",
    "food":           "🍔 **Food & Queues**\n✅ Level 2 Concessions: **4 min** wait\n⚠️  Level 1 Concessions: **9 min** wait\n✅ Section 12 Restrooms: **3 min** wait\n\n🌱 Eco tip: Veggie burger saves 2.7kg CO₂ vs beef!",
    "transport":      "🚌 **Transport Options**\n🚇 Metro Line 3: **12 min** wait · 68% load ✅\n🚌 Shuttle Zone C: **6 min** wait · 42% load ✅\n🚗 Parking Zone A: **95%** full ❌ → use Zone D (22% ✅)\n🚕 Taxi: 2.1× surge · 28 min wait",
    "accessibility":  "♿ **Accessibility Guide**\nMain accessible entry: **Gate A** (level ramp + lift)\nWheelchair seats: **Section F, Rows 1-2** · Companion seats included\nLifts: A1, A2, B1 ✅ · B3 under maintenance ⚠️\nNeed escort? Blue button at Gate A · 15 min response.",
    "eco":            "🌱 **Your EcoScore**\nFootprint today: ~7.1kg CO₂\n⭐ EcoScore: 72/100 · 36 EcoPoints earned!\nMetro travel saved 4.2kg CO₂ vs driving\n\n🏟️ Stadium today: 78% waste diverted · 4.2MWh solar",
    "emergency":      "🚨 **EMERGENCY**\nNearest First Aid: **Gate B entrance** (2 min)\nCall 911 or press **RED button** on any column\nAED defibrillators every 100m on concourse\nSecurity: press the **orange button** at your section entrance",
    "operations":     "⚡ **OPS SUMMARY** | Risk: HIGH\nField Level 91% - CRITICAL → restrict entry\nGate D 82% - HIGH → deploy 3 stewards\nOpen incidents: 3 (1 medical, 1 security, 1 crowd)\nRecommendation: Activate post-match transport now (match ends T-23min)",
    "general":        "👋 **Hi! I'm ARIA** - your FIFA WC 2026 AI assistant.\n\nI can help with:\n🎯 Navigation & seating\n🍔 Food queues & services\n♿ Accessibility routes\n🚌 Transport options\n🌱 EcoScore & sustainability\n🚨 Emergency assistance\n\nAdd your Gemini API key in ⚙️ Settings for full AI in 32 languages!",
}

def get_intent(q: str) -> str:
    q = q.lower()
    if any(w in q for w in ["seat","section","gate","where","navigate","find","row"]): return "navigation"
    if any(w in q for w in ["crowd","busy","dense","flow","capacity"]): return "crowd"
    if any(w in q for w in ["food","eat","queue","concession","burger","drink","wait"]): return "food"
    if any(w in q for w in ["bus","metro","train","parking","transport","shuttle","taxi","ride","car"]): return "transport"
    if any(w in q for w in ["wheelchair","accessible","disability","ramp","lift","elevator","accessible"]): return "accessibility"
    if any(w in q for w in ["eco","carbon","green","environment","sustainability","footprint","co2"]): return "eco"
    if any(w in q for w in ["emergency","medical","sick","hurt","injured","help","danger","fire","lost","sos"]): return "emergency"
    if any(w in q for w in ["incident","staff","deploy","steward","security","ops","operation"]): return "operations"
    return "general"

async def ai_chat(message: str, venue_id: str = "met", role: str = "fan") -> str:
    intent = get_intent(message)
    if GEMINI_OK and _genai_client:
        venue = STADIUM_MAP.get(venue_id, {})
        prompt = (
            f"You are ARIA, the official AI assistant for FIFA World Cup 2026 at {venue.get('name','Stadium')}.\n"
            f"Be helpful, concise, safety-first. Auto-detect language and reply in same language.\n"
            f"Use emojis for readability. Keep response under 150 words unless complex routing needed.\n"
            f"Intent: {intent}\n\nUser: {message}"
        )
        try:
            resp = await asyncio.to_thread(
                _genai_client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt
            )
            return resp.text
        except Exception as e:
            log.error("Gemini error: %s", e)
    return SIM_RESPONSES.get(intent, SIM_RESPONSES["general"])

# ── Crowd simulation state ────────────────────────────────────────
crowd_state = {
    v["id"]: {
        "zones": {z: {"density": random.randint(30,75), "flow": random.randint(200,700)}
                  for z in ["north","south","east","west","field","upper","concourse"]}
    } for v in STADIUMS
}

def tick_crowd():
    for vid in crowd_state:
        for zone in crowd_state[vid]["zones"]:
            d = crowd_state[vid]["zones"][zone]["density"]
            crowd_state[vid]["zones"][zone]["density"] = max(10, min(100, d + random.randint(-4,6)))
            crowd_state[vid]["zones"][zone]["flow"] = random.randint(100,900)

# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    log.info("StadiumIQ Local Server starting...")
    asyncio.create_task(broadcast_loop())
    log.info("StadiumIQ ready at http://localhost:8000")
    log.info("Fan App :  http://localhost:8000/fan")
    log.info("Ops Dash:  http://localhost:8000/ops")
    log.info("API Docs:  http://localhost:8000/api/docs")
    yield
    log.info("Shutting down...")

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="StadiumIQ GenAI Platform",
    description="FIFA World Cup 2026 - LangGraph · MCP · A2A · GraphRAG · Gemini",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Serve frontend ────────────────────────────────────────────────
FRONTEND = Path(__file__).parent / "frontend" if (Path(__file__).parent / "frontend").exists() else Path(__file__).parent.parent / "frontend"

@app.get("/")
async def root():
    idx = FRONTEND / "index.html"
    return FileResponse(str(idx)) if idx.exists() else JSONResponse({"message":"StadiumIQ API - /api/docs"})

@app.get("/fan")
async def fan_app():
    f = FRONTEND / "fan-app.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"fan-app.html not found"})

@app.get("/ops")
async def ops_dash():
    f = FRONTEND / "ops-dashboard.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"ops-dashboard.html not found"})

# Serve static assets (CSS, JS, images)
if (FRONTEND / "css").exists():
    app.mount("/css",    StaticFiles(directory=str(FRONTEND/"css")),    name="css")
if (FRONTEND / "js").exists():
    app.mount("/js",     StaticFiles(directory=str(FRONTEND/"js")),     name="js")
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND/"assets")), name="assets")

# ── REST API ──────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "operational",
        "platform": "StadiumIQ - FIFA World Cup 2026",
        "version": "2.0.0",
        "mode": "live_ai" if GEMINI_OK else "demo",
        "architecture": {
            "llm":       "Gemini 2.0 Flash" if GEMINI_OK else "Demo (no key)",
            "agents":    "LangGraph StateGraph" if LANGGRAPH_OK else "Simulated",
            "retrieval": "GraphRAG (NetworkX + FAISS)",
            "tools":     "MCP Protocol (4 servers)",
            "comms":     "A2A Agent-to-Agent Protocol",
        },
        "services": {
            "gemini":    "connected" if GEMINI_OK else "demo_mode",
            "langgraph": "active"    if LANGGRAPH_OK else "simulated",
            "websocket": f"{len(connected_ws)} clients",
            "venues":    len(STADIUMS),
            "matches":   len(MATCHES),
        },
        "urls": {
            "fan_app":   "http://localhost:8000/fan",
            "ops_dash":  "http://localhost:8000/ops",
            "api_docs":  "http://localhost:8000/api/docs",
            "websocket": "ws://localhost:8000/ws",
        }
    }

class ChatRequest(BaseModel):
    message:    str
    session_id: str  = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id:   str  = "met"
    role:       str  = "fan"
    context:    dict = Field(default_factory=dict)

@app.post("/api/chat")
async def chat(body: ChatRequest):
    response = await ai_chat(body.message, body.venue_id, body.role)
    return {
        "response":   response,
        "session_id": body.session_id,
        "agent_id":   "fan-assistant-agent" if body.role == "fan" else "ops-command-agent",
        "intent":     get_intent(body.message),
        "simulated":  not GEMINI_OK,
        "mode":       "live_ai" if GEMINI_OK else "demo",
    }

@app.get("/api/crowd/{venue_id}")
async def get_crowd(venue_id: str):
    state = crowd_state.get(venue_id, {})
    zones = state.get("zones", {})
    densities = [v["density"] for v in zones.values()]
    avg = round(sum(densities)/len(densities), 1) if densities else 50
    risk = "LOW" if avg<50 else "MEDIUM" if avg<75 else "HIGH" if avg<90 else "CRITICAL"
    return {"venue_id":venue_id, "zones":zones, "avg_density":avg, "risk_level":risk, "ts":datetime.utcnow().isoformat()}

@app.get("/api/crowd/{venue_id}/predictions")
async def crowd_predictions(venue_id: str):
    zones = crowd_state.get(venue_id, {}).get("zones", {})
    preds = [{"zone":z,"current_density":v["density"],"predicted_density":min(100,v["density"]+random.randint(2,12)),"severity":"HIGH" if v["density"]>75 else "MEDIUM" if v["density"]>50 else "LOW","recommendation":"Redirect via alternate gate" if v["density"]>75 else "Monitor"} for z,v in zones.items()]
    return {"venue_id":venue_id,"predictions":sorted(preds,key=lambda x:-x["current_density"]),"generated_at":datetime.utcnow().isoformat()}

class IncidentReport(BaseModel):
    description: str
    location:    str
    venue_id:    str = "met"
    severity_hint: int = 3

_incidents: list[dict] = []

@app.post("/api/incidents")
async def report_incident(body: IncidentReport):
    iid = str(uuid.uuid4())[:8].upper()
    ai_assessment = await ai_chat(f"[OPS] Assess incident: {body.description} at {body.location}. Severity estimate 1-5, recommend response.", body.venue_id, "ops")
    inc = {"id":iid,"description":body.description,"location":body.location,"venue_id":body.venue_id,"status":"OPEN","severity":body.severity_hint,"ai_assessment":ai_assessment,"created_at":datetime.utcnow().isoformat()}
    _incidents.append(inc)
    await broadcast({"type":"incident:new","data":inc})
    return inc

@app.get("/api/incidents/{venue_id}")
async def list_incidents(venue_id: str):
    active = [i for i in _incidents if i["venue_id"]==venue_id and i["status"]=="OPEN"]
    return {"incidents":active,"count":len(active),"venue_id":venue_id}

@app.get("/api/transport/{venue_id}/status")
async def transport_status(venue_id: str):
    return {"venue_id":venue_id,"shuttle":{"wait_min":random.randint(4,18),"load_pct":random.randint(30,85),"zones":["A","B","C","D"]},"metro":{"wait_min":random.randint(5,20),"load_pct":random.randint(40,95),"lines":["Line 1","Line 2","Line 3"]},"parking":{"zone_a":random.randint(70,100),"zone_b":random.randint(40,80),"zone_c":random.randint(20,60),"zone_d":random.randint(5,40)},"taxi_surge":round(random.uniform(1.0,3.5),1),"ts":datetime.utcnow().isoformat()}

class EcoQuery(BaseModel):
    travel_mode: str = "metro"
    travel_distance: float = 25.0
    group_size: int = 1
    food_choices: list = ["local_food"]
    venue_id: str = "met"

@app.post("/api/eco/score")
async def eco_score(body: EcoQuery):
    factors = {"metro":0.041,"bus":0.089,"car_petrol":0.171,"walk":0.0,"bike":0.0,"shuttle":0.072,"taxi":0.158,"flight":0.255}
    co2 = factors.get(body.travel_mode,0.1)*body.travel_distance
    food_co2 = sum({"beef_burger":3.5,"veggie_burger":0.8,"chicken":2.1,"local_food":1.2,"snacks":0.3}.get(f,1.0) for f in body.food_choices)
    total = round(co2+food_co2,2)
    score = max(0,int(100-(total/20)*100))
    advice = await ai_chat(f"Give eco advice for: transport={body.travel_mode}, distance={body.travel_distance}km, CO2={total}kg, EcoScore={score}/100. Keep it brief and encouraging.",body.venue_id,"fan")
    return {"co2_kg":total,"eco_score":score,"eco_points":score//2,"travel_co2":round(co2,2),"food_co2":round(food_co2,2),"advice":advice}

@app.get("/api/analytics/kpis/{venue_id}")
async def kpis(venue_id: str):
    zones = crowd_state.get(venue_id,{}).get("zones",{})
    densities = [v["density"] for v in zones.values()]
    avg = round(sum(densities)/len(densities),1) if densities else 50
    return {"venue_id":venue_id,"crowd":{"avg_density_pct":avg,"risk_level":"HIGH" if avg>75 else "MEDIUM" if avg>50 else "LOW","total_fans":random.randint(50000,85000)},"transport":{"shuttle_wait":random.randint(5,18),"metro_wait":random.randint(5,20),"parking_d_pct":random.randint(15,40)},"incidents":{"open":len([i for i in _incidents if i["status"]=="OPEN"]),"total":len(_incidents)},"eco":{"avg_eco_score":random.randint(55,80),"co2_saved_kg":random.randint(800,2500)},"aria":{"chats_today":random.randint(3000,9000),"languages_active":random.randint(12,28)}}

@app.get("/api/analytics/summary")
async def summary():
    return {"platform":"StadiumIQ - FIFA World Cup 2026","venues":len(STADIUMS),"matches":len(MATCHES),"agents":6,"mcp_servers":4,"mode":"live_ai" if GEMINI_OK else "demo","langgraph":LANGGRAPH_OK,"graphrag":True,"a2a":True}

@app.get("/api/venues")
async def venues():
    return {"venues":STADIUMS,"count":len(STADIUMS)}

@app.get("/api/matches")
async def matches():
    return {"matches":MATCHES,"count":len(MATCHES)}

# A2A agent discovery
@app.get("/a2a/agents")
async def a2a_agents():
    agents = [{"agent_id":a,"name":n,"endpoint":f"http://localhost:8000/a2a/{a.split('-')[0]}","status":"active"}
              for a,n in [("fan-assistant-agent","ARIA Fan Assistant"),("crowd-intelligence-agent","CrowdSense"),("incident-response-agent","IncidentGuard"),("transport-optimizer-agent","FlowRoute"),("eco-scoring-agent","EcoScore"),("ops-command-agent","OpsCommand")]]
    return {"agents":agents,"count":len(agents),"protocol":"A2A/1.0"}

@app.post("/a2a/{agent}")
async def a2a_call(agent: str, request: Request):
    body = await request.json()
    msg = body.get("message",{}).get("content","")
    ctx = body.get("context",{})
    resp = await ai_chat(msg, ctx.get("venue_id","met"), "ops" if agent=="ops" else "fan")
    return {"task_id":body.get("task_id",str(uuid.uuid4())),"agent_id":f"{agent}-agent","status":"completed","message":{"role":"agent","content":resp}}

# ── WebSocket ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    connected_ws.append(ws)
    log.info("WS connected - total: %d", len(connected_ws))
    try:
        await ws.send_json({"type":"welcome","data":{"platform":"StadiumIQ","mode":"live_ai" if GEMINI_OK else "demo","venues":len(STADIUMS)}})
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type":"pong"})
    except WebSocketDisconnect:
        connected_ws.remove(ws) if ws in connected_ws else None

async def broadcast(payload: dict):
    dead = []
    for ws in list(connected_ws):
        try: await ws.send_json(payload)
        except: dead.append(ws)
    for ws in dead:
        if ws in connected_ws: connected_ws.remove(ws)

async def broadcast_loop():
    tick = 0
    while True:
        await asyncio.sleep(8)
        tick += 1
        tick_crowd()
        if connected_ws:
            await broadcast({"type":"crowd:update","data":{v:crowd_state[v] for v in list(crowd_state)[:2]},"tick":tick})
            if tick % 3 == 0:
                await broadcast({"type":"kpi:snapshot","data":{"tick":tick,"venues":len(STADIUMS),"incidents_open":len([i for i in _incidents if i["status"]=="OPEN"]),"ws_clients":len(connected_ws)}})

# ── Entry ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print("\n" + "="*55)
    print("  StadiumIQ -- FIFA World Cup 2026 GenAI Platform")
    print("="*55)
    print(f"  Fan App :  http://localhost:{port}/fan")
    print(f"  Ops Dash:  http://localhost:{port}/ops")
    print(f"  API Docs:  http://localhost:{port}/api/docs")
    print(f"  Health  :  http://localhost:{port}/api/health")
    print(f"  AI Mode :  {'LIVE (Gemini 2.0 Flash)' if GEMINI_OK else 'DEMO (add GEMINI_API_KEY to .env)'}")
    print("="*55 + "\n")
    # NOTE: reload=False is critical - reload=True spawns a reloader process
    # AND a worker process, both binding the same port, causing 502s via ngrok.
    uvicorn.run(
        "run_local:app",
        host=host,
        port=port,
        reload=False,      # <-- MUST be False for stable single-process operation
        log_level="info",
        access_log=True,
    )

