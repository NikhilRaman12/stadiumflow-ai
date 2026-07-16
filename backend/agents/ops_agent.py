"""
OpsCommand Supervisor Agent - LangGraph StateGraph
===================================================
The orchestrating supervisor that routes complex queries
to specialist agents via A2A and synthesizes final responses.
Also handles staff deployment optimization.

StateGraph:
  classify_request → route_to_specialist_agents (A2A calls)
  → fetch_graph_context → synthesize_ops_response → END
"""
from __future__ import annotations
import logging
from typing import Annotated, TypedDict, Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from .base_agent import get_llm, memory, classify_intent, simulate_response

log = logging.getLogger("stadiumiq.agents.ops")

OPS_SYSTEM_PROMPT = """You are the OpsCommand AI Supervisor for FIFA World Cup 2026.
You coordinate all stadium operations: crowd management, incidents, transport, staff deployment.
Synthesize inputs from specialist agents and provide decisive operational directives.
Output format: PRIORITY LEVEL → ACTION REQUIRED → RESOURCES → TIME-TO-ACT

GRAPH CONTEXT:
{graph_context}

SPECIALIST AGENT REPORTS:
{agent_reports}

CURRENT OPS METRICS:
{ops_metrics}
"""

class OpsAgentState(TypedDict):
    messages:       Annotated[list, add_messages]
    user_query:     str
    venue_id:       str
    request_type:   str
    graph_context:  str
    agent_reports:  dict
    ops_metrics:    dict
    staff_plan:     list
    response:       str
    session_id:     str

class OpsCommandGraph:
    def __init__(self, retriever, sub_graphs: dict) -> None:
        self.retriever  = retriever
        self.sub_graphs = sub_graphs    # {name: compiled_graph}
        self.llm        = get_llm(temperature=0.4, max_tokens=800)

    def compile(self):
        g = StateGraph(OpsAgentState)
        g.add_node("classify_request",    self._classify)
        g.add_node("fetch_graph_context", self._fetch_context)
        g.add_node("gather_agent_reports",self._gather_reports)
        g.add_node("optimize_staff",      self._optimize_staff)
        g.add_node("synthesize_response", self._synthesize)

        g.set_entry_point("classify_request")
        g.add_edge("classify_request",     "fetch_graph_context")
        g.add_edge("fetch_graph_context",  "gather_agent_reports")
        g.add_edge("gather_agent_reports", "optimize_staff")
        g.add_edge("optimize_staff",       "synthesize_response")
        g.add_edge("synthesize_response",  END)
        return g.compile(checkpointer=memory)

    async def _classify(self, state: OpsAgentState) -> dict:
        intent = classify_intent(state.get("user_query",""))
        return {"request_type": intent}

    async def _fetch_context(self, state: OpsAgentState) -> dict:
        try:
            ctx = await self.retriever.retrieve_for_venue(
                state.get("venue_id","met"),
                f"operations staff management {state.get('user_query','')}",
                top_k=6
            )
            return {"graph_context": ctx}
        except Exception:
            return {"graph_context": "Ops context unavailable."}

    async def _gather_reports(self, state: OpsAgentState) -> dict:
        """Call sub-agents via A2A-like in-process invocation for rapid synthesis."""
        reports = {}
        venue_id = state.get("venue_id","met")
        config = {"configurable": {"thread_id": f"ops_{state.get('session_id','default')}"}}

        # Call crowd agent
        if "crowd" in self.sub_graphs:
            try:
                result = await self.sub_graphs["crowd"].ainvoke(
                    {"user_query": "Current crowd status", "venue_id": venue_id,
                     "messages": [], "crowd_data": {}, "density_scores": {},
                     "bottlenecks": [], "recommendations": [], "risk_level": "LOW", "response": ""},
                    config=config
                )
                reports["crowd"] = result.get("response","No crowd data")[:300]
            except Exception as e:
                reports["crowd"] = f"Crowd agent unavailable: {e}"

        # Call transport agent
        if "transport" in self.sub_graphs:
            try:
                result = await self.sub_graphs["transport"].ainvoke(
                    {"user_query": "Current transport status", "venue_id": venue_id,
                     "match_phase": "pre_match", "messages": [], "transport_state": {},
                     "optimized_routes": [], "response": ""},
                    config=config
                )
                reports["transport"] = result.get("response","No transport data")[:300]
            except Exception as e:
                reports["transport"] = f"Transport agent unavailable: {e}"

        return {"agent_reports": reports}

    async def _optimize_staff(self, state: OpsAgentState) -> dict:
        """Simple staff deployment optimization based on crowd reports."""
        reports = state.get("agent_reports", {})
        crowd_report = reports.get("crowd","").lower()
        staff_plan = [
            {"zone": "Gate D Concourse", "staff_count": 5, "role": "Crowd Steward", "priority": "HIGH"},
            {"zone": "Medical Station 2", "staff_count": 2, "role": "First Aid",     "priority": "MEDIUM"},
            {"zone": "Gate A Accessible", "staff_count": 2, "role": "Accessibility", "priority": "MEDIUM"},
            {"zone": "Transport Hub",     "staff_count": 3, "role": "Transport",     "priority": "LOW"},
        ]
        if "critical" in crowd_report or "high" in crowd_report:
            staff_plan[0]["staff_count"] = 8
            staff_plan[0]["priority"]    = "CRITICAL"
        return {"staff_plan": staff_plan, "ops_metrics": {"total_staff_deployed": sum(s["staff_count"] for s in staff_plan)}}

    async def _synthesize(self, state: OpsAgentState) -> dict:
        query   = state.get("user_query","Ops status")
        ctx     = state.get("graph_context","")
        reports = state.get("agent_reports",{})
        metrics = state.get("ops_metrics",{})
        staff   = state.get("staff_plan",[])

        if self.llm is None:
            resp = (f"🏟️ OPS COMMAND REPORT\n"
                    f"Total staff deployed: {metrics.get('total_staff_deployed','?')}\n"
                    + "\n".join(f"• [{s['priority']}] {s['zone']}: {s['staff_count']} {s['role']}" for s in staff[:4])
                    + f"\n\nCROWD: {reports.get('crowd','N/A')[:100]}\n"
                    + f"TRANSPORT: {reports.get('transport','N/A')[:100]}")
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        try:
            reports_text = "\n".join(f"[{k.upper()}]: {v[:250]}" for k,v in reports.items())
            system_msg   = SystemMessage(content=OPS_SYSTEM_PROMPT.format(
                graph_context=ctx[:1200], agent_reports=reports_text,
                ops_metrics=str(metrics)
            ))
            result = await self.llm.ainvoke([system_msg, HumanMessage(content=query)])
            return {"response": result.content, "messages": [AIMessage(content=result.content)]}
        except Exception as e:
            log.error("OpsCommand LLM error: %s", e)
            return {"response": await simulate_response("operations", query), "messages": []}
