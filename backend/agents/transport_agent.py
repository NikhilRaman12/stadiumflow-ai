"""
Transport Optimizer Agent — LangGraph StateGraph
=================================================
Optimizes transport routing, parking assignment, shuttle
load balancing, and post-match dispersal planning.

StateGraph:
  fetch_transport_state → fetch_graph_context
  → analyze_loads → optimize_routing → generate_plan → END
"""
from __future__ import annotations
import logging, random
from typing import Annotated, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from .base_agent import get_llm, memory, simulate_response

log = logging.getLogger("stadiumiq.agents.transport")

TRANSPORT_SYSTEM_PROMPT = """You are the FlowRoute AI for FIFA World Cup 2026 transport management.
Optimize transport routing, parking, shuttles, and post-match dispersal for up to 87,000 fans.
Be specific with numbers, times, and zone names. Recommend load balancing actions.

GRAPH CONTEXT:
{graph_context}

TRANSPORT STATE:
{transport_state}

MATCH PHASE: {match_phase}
"""

class TransportAgentState(TypedDict):
    messages:       Annotated[list, add_messages]
    user_query:     str
    venue_id:       str
    match_phase:    str   # pre_match | in_match | post_match
    graph_context:  str
    transport_state: dict
    optimized_routes: list
    response:       str
    session_id:     str

class TransportOptimizerGraph:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.llm       = get_llm(temperature=0.5, max_tokens=700)

    def compile(self):
        g = StateGraph(TransportAgentState)
        g.add_node("fetch_transport_state", self._fetch_transport)
        g.add_node("fetch_graph_context",   self._fetch_graph_context)
        g.add_node("analyze_loads",         self._analyze_loads)
        g.add_node("generate_plan",         self._generate_plan)

        g.set_entry_point("fetch_transport_state")
        g.add_edge("fetch_transport_state", "fetch_graph_context")
        g.add_edge("fetch_graph_context",   "analyze_loads")
        g.add_edge("analyze_loads",         "generate_plan")
        g.add_edge("generate_plan",         END)
        return g.compile(checkpointer=memory)

    async def _fetch_transport(self, state: TransportAgentState) -> dict:
        transport_state = {
            "shuttle": {"wait_min": random.randint(3,20), "load_pct": random.randint(30,95), "zones": ["A","B","C","D"]},
            "metro":   {"wait_min": random.randint(5,18), "load_pct": random.randint(40,100), "lines": ["Line 1","Line 2","Line 3"]},
            "parking": {"zone_a": random.randint(60,100), "zone_b": random.randint(20,80), "zone_c": random.randint(10,60), "zone_d": random.randint(5,40)},
            "taxi_ride_share": {"wait_min": random.randint(8,35), "surge_multiplier": round(random.uniform(1.0,3.5),1)},
        }
        return {"transport_state": transport_state}

    async def _fetch_graph_context(self, state: TransportAgentState) -> dict:
        try:
            ctx = await self.retriever.retrieve_for_venue(
                state.get("venue_id","met"),
                f"transport metro shuttle parking routes {state.get('user_query','')}",
                top_k=5
            )
            return {"graph_context": ctx}
        except Exception:
            return {"graph_context": "Transport context unavailable."}

    async def _analyze_loads(self, state: TransportAgentState) -> dict:
        ts = state.get("transport_state", {})
        routes = []
        shuttle = ts.get("shuttle", {})
        if shuttle.get("load_pct", 0) > 80:
            routes.append({"action": "activate_overflow_shuttles", "priority": "HIGH", "zones": ["D","E"]})
        parking = ts.get("parking", {})
        if parking.get("zone_a", 0) > 85:
            routes.append({"action": "redirect_parking", "from": "Zone A", "to": "Zone D", "priority": "MEDIUM"})
        metro = ts.get("metro", {})
        if metro.get("load_pct", 0) > 90:
            routes.append({"action": "increase_metro_frequency", "lines": ["Line 2"], "priority": "HIGH"})
        return {"optimized_routes": routes}

    async def _generate_plan(self, state: TransportAgentState) -> dict:
        query   = state.get("user_query","Transport status")
        ctx     = state.get("graph_context","")
        ts      = state.get("transport_state",{})
        phase   = state.get("match_phase","pre_match")
        routes  = state.get("optimized_routes",[])

        if self.llm is None:
            p = ts.get("parking",{})
            m = ts.get("metro",{})
            s = ts.get("shuttle",{})
            resp = (f"🚌 TRANSPORT STATUS | Phase: {phase.upper()}\n"
                    f"Metro: {m.get('wait_min','?')}min wait ({m.get('load_pct','?')}% load)\n"
                    f"Shuttle: {s.get('wait_min','?')}min wait ({s.get('load_pct','?')}% load)\n"
                    f"Parking: Zone A {p.get('zone_a','?')}% | Zone D {p.get('zone_d','?')}% (recommended)\n"
                    + (f"\n⚡ Actions: {', '.join(r['action'] for r in routes)}" if routes else ""))
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        try:
            ts_text = "\n".join(f"  {k}: {v}" for k,v in ts.items())
            system_msg = SystemMessage(content=TRANSPORT_SYSTEM_PROMPT.format(
                graph_context=ctx[:1200], transport_state=ts_text, match_phase=phase
            ))
            result = await self.llm.ainvoke([system_msg, HumanMessage(content=query)])
            resp = result.content
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        except Exception as e:
            log.error("Transport agent LLM error: %s", e)
            return {"response": await simulate_response("transport", query), "messages": []}
