import pytest
from fastapi.testclient import TestClient
import os
import sys

# Ensure backend directory is in python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from main import app

@pytest.fixture(scope="module")
def client():
    """Context manager fixture that triggers the FastAPI lifespan events (builds GraphRAG, compiles agents)."""
    with TestClient(app) as c:
        yield c

def test_health_check(client):
    """Verify that the health check endpoint returns 200 operational state."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "version" in data
    assert "services" in data

def test_a2a_agents_registered(client):
    """Verify that the A2A router has the 6 specialized agents registered."""
    response = client.get("/a2a/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) == 6
    agent_ids = [agent["agent_id"] for agent in data["agents"]]
    assert "fan-assistant-agent" in agent_ids
    assert "ops-command-agent" in agent_ids

def test_chat_endpoint(client):
    """Verify chat route completes and returns intent classification."""
    payload = {
        "message": "Where is Gate A at MetLife Stadium?",
        "session_id": "test_session_123",
        "venue_id": "met",
        "role": "fan"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert "agent_id" in data
    assert "intent" in data

def test_incidents_management(client):
    """Verify listing and creating incidents works cleanly."""
    # List incidents
    response = client.get("/api/incidents/met")
    assert response.status_code == 200
    
    # Create incident
    payload = {
        "description": "Crowd queue congestion building up near escalator at Gate B",
        "location": "Gate B",
        "venue_id": "met",
        "severity_hint": 3,
        "reporter_id": "volunteer-12"
    }
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OPEN"
    assert "id" in data

def test_parking_endpoint(client):
    """Verify getting parking status returns recommendations."""
    response = client.get("/api/transport/met/parking")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data
    assert "venue_id" in data
    assert "A" in data["zones"]

def test_sustainability_score(client):
    """Verify the EcoScore calculator route."""
    payload = {
        "venue_id": "met",
        "travel_mode": "metro",
        "travel_distance": 15.0,
        "group_size": 2,
        "food_choices": ["local_food", "vegan_option"]
    }
    response = client.post("/api/eco/score", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "eco_score" in data
    assert "co2_kg" in data

def test_analytics_summary(client):
    """Verify analytics summary route retrieves valid data."""
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert "platform" in data
    assert data["matches_supported"] == 104

def test_crowd_endpoints(client):
    """Verify crowd status, predictions, and AI analysis endpoints."""
    # Crowd status
    response = client.get("/api/crowd/met")
    assert response.status_code == 200
    assert response.json()["venue_id"] == "met"
    
    # Crowd predictions
    response = client.get("/api/crowd/met/predictions")
    assert response.status_code == 200
    assert "predictions" in response.json()
    
    # Crowd analyze
    response = client.post("/api/crowd/met/analyze")
    assert response.status_code == 200
    assert "analysis" in response.json()

def test_transport_endpoints(client):
    """Verify transport status and route optimization endpoints."""
    # Transport status
    response = client.get("/api/transport/met/status")
    assert response.status_code == 200
    assert "shuttle" in response.json()
    
    # Route optimize
    response = client.post("/api/transport/met/optimize?match_phase=pre_match")
    assert response.status_code == 200
    assert "optimized_routes" in response.json()

def test_eco_endpoints(client):
    """Verify venue sustainability stats and KPIs."""
    response = client.get("/api/eco/met/stats")
    assert response.status_code == 200
    assert response.json()["solar_kwh_today"] == 4200

def test_analytics_kpis(client):
    """Verify detailed venue KPIs analytics endpoints."""
    response = client.get("/api/analytics/kpis/met")
    assert response.status_code == 200
    assert "crowd" in response.json()

def test_a2a_routing(client):
    """Verify A2A task execution via Supervisor Agent."""
    payload = {
        "task_id": "task-abc-123",
        "session_id": "session-a2a-456",
        "agent_id": "ops-command-agent",
        "message": {
            "role": "ops",
            "content": "Status report and resource allocation plan"
        },
        "context": {
            "venue_id": "met",
            "request_type": "status_report"
        }
    }
    response = client.post("/a2a/ops", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

def test_root_html_routes(client):
    """Verify GET requests to frontend pages return HTML files."""
    response = client.get("/")
    assert response.status_code == 200
    
    response = client.get("/index.html")
    assert response.status_code == 200
    
    response = client.get("/fan")
    assert response.status_code == 200
    
    response = client.get("/fan-app.html")
    assert response.status_code == 200
    
    response = client.get("/ops")
    assert response.status_code == 200
    
    response = client.get("/ops-dashboard.html")
    assert response.status_code == 200


def test_global_exception_trigger(monkeypatch):
    """Verify that unhandled exceptions are caught by the middleware and returned as JSON."""
    from fastapi.testclient import TestClient
    local_client = TestClient(app, raise_server_exceptions=False)
    
    # Monkeypatch random.randint inside api.analytics to raise a ValueError
    def mock_randint(*args, **kwargs):
        raise ValueError("Simulated unhandled exception in random")
    monkeypatch.setattr("api.analytics.random.randint", mock_randint)
    
    response = local_client.get("/api/analytics/kpis/met")
    assert response.status_code == 500
    assert "Simulated unhandled exception in random" in response.json()["error"]

def test_endpoint_no_graph_fallbacks(client):
    """Verify endpoint fallbacks when agent graphs are not registered/ready."""
    orig_fan = app.state.fan_graph
    orig_crowd = app.state.crowd_graph
    orig_eco = app.state.eco_graph
    orig_inc = app.state.incident_graph
    orig_trans = app.state.transport_graph
    
    app.state.fan_graph = None
    app.state.crowd_graph = None
    app.state.eco_graph = None
    app.state.incident_graph = None
    app.state.transport_graph = None
    
    try:
        # 1. Crowd analyze fallback
        res = client.post("/api/crowd/met/analyze")
        assert "error" in res.json()
        
        # 2. Transport optimize fallback
        res = client.post("/api/transport/met/optimize")
        assert "error" in res.json()
        
        # 3. Eco score fallback (should run direct fallback calculation)
        payload_eco = {
            "venue_id": "met",
            "travel_mode": "metro",
            "travel_distance": 15.0,
            "group_size": 2,
            "food_choices": ["local_food"]
        }
        res = client.post("/api/eco/score", json=payload_eco)
        assert res.status_code == 200
        assert "eco_score" in res.json()
        
        # 4. Incident report fallback (ai_assessment will have error)
        payload_inc = {
            "description": "Test fallback escalator failure at Gate C",
            "location": "Gate C",
            "venue_id": "met",
            "severity_hint": 2
        }
        res = client.post("/api/incidents", json=payload_inc)
        assert res.status_code == 200
        
        # 5. Get chat history endpoint
        res = client.get("/api/chat/history/session_test_123")
        assert res.status_code == 200
        assert "messages" in res.json()
        
        # 6. Chat 503 agent-not-ready error
        res = client.post("/api/chat", json={"message": "hi", "role": "fan"})
        assert res.status_code == 503
        
        # 7. Restore fan graph temporarily to mock an internal exception (500)
        app.state.fan_graph = orig_fan
        class MockGraphError:
            async def ainvoke(self, *args, **kwargs):
                raise ValueError("Simulated agent runtime error")
        app.state.fan_graph = MockGraphError()
        res = client.post("/api/chat", json={"message": "hi", "role": "fan"})
        assert res.status_code == 500
        assert "Simulated agent runtime error" in res.json()["detail"]
        
        # 8. Invalid venue ID parameter validations (400)
        assert client.get("/api/crowd/invalid").status_code == 400
        assert client.get("/api/crowd/invalid/predictions").status_code == 400
        assert client.post("/api/crowd/invalid/analyze").status_code == 400
        assert client.get("/api/transport/invalid/status").status_code == 400
        assert client.post("/api/transport/invalid/optimize").status_code == 400
        assert client.get("/api/transport/invalid/parking").status_code == 400
        assert client.get("/api/eco/invalid/stats").status_code == 400

        # 9. Resolve incident endpoint and incident exceptions
        res_res = client.patch("/api/incidents/INC-1234/resolve")
        assert res_res.status_code == 200
        assert res_res.json()["status"] == "RESOLVED"
        
        # 10. Crowd exceptions and agent invoke errors
        app.state.crowd_graph = MockGraphError()
        res_crowd_err = client.post("/api/crowd/met/analyze")
        assert "error" in res_crowd_err.json()

    finally:
        app.state.fan_graph = orig_fan
        app.state.crowd_graph = orig_crowd
        app.state.eco_graph = orig_eco
        app.state.incident_graph = orig_inc
        app.state.transport_graph = orig_trans

def test_stream_to_logger_coverage():
    """Verify that StreamToLogger utility properly directs data to logging stream."""
    from middleware.logger import StreamToLogger, get_logger
    logger = get_logger("stadiumiq.test")
    stream = StreamToLogger(logger, 20)
    stream.write("Log line integration test\nSecond line")
    stream.flush()
    assert stream.linebuf == ""







