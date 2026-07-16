"""
A2A Server — StadiumIQ
========================
Implements Google's Agent-to-Agent (A2A) protocol HTTP endpoints.
Each agent is exposed at /a2a/{agent_name} accepting Task objects
and returning Message responses per A2A spec.
"""
from __future__ import annotations
import logging, uuid
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from .agent_cards import get_all_agent_cards, AgentCard

log = logging.getLogger("stadiumiq.a2a")


# ── A2A Protocol Data Models ─────────────────────────────────────────

class A2AMessage(BaseModel):
    role:    str           # "user" | "agent"
    content: str
    metadata: dict = Field(default_factory=dict)

class A2ATask(BaseModel):
    task_id:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id:   str
    message:    A2AMessage
    context:    dict = Field(default_factory=dict)
    created_at: str  = Field(default_factory=lambda: datetime.utcnow().isoformat())

class A2AResponse(BaseModel):
    task_id:    str
    agent_id:   str
    status:     str   # "completed" | "failed" | "streaming"
    message:    A2AMessage
    metadata:   dict = Field(default_factory=dict)
    completed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── A2A Router ────────────────────────────────────────────────────────

class A2ARouter:
    """Mounts A2A endpoints for all agents and the agent registry."""

    def __init__(self) -> None:
        self.router = APIRouter()
        self._register_routes()

    def _register_routes(self) -> None:
        router = self.router

        @router.get("/agents", summary="A2A Agent Registry — discover all agents")
        async def list_agents():
            """Return all Agent Cards in the StadiumIQ multi-agent system."""
            cards = get_all_agent_cards()
            return {"agents": [c.model_dump() for c in cards], "count": len(cards),
                    "protocol": "A2A/1.0", "platform": "StadiumIQ FIFA WC 2026"}

        @router.get("/agents/{agent_id}", summary="Get specific agent card")
        async def get_agent(agent_id: str):
            cards = {c.agent_id: c for c in get_all_agent_cards()}
            if agent_id not in cards:
                raise HTTPException(404, f"Agent '{agent_id}' not found")
            return cards[agent_id].model_dump()

        # ── Per-agent task endpoints ──────────────────────────────────

        @router.post("/fan", summary="Send task to Fan Assistant Agent")
        async def fan_task(task: A2ATask, request: Request):
            return await _invoke_agent(request, "fan_graph", task, "fan-assistant-agent", {
                "user_query": task.message.content,
                "venue_id":   task.context.get("venue_id", "met"),
                "session_id": task.session_id,
                "messages":   [], "detected_language": "en", "intent": "",
                "graph_context": "", "crowd_data": "", "response": "",
            })

        @router.post("/crowd", summary="Send task to Crowd Intelligence Agent")
        async def crowd_task(task: A2ATask, request: Request):
            return await _invoke_agent(request, "crowd_graph", task, "crowd-intelligence-agent", {
                "user_query": task.message.content,
                "venue_id":   task.context.get("venue_id","met"),
                "session_id": task.session_id,
                "messages":   [], "crowd_data": {}, "density_scores": {},
                "bottlenecks":[], "recommendations":[], "risk_level":"LOW", "response":"",
            })

        @router.post("/incident", summary="Send task to Incident Response Agent")
        async def incident_task(task: A2ATask, request: Request):
            ctx = task.context
            return await _invoke_agent(request, "incident_graph", task, "incident-response-agent", {
                "incident_description": task.message.content,
                "location":  ctx.get("location","Unknown"),
                "venue_id":  ctx.get("venue_id","met"),
                "session_id":task.session_id,
                "messages":  [], "incident_type":"other", "severity_estimate":3,
                "parsed_response":{}, "response":"",
            })

        @router.post("/transport", summary="Send task to Transport Optimizer Agent")
        async def transport_task(task: A2ATask, request: Request):
            ctx = task.context
            return await _invoke_agent(request, "transport_graph", task, "transport-optimizer-agent", {
                "user_query":  task.message.content,
                "venue_id":    ctx.get("venue_id","met"),
                "match_phase": ctx.get("match_phase","pre_match"),
                "session_id":  task.session_id,
                "messages":    [], "transport_state":{}, "optimized_routes":[], "response":"",
            })

        @router.post("/eco", summary="Send task to EcoScore Agent")
        async def eco_task(task: A2ATask, request: Request):
            ctx = task.context
            return await _invoke_agent(request, "eco_graph", task, "eco-scoring-agent", {
                "user_query":       task.message.content,
                "venue_id":         ctx.get("venue_id","met"),
                "travel_mode":      ctx.get("travel_mode","metro"),
                "travel_distance":  ctx.get("travel_distance",25.0),
                "group_size":       ctx.get("group_size",1),
                "food_choices":     ctx.get("food_choices",["local_food"]),
                "session_id":       task.session_id,
                "messages":         [], "co2_kg":0.0, "eco_score":0,
                "eco_points":0, "recommendations":[], "response":"",
            })

        @router.post("/ops", summary="Send task to OpsCommand Supervisor Agent")
        async def ops_task(task: A2ATask, request: Request):
            ctx = task.context
            return await _invoke_agent(request, "ops_graph", task, "ops-command-agent", {
                "user_query":   task.message.content,
                "venue_id":     ctx.get("venue_id","met"),
                "request_type": ctx.get("request_type","general"),
                "session_id":   task.session_id,
                "messages":     [], "agent_reports":{}, "ops_metrics":{},
                "staff_plan":   [], "response":"",
            })


async def _invoke_agent(request: Request, graph_attr: str, task: A2ATask,
                        agent_id: str, state: dict) -> A2AResponse:
    """Helper to invoke a LangGraph agent from an A2A task."""
    graph = getattr(request.app.state, graph_attr, None)
    if graph is None:
        return A2AResponse(
            task_id=task.task_id, agent_id=agent_id, status="failed",
            message=A2AMessage(role="agent", content="Agent not initialized. Startup may still be in progress."),
            metadata={"error": "graph_not_ready"}
        )
    try:
        config = {"configurable": {"thread_id": task.session_id}}
        result = await graph.ainvoke(state, config=config)
        response_text = result.get("response", "No response generated")
        meta = {k: v for k, v in result.items() if k not in ("messages","response") and not callable(v)}
        return A2AResponse(
            task_id=task.task_id, agent_id=agent_id, status="completed",
            message=A2AMessage(role="agent", content=response_text, metadata=meta),
            metadata={"langgraph_state_keys": list(result.keys())}
        )
    except Exception as e:
        log.error("A2A agent invocation error [%s]: %s", agent_id, e, exc_info=True)
        return A2AResponse(
            task_id=task.task_id, agent_id=agent_id, status="failed",
            message=A2AMessage(role="agent", content=f"Agent error: {str(e)}"),
            metadata={"error": str(e)}
        )
