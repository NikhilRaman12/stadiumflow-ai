# ⚡ StadiumIQ — FIFA World Cup 2026 GenAI Platform

<div align="center">

![StadiumIQ](https://img.shields.io/badge/StadiumIQ-FIFA%20WC%202026-00d4ff?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMiAyQzYuNDggMiAyIDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAxMiAyem0wIDE4Yy00LjQxIDAtOC0zLjU5LTgtOHMzLjU5LTggOC04IDggMy41OSA4IDgtMy41OSA4LTggOHoiLz48L3N2Zz4=)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-00d4ff?style=for-the-badge)
![Gemini](https://img.shields.io/badge/Gemini-1.5%20Pro-4285F4?style=for-the-badge&logo=google)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi)

**Enterprise GenAI platform for stadium operations and fan experience at FIFA World Cup 2026**

[🏟️ Fan App](#fan-app) · [🖥️ Ops Dashboard](#ops-dashboard) · [📡 API Docs](#api) · [🚀 Deploy](#deploy)

</div>

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    StadiumIQ GenAI Platform                       │
├─────────────────────────────────────────────────────────────────┤
│  FRONTEND                                                         │
│  ┌─────────────────┐  ┌─────────────────────────────────────┐   │
│  │  Fan App (PWA)  │  │    Ops Command Dashboard              │   │
│  │  fan-app.html   │  │    ops-dashboard.html                 │   │
│  │  ARIA Chat      │  │    CrowdSense · Incidents · Staff      │   │
│  │  EcoScore       │  │    Transport · Agents · Analytics     │   │
│  └─────────────────┘  └─────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  FASTAPI BACKEND  (Python 3.12 · uvicorn · WebSocket)            │
│                                                                   │
│  ┌── LangGraph StateGraph Agents ──────────────────────────┐     │
│  │  🤖 FanAssistant   🧠 CrowdSense   🚨 IncidentGuard     │     │
│  │  🚌 FlowRoute      🌱 EcoScore     ⚡ OpsCommand (Sup.) │     │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌── GraphRAG ──────┐  ┌── MCP Servers ────────────────┐        │
│  │ NetworkX DiGraph  │  │ Stadium · Crowd               │        │
│  │ FAISS Vector Index│  │ Transport · Eco               │        │
│  └──────────────────┘  └───────────────────────────────┘        │
│                                                                   │
│  ┌── A2A Protocol ─────────────────────────────────────────┐     │
│  │  Agent Cards · Task/Message Schema · HTTP Agent Bus      │     │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌── LLM ──────────────────────────────────────────────────┐     │
│  │  Google Gemini 1.5 Pro via LangChain · langchain-google  │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## 🌟 Key Features

| Module | Technology | Capability |
|--------|-----------|------------|
| **ARIA** | Gemini 1.5 Pro + LangGraph | Multilingual fan assistant (32 languages) |
| **CrowdSense** | LangGraph StateGraph + MCP | Real-time density analysis + bottleneck prediction |
| **IncidentGuard** | LangGraph + Gemini | AI incident classification + response protocols |
| **FlowRoute** | LangGraph + Transport MCP | Transport load balancing + dispersal planning |
| **EcoScore** | LangGraph + CO₂ factors | Carbon footprint + sustainability gamification |
| **OpsCommand** | LangGraph Supervisor + A2A | Agent orchestration + staff deployment |
| **GraphRAG** | NetworkX + FAISS | 250+ node stadium knowledge graph + semantic search |
| **MCP Servers** | 4 tool servers | Structured tools for Stadium, Crowd, Transport, Eco |
| **A2A Protocol** | FastAPI + Pydantic | Google Agent-to-Agent spec with Agent Cards |
| **WebSocket** | FastAPI WS | Real-time crowd/transport/incident broadcasts |

## 📁 Project Structure

```
stadiumiq/
├── backend/                        # Python FastAPI backend
│   ├── main.py                     # FastAPI app + WebSocket + lifespan
│   ├── requirements.txt            # All Python dependencies
│   ├── .env.example                # Environment template
│   ├── Dockerfile                  # Production container
│   ├── agents/                     # LangGraph StateGraph agents
│   │   ├── base_agent.py           # Shared utilities, LLM, simulation
│   │   ├── fan_agent.py            # FanAssistantGraph (4 nodes)
│   │   ├── crowd_agent.py          # CrowdIntelligenceGraph (5 nodes)
│   │   ├── incident_agent.py       # IncidentResponseGraph (4 nodes)
│   │   ├── transport_agent.py      # TransportOptimizerGraph (4 nodes)
│   │   ├── eco_agent.py            # EcoScoringGraph (4 nodes)
│   │   └── ops_agent.py            # OpsCommandGraph (Supervisor + A2A)
│   ├── graph_rag/                  # GraphRAG pipeline
│   │   ├── graph_builder.py        # NetworkX KG builder
│   │   └── graph_retriever.py      # FAISS + BFS retrieval
│   ├── mcp/                        # Model Context Protocol servers
│   │   └── stadium_server.py       # Stadium, Crowd, Transport, Eco MCPs
│   ├── a2a/                        # Agent-to-Agent protocol
│   │   ├── agent_cards.py          # 6 Agent Card definitions
│   │   └── a2a_server.py           # A2A HTTP router + handlers
│   ├── api/                        # REST API routes
│   │   ├── chat.py                 # POST /api/chat
│   │   ├── crowd.py                # /api/crowd
│   │   ├── incidents.py            # /api/incidents
│   │   ├── transport.py            # /api/transport
│   │   ├── eco.py                  # /api/eco
│   │   └── analytics.py            # /api/analytics
│   ├── services/                   # Simulation services
│   │   └── crowd_simulator.py      # CrowdSim + TransportOpt + IncidentMgr
│   └── data/                       # Seed data
│       ├── stadiums.json           # 6 venue definitions for GraphRAG
│       └── matches.json            # WC2026 match schedule
├── frontend/                       # Static web frontends
│   ├── index.html                  # Landing page
│   ├── fan-app.html                # Fan PWA (5 pages)
│   ├── ops-dashboard.html          # Ops Command (8 panels)
│   └── css/
│       └── design-system.css       # Global design tokens + components
├── docker-compose.yml
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Google Gemini API key (free at [Google AI Studio](https://aistudio.google.com/app/apikey))

### 1. Clone & Install

```bash
git clone https://github.com/NikhilRaman12/stadiumflow-ai.git
cd stadiumflow-ai
cd backend
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key
```

### 3. Run Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open Frontend

Open any of these in your browser:
- `frontend/index.html` — Landing page
- `frontend/fan-app.html` — Fan PWA
- `frontend/ops-dashboard.html` — Operations Command
- Or visit `http://localhost:8000` if serving via FastAPI

### 5. Set API Key in UI

Click ⚙️ Settings (Fan App) or the key icon (Ops Dashboard) and enter your Gemini API key. Works **without a key** in demo/simulation mode.

## 📡 API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Platform status + agent health |
| `/api/chat` | POST | ARIA AI chat (fan/ops modes) |
| `/api/crowd/{venue_id}` | GET | Live crowd density |
| `/api/crowd/{venue_id}/analyze` | POST | AI crowd analysis |
| `/api/incidents` | POST | Report + AI-assess incident |
| `/api/transport/{venue_id}/optimize` | POST | AI transport optimization |
| `/api/eco/score` | POST | Calculate EcoScore + CO₂ |
| `/api/analytics/kpis/{venue_id}` | GET | Live KPI snapshot |
| `/a2a/agents` | GET | A2A Agent Registry (all cards) |
| `/a2a/fan` | POST | A2A task → Fan Agent |
| `/a2a/crowd` | POST | A2A task → Crowd Agent |
| `/a2a/incident` | POST | A2A task → Incident Agent |
| `/a2a/ops` | POST | A2A task → OpsCommand |
| `/ws` | WebSocket | Real-time event stream |
| `/api/docs` | GET | Swagger UI |

## 🤖 LangGraph Agents

Each agent is a compiled `StateGraph` with:
- **GraphRAG retrieval** at every query for knowledge-grounded responses
- **MCP tool calls** for structured real-time data
- **A2A protocol** for inter-agent communication
- **Gemini 1.5 Pro** for reasoning (with simulation fallback)
- **MemorySaver** checkpointing for conversation continuity

```python
# Example: Invoke Fan Agent
config = {"configurable": {"thread_id": "fan_session_123"}}
result = await fan_graph.ainvoke({
    "user_query": "Where is the accessible entrance?",
    "venue_id": "met",
    ...
}, config=config)
print(result["response"])  # ARIA's multilingual response
```

## 🏟️ Supported Venues (FIFA WC 2026)

| ID | Venue | City | Capacity |
|----|-------|------|----------|
| `met` | MetLife Stadium | New York/NJ | 82,500 |
| `dal` | AT&T Stadium | Dallas, TX | 80,000 |
| `la` | SoFi Stadium | Los Angeles | 70,240 |
| `atz` | Estadio Azteca | Mexico City | 87,523 |
| `bc` | BC Place | Vancouver | 54,000 |
| `sf` | Levi's Stadium | Santa Clara | 68,500 |

## 🐳 Deploy with Docker

```bash
cp backend/.env.example backend/.env
# Set GEMINI_API_KEY in .env

docker-compose up -d
```

Access: `http://localhost` (Fan App) · `http://localhost:8000/api/docs` (API)

## 🌱 Sustainability

StadiumIQ tracks real-time sustainability metrics:
- **CO₂ calculations** per transport mode (metro vs car vs flight)
- **EcoScore** gamification (0-100 + EcoPoints rewards)
- **Venue sustainability stats**: solar, waste diversion, water savings
- **SDG alignment**: SDG 11 (Sustainable Cities), SDG 13 (Climate Action)

## 📝 License

MIT License — Built for FIFA World Cup 2026 GenAI Challenge

---

<div align="center">
Built with ❤️ using <strong>LangChain · LangGraph · Gemini · FastAPI · GraphRAG · MCP · A2A</strong>
</div>
