"""
EcoScore Agent — LangGraph StateGraph
======================================
Calculates carbon footprints, tracks sustainability metrics,
and provides eco-friendly recommendations for fans and venues.

StateGraph:
  parse_eco_inputs → fetch_graph_context
  → calculate_footprint → compare_benchmarks → generate_advice → END
"""
from __future__ import annotations
import logging
from typing import Annotated, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from .base_agent import get_llm, memory, simulate_response

log = logging.getLogger("stadiumiq.agents.eco")

# CO2 factors (kg per km per person)
CO2_FACTORS = {
    "flight":   0.255, "car_petrol": 0.171, "car_electric": 0.053,
    "bus":      0.089, "metro":      0.041,  "bike":          0.000,
    "walk":     0.000, "shuttle":    0.072,  "taxi":          0.158,
}

ECO_SYSTEM_PROMPT = """You are the EcoScore AI for FIFA World Cup 2026.
Calculate carbon footprints and provide sustainability advice.
Be encouraging, not preachy. Reward eco-choices with EcoPoints (0-100 scale).

CO2 reference data:
- Flight: 0.255 kg CO2/km/person
- Car (petrol): 0.171 kg/km/person
- Metro/Rail: 0.041 kg/km/person
- Bus: 0.089 kg/km/person
- E-Bike: 0.000 kg/km/person

GRAPH CONTEXT (Venue eco features):
{graph_context}

FAN ECO PROFILE:
{eco_profile}
"""

class EcoAgentState(TypedDict):
    messages:         Annotated[list, add_messages]
    user_query:       str
    venue_id:         str
    graph_context:    str
    travel_mode:      str
    travel_distance:  float
    group_size:       int
    food_choices:     list
    co2_kg:           float
    eco_score:        int
    eco_points:       int
    recommendations:  list
    response:         str

class EcoScoringGraph:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.llm       = get_llm(temperature=0.6, max_tokens=500)

    def compile(self):
        g = StateGraph(EcoAgentState)
        g.add_node("parse_eco_inputs",    self._parse_inputs)
        g.add_node("fetch_graph_context", self._fetch_context)
        g.add_node("calculate_footprint", self._calculate_footprint)
        g.add_node("generate_advice",     self._generate_advice)

        g.set_entry_point("parse_eco_inputs")
        g.add_edge("parse_eco_inputs",    "fetch_graph_context")
        g.add_edge("fetch_graph_context", "calculate_footprint")
        g.add_edge("calculate_footprint", "generate_advice")
        g.add_edge("generate_advice",     END)
        return g.compile(checkpointer=memory)

    async def _parse_inputs(self, state: EcoAgentState) -> dict:
        # Defaults if not provided
        return {
            "travel_mode":     state.get("travel_mode", "metro"),
            "travel_distance": state.get("travel_distance", 25.0),
            "group_size":      state.get("group_size", 1),
            "food_choices":    state.get("food_choices", ["local_food"]),
        }

    async def _fetch_context(self, state: EcoAgentState) -> dict:
        try:
            ctx = await self.retriever.retrieve_for_venue(
                state.get("venue_id","met"),
                "eco sustainability green energy solar recycling",
                top_k=4
            )
            return {"graph_context": ctx}
        except Exception:
            return {"graph_context": "Eco context unavailable."}

    async def _calculate_footprint(self, state: EcoAgentState) -> dict:
        mode      = state.get("travel_mode","metro")
        dist      = state.get("travel_distance",25.0)
        group     = state.get("group_size",1)
        factor    = CO2_FACTORS.get(mode, 0.1)
        travel_co2 = factor * dist                      # per person (shared car etc handled by factor)
        food_co2   = sum({"beef_burger":3.5,"veggie_burger":0.8,"chicken":2.1,"pizza":1.6,"local_food":1.2,"snacks":0.3}.get(f,1.0) for f in state.get("food_choices",["local_food"]))
        total_co2  = travel_co2 + food_co2
        # Score: 100 = zero carbon, 0 = very high carbon (>20kg)
        eco_score = max(0, int(100 - (total_co2 / 20) * 100))
        eco_points = eco_score // 2                      # gamification points

        recs = []
        if mode in ("car_petrol","taxi","flight"):
            recs.append("🚌 Switch to metro/shuttle — save up to 75% CO₂ on transport")
        if "beef_burger" in state.get("food_choices",[]):
            recs.append("🥗 Choose veggie option — saves 2.7kg CO₂ per meal")
        if eco_score >= 80:
            recs.append("🌟 Excellent eco choice! You're a Green Champion today")

        return {"co2_kg": round(total_co2, 2), "eco_score": eco_score, "eco_points": eco_points, "recommendations": recs}

    async def _generate_advice(self, state: EcoAgentState) -> dict:
        query  = state.get("user_query","Eco advice")
        ctx    = state.get("graph_context","")
        co2    = state.get("co2_kg",0)
        score  = state.get("eco_score",50)
        points = state.get("eco_points",25)
        recs   = state.get("recommendations",[])
        mode   = state.get("travel_mode","metro")
        dist   = state.get("travel_distance",25)

        if self.llm is None:
            resp = (f"🌱 ECOSCORE REPORT\n"
                    f"Carbon footprint: {co2:.1f}kg CO₂\n"
                    f"EcoScore: {score}/100 | EcoPoints earned: {points}⭐\n"
                    f"Transport: {mode.upper()} ({dist}km)\n"
                    + ("\n".join(f"• {r}" for r in recs) if recs else "• Keep up the great eco choices!"))
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        try:
            eco_profile = f"Transport: {mode} | Distance: {dist}km | CO2: {co2:.2f}kg | Score: {score}/100"
            system_msg = SystemMessage(content=ECO_SYSTEM_PROMPT.format(
                graph_context=ctx[:1000], eco_profile=eco_profile
            ))
            result = await self.llm.ainvoke([system_msg, HumanMessage(content=query)])
            return {"response": result.content, "messages": [AIMessage(content=result.content)]}
        except Exception as e:
            log.error("Eco agent LLM error: %s", e)
            return {"response": await simulate_response("eco", query), "messages": []}
