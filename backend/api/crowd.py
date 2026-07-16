"""
Crowd API — /api/crowd
=======================
Real-time crowd data and AI analysis endpoints.
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
import random, uuid

router = APIRouter()

@router.get("/{venue_id}")
async def get_crowd(venue_id: str, request: Request):
    sim = getattr(request.app.state, "crowd_sim", None)
    if sim:
        return sim.get_venue_state(venue_id)
    zones = ["north","south","east","west","field","upper"]
    return {
        "venue_id": venue_id,
        "zones": {z: {"density": random.randint(20,98), "flow_rate": random.randint(100,800),
                      "status": "normal", "capacity_pct": random.randint(20,98)} for z in zones},
        "overall_risk": "MEDIUM", "timestamp": "2026-07-16T07:00:00Z"
    }

@router.get("/{venue_id}/predictions")
async def get_predictions(venue_id: str, minutes_ahead: int = 45):
    return {
        "venue_id": venue_id, "minutes_ahead": minutes_ahead,
        "predictions": [
            {"zone":"north","predicted_density":87,"severity":"HIGH","recommendation":"Redirect to Gate E"},
            {"zone":"south","predicted_density":62,"severity":"MEDIUM","recommendation":"Monitor, deploy 1 steward"},
            {"zone":"east", "predicted_density":44,"severity":"LOW",   "recommendation":"Normal operations"},
        ]
    }

@router.post("/{venue_id}/analyze")
async def analyze_crowd(venue_id: str, request: Request):
    graph = getattr(request.app.state, "crowd_graph", None)
    if graph is None:
        return {"error": "Crowd agent not ready"}
    try:
        result = await graph.ainvoke({
            "user_query": f"Analyze crowd at {venue_id}", "venue_id": venue_id,
            "messages":[], "crowd_data":{}, "density_scores":{},
            "bottlenecks":[], "recommendations":[], "risk_level":"LOW", "response":"",
        }, config={"configurable":{"thread_id":str(uuid.uuid4())}})
        return {"venue_id":venue_id,"analysis":result.get("response"),"risk_level":result.get("risk_level"),"bottlenecks":result.get("bottlenecks",[])}
    except Exception as e:
        return {"error": str(e)}
