import pytest
from fastapi.testclient import TestClient
import os
import sys

# Ensure backend directory is in python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from run_local import app

@pytest.fixture(scope="module")
def client():
    """TestClient context fixture."""
    with TestClient(app) as c:
        yield c

def test_api_health(client):
    """Verify that the health check endpoint returns 200 and indicates correct simulation mode."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "mode" in data
    # Health mode must be one of the specified ones
    assert data["mode"] in ("demo", "live_ai")

def test_accessibility_routing(client):
    """Verify that accessibility queries invoke venue-specific details and never return generic guidance."""
    # Test accessibility query for SoFi Stadium (la)
    payload_la = {
        "message": "where is the accessible lift at la?",
        "session_id": "test_acc_la",
        "venue_id": "la",
        "role": "fan"
    }
    response = client.post("/api/chat", json=payload_la)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "accessibility"
    resp_text = data["response"]
    assert "Accessibility Guide" in resp_text
    assert "North Entry" in resp_text or "VIP North" in resp_text or "P1-P4" in resp_text or "Sensory Room" in resp_text

    # Test accessibility query for AT&T Stadium (dal)
    payload_dal = {
        "message": "wheelchair ramp location at dal?",
        "session_id": "test_acc_dal",
        "venue_id": "dal",
        "role": "fan"
    }
    response = client.post("/api/chat", json=payload_dal)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "accessibility"
    resp_text = data["response"]
    assert "Gates 1 and 3" in resp_text or "L1 and L3" in resp_text or "Section 102" in resp_text

def test_emergency_safeguards(client):
    """Verify that emergency/ops queries return disclaimers requiring human approval before action."""
    # Test emergency request
    payload_em = {
        "message": "critical medical help needed at Gate B",
        "session_id": "test_em",
        "venue_id": "met",
        "role": "fan"
    }
    response = client.post("/api/chat", json=payload_em)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "emergency"
    resp_text = data["response"]
    assert "Human Supervisor Approval Required" in resp_text
    assert "dispatch" in resp_text.lower() or "deploy" in resp_text.lower()

    # Test operations dispatcher request
    payload_ops = {
        "message": "deploy more stewards to Section 101 due to high crowd flow",
        "session_id": "test_ops",
        "venue_id": "met",
        "role": "ops"
    }
    response = client.post("/api/chat", json=payload_ops)
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "operations"
    resp_text = data["response"]
    assert "AI OPERATIONS RECOMMENDATIONS" in resp_text or "Human Supervisor Approval Required" in resp_text

def test_multilingual_responses(client):
    """Verify ARIA intent routing and response output in English plus 5 additional languages."""
    languages_tests = [
        {"q": "where is the accessible lift?", "lang": "en", "keywords": ["Accessibility", "Entry"]},
        {"q": "hola, dónde está el ascensor accesible en met?", "lang": "es", "keywords": ["Guía", "Accesibilidad", "Puerta"]},
        {"q": "bonjour, fauteuil roulant rampe porte?", "lang": "fr", "keywords": ["Guide", "Accessibilité", "Porte"]},
        {"q": "olá, ajuda elevador cadeira de rodas?", "lang": "pt", "keywords": ["Guia", "Acessibilidade", "Portão"]},
        {"q": "hallo, hilfe rollstuhl rampe?", "lang": "de", "keywords": ["Barrierefreiheit", "Eingang", "Tor"]},
        {"q": "مرحبا، أين المدخل الميسر للكراسي المتحركة؟", "lang": "ar", "keywords": ["سهولة الوصول", "البوابة", "المصاعد"]}
    ]

    for test in languages_tests:
        payload = {
            "message": test["q"],
            "session_id": f"lang_{test['lang']}",
            "venue_id": "met",
            "role": "fan"
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == test["lang"]
        resp_text = data["response"]
        for kw in test["keywords"]:
            assert kw in resp_text

def test_fan_to_ops_workflow(client):
    """Verify a complete Fan-to-Ops workflow including querying ARIA and incident logging."""
    # 1. Fan reports emergency medical issue to ARIA
    payload = {
        "message": "HELP! Fan has fainted near escalator at Gate B!",
        "session_id": "fan_wf_1",
        "venue_id": "met",
        "role": "fan"
    }
    res_chat = client.post("/api/chat", json=payload)
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert chat_data["intent"] == "emergency"
    assert "Human Supervisor Approval Required" in chat_data["response"]

    # 2. Ops Dashboard operator creates / logs an incident based on the report
    payload_inc = {
        "description": "Fan fainted near Gate B escalator. Medical requested.",
        "location": "Gate B",
        "venue_id": "met",
        "severity_hint": 4,
        "reporter_id": "ARIA-AI"
    }
    res_inc = client.post("/api/incidents", json=payload_inc)
    assert res_inc.status_code == 200
    inc_data = res_inc.json()
    assert inc_data["status"] == "OPEN"
    assert inc_data["location"] == "Gate B"
    inc_id = inc_data["id"]

    # 3. Check active incidents for met venue to ensure it is registered
    res_list = client.get("/api/incidents/met")
    assert res_list.status_code == 200
    incidents_list = res_list.json()
    registered_ids = [inc["id"] for inc in incidents_list["incidents"]]
    assert inc_id in registered_ids
