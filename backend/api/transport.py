from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional, Literal
import uuid, random

router = APIRouter()

@router.get("/{venue_id}/status")
async def transport_status(venue_id: str, request: Request):
    if venue_id not in ("met", "dal", "la", "atz", "bc", "sf"):
        raise HTTPException(status_code=400, detail="Unsupported venue ID")
    opt = getattr(request.app.state, "transport_opt", None)
    if opt:
        return opt.get_full_state()
    return {
        "venue_id": venue_id,
        "shuttle":   {"wait_min": random.randint(3,18), "load_pct": random.randint(30,90)},
        "metro":     {"wait_min": random.randint(5,20), "load_pct": random.randint(40,95)},
        "parking":   {"zone_a": random.randint(50,100), "zone_b": random.randint(20,75), "zone_d": random.randint(5,40)},
        "taxi_surge": round(random.uniform(1.0, 3.5), 1),
    }

@router.post("/{venue_id}/optimize")
async def optimize_transport(
    venue_id: str,
    match_phase: Literal["pre_match", "in_match", "post_match"] = "pre_match",
    request: Request = None,
    x_gemini_api_key: Optional[str] = Header(None)
):
    if venue_id not in ("met", "dal", "la", "atz", "bc", "sf"):
        raise HTTPException(status_code=400, detail="Unsupported venue ID")
    graph = getattr(request.app.state, "transport_graph", None)
    if not graph:
        return {"error": "Transport agent not ready"}
    try:
        result = await graph.ainvoke({
            "user_query": f"Optimize transport for {venue_id} during {match_phase}",
            "venue_id": venue_id, "match_phase": match_phase,
            "messages":[], "transport_state":{}, "optimized_routes":[], "response":"",
        }, config={"configurable":{"thread_id":str(uuid.uuid4()), "api_key": x_gemini_api_key}})
        return {"venue_id":venue_id,"match_phase":match_phase,
                "optimized_routes":result.get("optimized_routes",[]),
                "recommendation":result.get("response")}
    except Exception as e:
        return {"error": str(e)}

@router.get("/{venue_id}/parking")
async def parking_status(venue_id: str):
    if venue_id not in ("met", "dal", "la", "atz", "bc", "sf"):
        raise HTTPException(status_code=400, detail="Unsupported venue ID")
    return {"venue_id": venue_id, "zones": {
        "A": {"capacity_pct": random.randint(60,100), "recommended": False},
        "B": {"capacity_pct": random.randint(30,75),  "recommended": False},
        "C": {"capacity_pct": random.randint(20,60),  "recommended": True},
        "D": {"capacity_pct": random.randint(5,40),   "recommended": True},
    }, "recommendation": "Use Zone C or D - lower occupancy and 5-min walk"}
