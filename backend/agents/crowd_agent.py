"""
Crowd Intelligence Agent - LangGraph StateGraph
================================================
Analyzes crowd density, predicts bottlenecks, recommends
flow optimizations. Called directly and via A2A protocol.

StateGraph:
  fetch_crowd_data → fetch_graph_context → analyze_density
                   → predict_bottlenecks → recommend_actions → END
"""
from __future__ import annotations
import logging, random, math
from typing import Annotated, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from .base_agent import get_llm, memory, simulate_response

log = logging.getLogger("stadiumiq.agents.crowd")

CROWD_SYSTEM_PROMPT = """You are the CrowdSense AI for FIFA World Cup 2026 stadium operations.
Analyze crowd density data and provide precise operational recommendations.
Always include: RISK LEVEL (LOW/MEDIUM/HIGH/CRITICAL), RECOMMENDED ACTION, TIME-TO-ACT.
Be concise and decisive - operational staff need clear, actionable output.

GRAPH CONTEXT:
{graph_context}

LIVE CROWD DATA:
{crowd_data}
"""

class CrowdAgentState(TypedDict):
    messages:        Annotated[list, add_messages]
    user_query:      str
    venue_id:        str
    graph_context:   str
    crowd_data:      dict
    density_scores:  dict
    bottlenecks:     list
    recommendations: list
    risk_level:      str
    response:        str

class CrowdIntelligenceGraph:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.llm       = get_llm(temperature=0.4, max_tokens=600)

    def compile(self):
        g = StateGraph(CrowdAgentState)
        g.add_node("fetch_crowd_data",    self._fetch_crowd_data)
        g.add_node("fetch_graph_context", self._fetch_graph_context)
        g.add_node("analyze_density",     self._analyze_density)
        g.add_node("predict_bottlenecks", self._predict_bottlenecks)
        g.add_node("generate_response",   self._generate_response)

        g.set_entry_point("fetch_crowd_data")
        g.add_edge("fetch_crowd_data",    "fetch_graph_context")
        g.add_edge("fetch_graph_context", "analyze_density")
        g.add_edge("analyze_density",     "predict_bottlenecks")
        g.add_edge("predict_bottlenecks", "generate_response")
        g.add_edge("generate_response",   END)
        return g.compile(checkpointer=memory)

    async def _fetch_crowd_data(self, state: CrowdAgentState) -> dict:
        venue_id = state.get("venue_id", "met")
        # Simulate real-time crowd data
        zones = ["north","south","east","west","field","upper"]
        crowd_data = {z: {"density": random.randint(20,98), "flow_rate": random.randint(100,800)} for z in zones}
        return {"crowd_data": crowd_data}

    async def _fetch_graph_context(self, state: CrowdAgentState) -> dict:
        try:
            ctx = await self.retriever.retrieve_for_venue(
                state.get("venue_id","met"),
                f"crowd density zones gates capacity {state.get('user_query','')}",
                top_k=5
            )
            return {"graph_context": ctx}
        except Exception as e:
            return {"graph_context": "Crowd zone context unavailable."}

    async def _analyze_density(self, state: CrowdAgentState) -> dict:
        crowd = state.get("crowd_data", {})
        scores = {}
        for zone, data in crowd.items():
            d = data.get("density", 0)
            scores[zone] = {"density": d, "status": "low" if d<50 else "medium" if d<75 else "high" if d<90 else "critical"}
        overall = max((v["density"] for v in scores.values()), default=0)
        risk = "LOW" if overall<50 else "MEDIUM" if overall<75 else "HIGH" if overall<90 else "CRITICAL"
        return {"density_scores": scores, "risk_level": risk}

    async def _predict_bottlenecks(self, state: CrowdAgentState) -> dict:
        scores = state.get("density_scores", {})
        bottlenecks = [
            {"zone": z, "density": v["density"], "eta_minutes": random.randint(5,30),
             "severity": v["status"], "recommended_gate": "Gate E" if z=="north" else "Gate A"}
            for z, v in scores.items() if v["density"] > 70
        ]
        return {"bottlenecks": bottlenecks}

    async def _generate_response(self, state: CrowdAgentState) -> dict:
        query      = state.get("user_query", "Crowd analysis")
        ctx        = state.get("graph_context", "")
        crowd      = state.get("crowd_data", {})
        risk       = state.get("risk_level", "LOW")
        bns        = state.get("bottlenecks", [])

        if self.llm is None:
            resp = (f"⚡ CROWD ANALYSIS | Risk: {risk}\n"
                    f"Bottlenecks detected: {len(bns)} zones\n"
                    + "\n".join(f"• {b['zone'].upper()}: {b['density']}% - redirect to {b['recommended_gate']}" for b in bns[:3])
                    + "\nAction: Deploy additional stewards to high-density zones immediately.")
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        try:
            crowd_summary = "\n".join(f"  {z}: {d['density']}% capacity ({d.get('status','?')})" for z, d in state.get("density_scores",{}).items())
            system_msg = SystemMessage(content=CROWD_SYSTEM_PROMPT.format(
                graph_context=ctx[:1500],
                crowd_data=crowd_summary
            ))
            result = await self.llm.ainvoke([system_msg, HumanMessage(content=query)])
            resp = result.content
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        except Exception as e:
            log.error("Crowd agent LLM error: %s", e)
            return {"response": await simulate_response("operations", query), "messages": []}
