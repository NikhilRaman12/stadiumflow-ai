import pytest
from fastapi.testclient import TestClient
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def reset_rate_limiter():
    """Traverse ASGI middleware stack and clear in-memory rate limit records."""
    current = app.middleware_stack
    while current:
        if hasattr(current, "app"):
            if type(current).__name__ == "RateLimitMiddleware":
                current.ip_records.clear()
                break
            current = current.app
        else:
            break

def test_security_headers(client):
    """Verify that custom security headers are present on API responses."""
    reset_rate_limiter()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

def test_cors_headers(client):
    """Verify that CORS headers are correctly returned for authorized origins."""
    reset_rate_limiter()
    headers = {"Origin": "http://localhost:3000"}
    response = client.options("/api/health", headers=headers)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_invalid_input_validation(client):
    """Verify input validation handles bad inputs cleanly without tracebacks."""
    reset_rate_limiter()
    # Bad travel mode
    bad_eco = {
        "venue_id": "met",
        "travel_mode": "invalid_mode",
        "travel_distance": 25.0
    }
    response = client.post("/api/eco/score", json=bad_eco)
    assert response.status_code == 422  # Pydantic validation error
    
    # Bad severity hint in incident
    bad_inc = {
        "description": "Short",
        "location": "Gate A",
        "severity_hint": 10  # Out of bounds (1-5)
    }
    response = client.post("/api/incidents", json=bad_inc)
    assert response.status_code == 422

def test_rate_limiting(client):
    """Verify that requests exceeding limits are rate limited (429)."""
    reset_rate_limiter()
    # Trigger 130 quick requests to trip the 120 req/min rate limit
    triggered = False
    for _ in range(130):
        res = client.get("/api/health")
        if res.status_code == 429:
            triggered = True
            break
    assert triggered, "Rate limiting middleware failed to return 429 status code"
