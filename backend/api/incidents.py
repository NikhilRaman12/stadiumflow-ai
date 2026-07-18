from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, Literal
import uuid, random
from datetime import datetime

router = APIRouter()

class IncidentReport(BaseModel):
    description: str = Field(..., min_length=3, max_length=500)
    location:    str = Field(..., min_length=2, max_length=100)
    venue_id:    Literal["met","dal","la","atz","bc","sf"] = "met"
    severity_hint: int = Field(default=3, ge=1, le=5)
    reporter_id: str = Field(default="anonymous", max_length=100)

@router.post("")
async def report_incident(body: IncidentReport, request: Request, x_gemini_api_key: Optional[str] = Header(None)):
    graph = getattr(request.app.state, "incident_graph", None)
    mgr   = getattr(request.app.state, "incident_mgr", None)
    iid   = str(uuid.uuid4())[:8].upper()

    ai_response = {}
    if graph:
        try:
            result = await graph.ainvoke({
                "incident_description": body.description, "location": body.location,
                "venue_id": body.venue_id, "session_id": iid,
                "messages": [], "incident_type":"other", "severity_estimate": body.severity_hint,
                "parsed_response":{}, "response":"",
            }, config={"configurable":{"thread_id":iid, "api_key": x_gemini_api_key}})
            ai_response = result.get("parsed_response", {})
        except Exception as e:
            ai_response = {"error": str(e)}

    incident = {"id": iid, "description": body.description, "location": body.location,
                "venue_id": body.venue_id, "status": "OPEN", "created_at": datetime.utcnow().isoformat(),
                "ai_assessment": ai_response, "reporter_id": body.reporter_id}
    if mgr:
        mgr.create_incident(incident)
    return incident

@router.get("/{venue_id}")
async def list_incidents(venue_id: str, request: Request):
    mgr = getattr(request.app.state, "incident_mgr", None)
    if mgr:
        return {"incidents": mgr.get_active(venue_id), "venue_id": venue_id}
    return {"incidents": [], "venue_id": venue_id}

@router.patch("/{incident_id}/resolve")
async def resolve_incident(incident_id: str, request: Request):
    mgr = getattr(request.app.state, "incident_mgr", None)
    if mgr:
        mgr.resolve(incident_id)
    return {"incident_id": incident_id, "status": "RESOLVED", "resolved_at": datetime.utcnow().isoformat()}
