from fastapi import APIRouter, Request, Header, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid

router = APIRouter()

class EcoQuery(BaseModel):
    venue_id:       Literal["met","dal","la","atz","bc","sf"] = "met"
    travel_mode:    Literal["metro", "bus", "car_petrol", "walk", "bike", "shuttle", "taxi", "flight"] = "metro"
    travel_distance:float = Field(default=25.0, ge=0.0, le=20000.0)
    group_size:     int = Field(default=1, ge=1, le=100)
    food_choices:   List[str] = Field(default_factory=lambda: ["local_food"])

@router.post("/score")
async def eco_score(body: EcoQuery, request: Request, x_gemini_api_key: Optional[str] = Header(None)):
    graph = getattr(request.app.state, "eco_graph", None)
    if not graph:
        factors = {"metro":0.041,"bus":0.089,"car_petrol":0.171,"walk":0.0, "bike":0.0, "shuttle":0.072, "taxi":0.158, "flight":0.255}
        co2 = factors.get(body.travel_mode, 0.1) * body.travel_distance
        return {"co2_kg": round(co2, 2), "eco_score": max(0, int(100-(co2/20)*100)), "eco_points": 50, "recommendations": [], "advice": "Simulation Mode: Choose public transport!"}
    try:
        result = await graph.ainvoke({
            "user_query": "Calculate my eco score", "venue_id": body.venue_id,
            "travel_mode": body.travel_mode, "travel_distance": body.travel_distance,
            "group_size": body.group_size, "food_choices": body.food_choices,
            "messages":[], "co2_kg":0.0,"eco_score":0,"eco_points":0,"recommendations":[],"response":"",
        }, config={"configurable":{"thread_id":str(uuid.uuid4()), "api_key": x_gemini_api_key}})
        return {"co2_kg":result.get("co2_kg",0),"eco_score":result.get("eco_score",0),
                "eco_points":result.get("eco_points",0),"recommendations":result.get("recommendations",[]),
                "advice":result.get("response","")}
    except Exception as e:
        return {"error": str(e)}

@router.get("/{venue_id}/stats")
async def venue_eco_stats(venue_id: str):
    if venue_id not in ("met", "dal", "la", "atz", "bc", "sf"):
        raise HTTPException(status_code=400, detail="Unsupported venue ID")
    return {"venue_id":venue_id,"solar_kwh_today":4200,"waste_diverted_pct":78,
            "water_saved_litres":12000,"co2_avoided_kg":2100,"eco_rating":"A","green_certified":True}
