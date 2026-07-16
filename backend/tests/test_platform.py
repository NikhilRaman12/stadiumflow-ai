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
    response = client.get("/api/transport/metlife_stadium/parking")
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
