from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List
import uuid

router = APIRouter()

class EcoQuery(BaseModel):
    venue_id:       str   = "met"
    travel_mode:    str   = "metro"
    travel_distance:float = 25.0
    group_size:     int   = 1
    food_choices:   List[str] = ["local_food"]

@router.post("/score")
async def eco_score(body: EcoQuery, request: Request):
    graph = getattr(request.app.state, "eco_graph", None)
    if not graph:
        factors = {"metro":0.041,"bus":0.089,"car_petrol":0.171,"walk":0.0}
        co2 = factors.get(body.travel_mode, 0.1) * body.travel_distance
        return {"co2_kg": round(co2, 2), "eco_score": max(0, int(100-(co2/20)*100)), "eco_points": 50}
    try:
        result = await graph.ainvoke({
            "user_query": "Calculate my eco score", "venue_id": body.venue_id,
            "travel_mode": body.travel_mode, "travel_distance": body.travel_distance,
            "group_size": body.group_size, "food_choices": body.food_choices,
            "messages":[], "co2_kg":0.0,"eco_score":0,"eco_points":0,"recommendations":[],"response":"",
        }, config={"configurable":{"thread_id":str(uuid.uuid4())}})
        return {"co2_kg":result.get("co2_kg",0),"eco_score":result.get("eco_score",0),
                "eco_points":result.get("eco_points",0),"recommendations":result.get("recommendations",[]),
                "advice":result.get("response","")}
    except Exception as e:
        return {"error": str(e)}

@router.get("/{venue_id}/stats")
async def venue_eco_stats(venue_id: str):
    return {"venue_id":venue_id,"solar_kwh_today":4200,"waste_diverted_pct":78,
            "water_saved_litres":12000,"co2_avoided_kg":2100,"eco_rating":"A","green_certified":True}
