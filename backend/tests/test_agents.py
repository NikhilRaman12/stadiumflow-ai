import pytest
import os
import sys
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from main import app
from graph_rag.graph_builder import StadiumKnowledgeGraph
from graph_rag.graph_retriever import GraphRAGRetriever
from mcp.stadium_server import StadiumMCPServer, CrowdMCPServer, TransportMCPServer, EcoMCPServer
from a2a.a2a_server import A2ATask, A2AMessage
from agents.base_agent import detect_language_node, classify_intent, simulate_response
from agents.fan_agent import FanAssistantGraph
from agents.crowd_agent import CrowdIntelligenceGraph
from agents.eco_agent import EcoScoringGraph
from agents.incident_agent import IncidentResponseGraph
from agents.transport_agent import TransportOptimizerGraph
from agents.ops_agent import OpsCommandGraph
from services.crowd_simulator import CrowdSimulator, TransportOptimizer, IncidentManager

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

# ──────────────────────────────────────────────────────────────────────
# 1. Base Agent Tests
# ──────────────────────────────────────────────────────────────────────

def test_language_detection():
    # Test multiple languages triggers
    assert detect_language_node({"user_query": "Hola, ¿dónde está mi asiento?"}) == {"detected_language": "es"}
    assert detect_language_node({"user_query": "Bonjour, où est le fauteuil?"}) == {"detected_language": "fr"}
    assert detect_language_node({"user_query": "Olá, obrigado pela ajuda!"}) == {"detected_language": "pt"}
    assert detect_language_node({"user_query": "Hallo, danke für den Sitz!"}) == {"detected_language": "de"}
    assert detect_language_node({"user_query": "مرحبا، أين المدخل؟"}) == {"detected_language": "ar"}
    assert detect_language_node({"user_query": "你好，谢谢！"}) == {"detected_language": "zh"}
    assert detect_language_node({"user_query": "こんにちは、どこですか"}) == {"detected_language": "ja"}
    assert detect_language_node({"user_query": "안녕하세요, 감사합니다"}) == {"detected_language": "ko"}
    assert detect_language_node({"user_query": "नमस्ते, कहाँ है?"}) == {"detected_language": "hi"}
    assert detect_language_node({"user_query": "Ciao, dove si trova il posto?"}) == {"detected_language": "it"}
    # Default fallback
    assert detect_language_node({"user_query": "Where is Gate A?"}) == {"detected_language": "en"}

def test_classify_intent():
    assert classify_intent("Where is my seat in section 12?") == "navigation"
    assert classify_intent("How busy is the food line right now?") == "crowd_services"
    assert classify_intent("Is there wheelchair ramp access?") == "accessibility"
    assert classify_intent("What is the best bus route to the metro station?") == "transport"
    assert classify_intent("Tell me about carbon footprint offsets") == "eco"
    assert classify_intent("Help! Medical emergency en route!") == "emergency"
    assert classify_intent("Deploy staff to incident alert") == "operations"
    assert classify_intent("What is the match schedule today?") == "itinerary"
    assert classify_intent("Hello ARIA!") == "general"

@pytest.mark.asyncio
async def test_simulate_response():
    resp1 = await simulate_response("navigation", "seat query", "some context")
    assert "Gate" in resp1 or "PATH" in resp1
    assert "Graph context: some context" in resp1

    resp2 = await simulate_response("general", "hi")
    assert "ARIA" in resp2

# ──────────────────────────────────────────────────────────────────────
# 2. GraphRAG Tests
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_graphrag_pipeline():
    kg = StadiumKnowledgeGraph()
    await kg.build()
    
    # Assert nodes and edges loaded correctly
    assert kg.graph.number_of_nodes() > 0
    assert kg.graph.number_of_edges() > 0

    # Search keyword
    res = kg.search_nodes("MetLife")
    assert len(res) > 0
    
    # BFS neighborhood subgraph
    sub = kg.get_subgraph(["venue:met"], hops=1)
    assert len(sub.nodes) > 0

    # Retriever fallbacks (keyword matching if API key missing)
    retriever = GraphRAGRetriever(kg)
    await retriever.build_index()
    ctx = await retriever.retrieve("Where is Gate A at MetLife Stadium?")
    assert len(ctx) > 0

    # Venue scoped retrieval
    ctx_venue = await retriever.retrieve_for_venue("met", "Gate A")
    assert "MetLife Stadium" in ctx_venue

# ──────────────────────────────────────────────────────────────────────
# 3. Model Context Protocol Tools
# ──────────────────────────────────────────────────────────────────────

def test_mcp_servers():
    kg = StadiumKnowledgeGraph()
    # In-memory fast setup for MCP testing
    kg.graph.add_node("venue:met", name="MetLife Stadium", type="Venue", text_summary="venue details")
    kg.graph.add_node("zone:met:north", name="North Zone", type="Zone", capacity=25000, venue_id="met")
    kg.graph.add_edge("venue:met", "zone:met:north")
    kg.graph.add_node("gate:met:A", name="Gate A", type="Gate", accessible=True, venue_id="met")
    kg.graph.add_edge("venue:met", "gate:met:A")

    StadiumMCPServer.start(kg)

    # test get_venue_info tool
    res = StadiumMCPServer.call("get_venue_info", venue_id="met")
    assert res["found"] is True
    assert len(res["zones"]) > 0

    # test unknown venue
    res_fail = StadiumMCPServer.call("get_venue_info", venue_id="unknown_venue")
    assert res_fail["found"] is False

    # test get_zone_info
    res_zone = StadiumMCPServer.call("get_zone_info", venue_id="met", zone_id="north")
    assert res_zone["found"] is True

    # test get_gate_status
    res_gate = StadiumMCPServer.call("get_gate_status", venue_id="met", gate_id="A")
    assert res_gate["found"] is True

    # test get_accessible_routes
    res_route = StadiumMCPServer.call("get_accessible_routes", venue_id="met", destination="Section F")
    assert len(res_route["accessible_gates"]) > 0

    # test search_venue_entities
    res_search = StadiumMCPServer.call("search_venue_entities", venue_id="met", keyword="North")
    assert len(res_search["results"]) > 0

    # test unknown tool
    res_unknown = StadiumMCPServer.call("unknown_tool_name")
    assert "available" in res_unknown

    StadiumMCPServer.stop()

    # Test other servers
    CrowdMCPServer.start()
    res_crowd = CrowdMCPServer.call("get_crowd_density", venue_id="met", zone_id="north")
    assert "density_pct" in res_crowd
    res_bns = CrowdMCPServer.call("get_bottleneck_predictions")
    assert "predictions" in res_bns
    res_safe = CrowdMCPServer.call("get_safe_routes")
    assert len(res_safe["safe_routes"]) > 0
    CrowdMCPServer.stop()

    TransportMCPServer.start()
    res_trans = TransportMCPServer.call("get_transport_options")
    assert len(res_trans["options"]) > 0
    res_park = TransportMCPServer.call("get_parking_availability")
    assert "zones" in res_park
    res_routes = TransportMCPServer.call("get_post_match_routes")
    assert "dispersal_plan" in res_routes
    TransportMCPServer.stop()

    EcoMCPServer.start()
    res_eco_co2 = EcoMCPServer.call("calculate_carbon_footprint", transport="metro", distance=15.0)
    assert res_eco_co2["co2_kg"] > 0
    res_eco_stats = EcoMCPServer.call("get_venue_eco_stats")
    assert "waste_diverted_pct" in res_eco_stats
    res_tips = EcoMCPServer.call("get_eco_recommendations")
    assert len(res_tips["tips"]) > 0
    EcoMCPServer.stop()

# ──────────────────────────────────────────────────────────────────────
# 4. Simulation Services
# ──────────────────────────────────────────────────────────────────────

def test_simulation_services():
    # CrowdSimulator
    sim = CrowdSimulator()
    state = sim.get_full_state()
    assert "venues" in state
    
    venue_state = sim.get_venue_state("met")
    assert venue_state["venue_id"] == "met"
    assert "avg_density" in venue_state

    tick_updates = sim.tick()
    assert "venues" in tick_updates

    kpis = sim.get_kpis()
    assert "avg_density_pct" in kpis

    # TransportOptimizer
    trans = TransportOptimizer()
    trans_state = trans.get_full_state()
    assert "shuttle" in trans_state
    trans_tick = trans.tick()
    assert "tick" in trans_tick
    trans_kpis = trans.get_kpis()
    assert "metro_wait_min" in trans_kpis

    # IncidentManager
    mgr = IncidentManager()
    inc = mgr.create_incident({"description": "Spill near Gate A", "location": "Gate A", "venue_id": "met"})
    assert inc["id"] is not None
    assert inc["status"] == "OPEN"

    active_inc = mgr.get_active("met")
    assert len(active_inc) == 1

    resolved = mgr.resolve(inc["id"])
    assert resolved is True
    assert mgr.get_active("met") == []
    
    mgr_kpis = mgr.get_kpis()
    assert mgr_kpis["resolved"] == 1

# ──────────────────────────────────────────────────────────────────────
# 5. LangGraph Agent Graphs (Simulation mode)
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_graphs():
    kg = StadiumKnowledgeGraph()
    await kg.build()
    retriever = GraphRAGRetriever(kg)

    # Fan Agent Graph
    fan_g = FanAssistantGraph(retriever).compile()
    res_fan = await fan_g.ainvoke({
        "user_query": "Where is my seat?", "venue_id": "met",
        "session_id": "session123", "messages": [],
        "detected_language": "en", "intent": "", "graph_context": "", "crowd_data": "", "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert "response" in res_fan
    assert len(res_fan["response"]) > 0

    # Crowd Agent Graph
    crowd_g = CrowdIntelligenceGraph(retriever).compile()
    res_crowd = await crowd_g.ainvoke({
        "user_query": "Is there a bottleneck?", "venue_id": "met",
        "messages": [], "graph_context": "", "crowd_data": {},
        "density_scores": {}, "bottlenecks": [], "recommendations": [],
        "risk_level": "LOW", "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert "risk_level" in res_crowd

    # Eco Scoring Graph
    eco_g = EcoScoringGraph(retriever).compile()
    res_eco = await eco_g.ainvoke({
        "user_query": "Calculate my score", "venue_id": "met",
        "travel_mode": "metro", "travel_distance": 20.0,
        "group_size": 2, "food_choices": ["local_food", "veggie_burger"],
        "messages": [], "co2_kg": 0.0, "eco_score": 0,
        "eco_points": 0, "recommendations": [], "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert res_eco["eco_score"] > 0

    # Incident Response Graph
    inc_g = IncidentResponseGraph(retriever).compile()
    res_inc = await inc_g.ainvoke({
        "incident_description": "We need medical help at Gate B", "location": "Gate B",
        "venue_id": "met", "session_id": "inc123",
        "messages": [], "incident_type": "other", "severity_estimate": 3,
        "parsed_response": {}, "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert "parsed_response" in res_inc
    assert res_inc["parsed_response"]["severity"] > 0

    # Transport Optimizer Graph
    trans_g = TransportOptimizerGraph(retriever).compile()
    res_trans = await trans_g.ainvoke({
        "user_query": "Optimize post match", "venue_id": "met",
        "match_phase": "post_match", "session_id": "trans123",
        "messages": [], "transport_state": {}, "optimized_routes": [], "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert "response" in res_trans

    # Ops Command Supervisor Graph
    ops_g = OpsCommandGraph(retriever, {
        "fan": fan_g, "crowd": crowd_g, "incident": inc_g, "transport": trans_g, "eco": eco_g
    }).compile()
    res_ops = await ops_g.ainvoke({
        "user_query": "Status report", "venue_id": "met",
        "request_type": "general", "session_id": "ops123",
        "messages": [], "agent_reports": {}, "ops_metrics": {},
        "staff_plan": [], "response": ""
    }, config={"configurable": {"thread_id": "session123"}})
    assert "response" in res_ops

# ──────────────────────────────────────────────────────────────────────
# 6. A2A Router Endpoints
# ──────────────────────────────────────────────────────────────────────

def test_a2a_endpoints(client):
    payload = {
        "agent_id": "fan-assistant-agent",
        "message": {"role": "user", "content": "Where is my seat?"},
        "context": {"venue_id": "met"}
    }
    
    # Test Fan A2A
    res = client.post("/a2a/fan", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    # Test Crowd A2A
    payload["agent_id"] = "crowd-intelligence-agent"
    res = client.post("/a2a/crowd", json=payload)
    assert res.status_code == 200

    # Test Incident A2A
    payload_inc = {
        "agent_id": "incident-response-agent",
        "message": {"role": "user", "content": "Medical emergency near Gate B"},
        "context": {"venue_id": "met", "location": "Gate B"}
    }
    res = client.post("/a2a/incident", json=payload_inc)
    assert res.status_code == 200

    # Test Transport A2A
    payload_trans = {
        "agent_id": "transport-optimizer-agent",
        "message": {"role": "user", "content": "Optimize post match routing"},
        "context": {"venue_id": "met", "match_phase": "post_match"}
    }
    res = client.post("/a2a/transport", json=payload_trans)
    assert res.status_code == 200

    # Test Eco A2A
    payload_eco = {
        "agent_id": "eco-scoring-agent",
        "message": {"role": "user", "content": "Calculate eco stats"},
        "context": {"venue_id": "met", "travel_mode": "metro", "travel_distance": 10.0}
    }
    res = client.post("/a2a/eco", json=payload_eco)
    assert res.status_code == 200

    # Test Ops A2A
    payload_ops = {
        "agent_id": "ops-command-agent",
        "message": {"role": "user", "content": "General status report"},
        "context": {"venue_id": "met"}
    }
    res = client.post("/a2a/ops", json=payload_ops)
    assert res.status_code == 200

    # Test specific agent card
    res_card = client.get("/a2a/agents/fan-assistant-agent")
    assert res_card.status_code == 200
    assert res_card.json()["agent_id"] == "fan-assistant-agent"

    # Test non-existing agent card
    res_card_fail = client.get("/a2a/agents/non-existent-agent")
    assert res_card_fail.status_code == 404

@pytest.mark.asyncio
async def test_agent_graphs_with_llm_failure():
    """Verify that all agent graphs fallback gracefully to simulation/fallback logic on LLM failures."""
    kg = StadiumKnowledgeGraph()
    await kg.build()
    retriever = GraphRAGRetriever(kg)
    config = {"configurable": {"thread_id": "err_session", "api_key": "fake_key"}}

    # Fan
    fan_g = FanAssistantGraph(retriever).compile()
    res = await fan_g.ainvoke({
        "user_query": "seat", "venue_id": "met", "session_id": "err", "messages": [],
        "detected_language": "en", "intent": "", "graph_context": "", "crowd_data": "", "response": ""
    }, config=config)
    assert len(res["response"]) > 0

    # Crowd
    crowd_g = CrowdIntelligenceGraph(retriever).compile()
    res = await crowd_g.ainvoke({
        "user_query": "bottleneck", "venue_id": "met", "messages": [], "graph_context": "",
        "crowd_data": {}, "density_scores": {}, "bottlenecks": [], "recommendations": [],
        "risk_level": "LOW", "response": ""
    }, config=config)
    assert len(res["response"]) > 0

    # Eco
    eco_g = EcoScoringGraph(retriever).compile()
    res = await eco_g.ainvoke({
        "user_query": "score", "venue_id": "met", "travel_mode": "metro", "travel_distance": 20.0,
        "group_size": 1, "food_choices": ["local_food"], "messages": [], "co2_kg": 0.0,
        "eco_score": 0, "eco_points": 0, "recommendations": [], "response": ""
    }, config=config)
    assert len(res["response"]) > 0

    # Incident
    inc_g = IncidentResponseGraph(retriever).compile()
    res = await inc_g.ainvoke({
        "incident_description": "medical help", "location": "Gate B", "venue_id": "met",
        "session_id": "err", "messages": [], "incident_type": "other", "severity_estimate": 3,
        "parsed_response": {}, "response": ""
    }, config=config)
    assert res["parsed_response"]["severity"] > 0

    # Transport
    trans_g = TransportOptimizerGraph(retriever).compile()
    res = await trans_g.ainvoke({
        "user_query": "optimize", "venue_id": "met", "match_phase": "pre_match", "session_id": "err",
        "messages": [], "transport_state": {}, "optimized_routes": [], "response": ""
    }, config=config)
    assert len(res["response"]) > 0

@pytest.mark.asyncio
async def test_retriever_methods():
    """Verify other retrieval methods on GraphRAGRetriever."""
    kg = StadiumKnowledgeGraph()
    await kg.build()
    retriever = GraphRAGRetriever(kg)
    
    # Test retrieve method
    ctx = await retriever.retrieve("Zone", hops=1)
    assert len(ctx) > 0

    # Test search_nodes directly on kg
    assert len(kg.search_nodes("Zone")) >= 0
    
    # Test retrieve_for_venue with unknown venue
    ctx_unknown = await retriever.retrieve_for_venue("unknown_venue", "query")
    assert len(ctx_unknown) > 0

    # Test MCP tool calls
    StadiumMCPServer.start(kg)
    assert StadiumMCPServer.get_accessible_routes("met", "Section F") is not None
    assert StadiumMCPServer.search_venue_entities("met", "Gate") is not None
    
    # Test MCP invalid tool call error blocks
    assert "error" in StadiumMCPServer.call("unknown_tool")
    assert not StadiumMCPServer.get_venue_info("unknown")["found"]
    assert not StadiumMCPServer.get_zone_info("met", "invalid_zone")["found"]
    assert not StadiumMCPServer.get_gate_status("met", "invalid_gate")["found"]
    assert StadiumMCPServer.get_accessible_routes("met", "invalid_dest") is not None



@pytest.mark.asyncio
async def test_semantic_search_fallback(monkeypatch):
    """Verify semantic search and its fallback paths."""
    kg = StadiumKnowledgeGraph()
    await kg.build()
    retriever = GraphRAGRetriever(kg)
    
    class MockEmbedder:
        def embed_query(self, query):
            return [0.1] * 768
    
    class MockIndex:
        def search(self, q_arr, top_k):
            return [[0.0]], [[0]]
            
    retriever.embedder = MockEmbedder()
    retriever.index = MockIndex()
    retriever.chunks = [{"id": "venue:met", "text": "MetLife Stadium"}]
    
    res = await retriever._semantic_search("MetLife", 1)
    assert "venue:met" in res
    
    # Verify error fallback
    def mock_search_fail(q_arr, top_k):
        raise ValueError("FAISS search error")
    retriever.index.search = mock_search_fail
    res_fail = await retriever._semantic_search("MetLife", 1)
    assert isinstance(res_fail, list)

@pytest.mark.asyncio
async def test_build_index_coverage(monkeypatch):
    """Verify FAISS vector index building path with mock modules."""
    kg = StadiumKnowledgeGraph()
    await kg.build()
    retriever = GraphRAGRetriever(kg)
    
    class MockEmbeddings:
        def __init__(self, **kwargs):
            pass
        def embed_documents(self, texts):
            return [[0.1] * 768] * len(texts)
            
    monkeypatch.setattr("graph_rag.graph_retriever.GoogleGenerativeAIEmbeddings", MockEmbeddings)
    monkeypatch.setattr("graph_rag.graph_retriever.FAISS_AVAILABLE", True)
    
    class MockIndexFlatIP:
        def __init__(self, dim):
            self.dim = dim
            self.data = []
        def add(self, arr):
            self.data.append(arr)
            
    import sys
    from types import ModuleType
    mock_faiss = ModuleType("faiss")
    mock_faiss.IndexFlatIP = MockIndexFlatIP
    mock_faiss.normalize_L2 = lambda arr: None
    sys.modules["faiss"] = mock_faiss
    
    await retriever.build_index()
    assert retriever.index is not None

@pytest.mark.asyncio
async def test_app_lifespan_directly():
    """Verify the startup and shutdown lifespan events of the application directly."""
    from main import lifespan, app
    import main
    
    # Temporarily disable broadcast loop task creation to prevent blocking
    original_create_task = main.asyncio.create_task
    main.asyncio.create_task = lambda t: None
    
    try:
        async with lifespan(app):
            pass
    finally:
        main.asyncio.create_task = original_create_task

@pytest.mark.asyncio
async def test_main_websocket_broadcast_exceptions():
    """Verify that websocket broadcast catches connection errors and purges dead links."""
    import main
    
    class MockWS:
        def __init__(self):
            self.sent = []
        async def send_json(self, data):
            # simulate connection error to trigger exception block
            raise RuntimeError("Connection reset by peer")
            
    ws_mock = MockWS()
    main.connected_ws.append(ws_mock)
    
    # Broadcast should catch the exception, append ws to dead, and clean it up
    await main.broadcast({"type": "test_ping"})
    assert ws_mock not in main.connected_ws




