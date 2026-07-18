import pytest
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_websocket_connection_and_pings(client):
    """Test that clients can connect, receive initial data, and ping-pong over WebSockets."""
    with client.websocket_connect("/ws") as websocket:
        # 1. Read initial state messages (there are 3: crowd, transport, incidents)
        initial_types = []
        for _ in range(3):
            msg = websocket.receive_json()
            initial_types.append(msg["type"])
        assert "crowd:state" in initial_types
        assert "transport:state" in initial_types
        
        # 2. Test ping-pong
        websocket.send_json({"type": "ping"})
        msg_pong = websocket.receive_json()
        assert msg_pong["type"] == "pong"

def test_websocket_venue_subscription(client):
    """Test subscribing to specific venue updates."""
    with client.websocket_connect("/ws") as websocket:
        # Drain initial 3 messages
        for _ in range(3):
            websocket.receive_json()
            
        websocket.send_json({"type": "subscribe:venue", "venue_id": "met"})
        # We should receive venue state response
        res = websocket.receive_json()
        assert res["type"] == "venue:state"
        assert res["data"]["venue_id"] == "met"

def test_websocket_report_incident(client):
    """Test reporting an incident via WebSockets and verifying broadcast."""
    with client.websocket_connect("/ws") as websocket:
        # Drain initial 3 messages
        for _ in range(3):
            websocket.receive_json()

        websocket.send_json({
            "type": "incident:report",
            "data": {
                "description": "WS incident test near Gate C",
                "location": "Gate C",
                "venue_id": "met",
                "severity_hint": 2
            }
        })
        # The broadcast should send incident details back
        broadcast_msg = websocket.receive_json()
        assert broadcast_msg["type"] == "incident:new"
        assert broadcast_msg["data"]["description"] == "WS incident test near Gate C"

def test_websocket_invalid_message(client):
    """Verify that incoming WebSocket messages with unknown types are handled cleanly."""
    with client.websocket_connect("/ws") as websocket:
        for _ in range(3):
            websocket.receive_json()
        websocket.send_json({"type": "unknown_action_type"})
        # Should not crash the server and allow subsequent pings
        websocket.send_json({"type": "ping"})
        msg_pong = websocket.receive_json()
        assert msg_pong["type"] == "pong"

@pytest.mark.asyncio
async def test_broadcast_loop_directly(monkeypatch):
    """Verify that the periodic WebSocket broadcast loop runs successfully across all intervals."""
    import main
    ticks = 0
    async def mock_sleep(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 6:
            raise ValueError("Stop loop execution")
        # run immediately
        
    monkeypatch.setattr(main.asyncio, "sleep", mock_sleep)
    
    try:
        await main.broadcast_loop()
    except ValueError:
        pass

