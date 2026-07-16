from fastapi import APIRouter, Request
import random

router = APIRouter()

@router.get("/kpis/{venue_id}")
async def get_kpis(venue_id: str, request: Request):
    return {
        "venue_id": venue_id,
        "crowd":     {"total_fans": random.randint(50000,85000), "avg_density_pct": random.randint(40,85), "risk_level":"MEDIUM"},
        "transport": {"shuttle_load_pct": random.randint(40,90), "metro_wait_min": random.randint(5,18), "parking_availability_pct": random.randint(15,60)},
        "incidents": {"open":random.randint(0,5),"resolved_today":random.randint(8,25),"severity_avg":1.8},
        "eco":       {"avg_eco_score":random.randint(55,80),"co2_saved_kg":random.randint(800,2500),"eco_champions_pct":random.randint(30,65)},
        "satisfaction": {"nps_score":random.randint(62,91),"aria_chats_today":random.randint(2000,8000),"languages_used":random.randint(12,28)},
    }

@router.get("/summary")
async def platform_summary():
    return {
        "platform": "StadiumIQ — FIFA World Cup 2026",
        "matches_supported": 104, "venues": 16, "total_fans_served": 3400000,
        "ai_interactions_today": 45892, "languages_active": 28,
        "agents_running": 6, "mcp_servers": 4, "graphrag_nodes": 250,
        "uptime_pct": 99.97,
    }
