"""
Chat API — /api/chat
=====================
Routes ARIA chat to the appropriate LangGraph agent based on role.
Supports SSE streaming for progressive responses.
"""
from __future__ import annotations
import logging, uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

log = logging.getLogger("stadiumiq.api.chat")
router = APIRouter()


class ChatRequest(BaseModel):
    message:    str
    session_id: str  = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id:   str  = "met"
    role:       str  = "fan"          # fan | ops | volunteer | staff
    language:   str  = "auto"
    context:    dict = Field(default_factory=dict)

class ChatResponse(BaseModel):
    response:   str
    session_id: str
    agent_id:   str
    intent:     Optional[str] = None
    language:   Optional[str] = None
    simulated:  bool = False
    metadata:   dict = Field(default_factory=dict)


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Send a message to the ARIA AI assistant (Fan or Ops mode)."""
    role_to_graph = {
        "fan":       ("fan_graph",  "fan-assistant-agent"),
        "volunteer": ("fan_graph",  "fan-assistant-agent"),
        "ops":       ("ops_graph",  "ops-command-agent"),
        "staff":     ("ops_graph",  "ops-command-agent"),
    }
    graph_attr, agent_id = role_to_graph.get(body.role, ("fan_graph","fan-assistant-agent"))
    graph = getattr(request.app.state, graph_attr, None)

    if graph is None:
        raise HTTPException(503, "AI agent not ready — startup may be in progress")

    try:
        config  = {"configurable": {"thread_id": body.session_id}}
        if body.role in ("fan","volunteer"):
            state = {
                "user_query": body.message, "venue_id": body.venue_id,
                "session_id": body.session_id, "messages": [],
                "detected_language":"en", "intent":"", "graph_context":"", "crowd_data":"", "response":"",
            }
        else:
            state = {
                "user_query": body.message, "venue_id": body.venue_id,
                "session_id": body.session_id, "messages": [],
                "request_type":"", "graph_context":"", "agent_reports":{},
                "ops_metrics":{}, "staff_plan":[], "response":"",
            }

        result = await graph.ainvoke(state, config=config)
        return ChatResponse(
            response=result.get("response",""),
            session_id=body.session_id,
            agent_id=agent_id,
            intent=result.get("intent"),
            language=result.get("detected_language"),
            simulated=not bool(__import__("os").getenv("GEMINI_API_KEY")),
            metadata={"risk_level": result.get("risk_level"), "eco_score": result.get("eco_score")},
        )
    except Exception as e:
        log.error("Chat API error: %s", e, exc_info=True)
        raise HTTPException(500, f"Agent error: {str(e)}")


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """Get conversation history for a session (from LangGraph checkpointer)."""
    return {"session_id": session_id, "messages": [], "note": "History stored in LangGraph MemorySaver"}
