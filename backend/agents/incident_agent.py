"""
Incident Response Agent - LangGraph StateGraph
===============================================
Detects, classifies, scores severity, and orchestrates
response for stadium incidents. Integrates with A2A to
alert OpsAgent and TransportAgent as needed.

StateGraph:
  ingest_incident → fetch_graph_context → assess_severity
                  → determine_resources → generate_protocol → END
"""
from __future__ import annotations
import logging, json
from typing import Annotated, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from .base_agent import get_llm, memory

log = logging.getLogger("stadiumiq.agents.incident")

INCIDENT_SYSTEM_PROMPT = """You are the IncidentResponse AI for FIFA World Cup 2026.
Analyze stadium incidents and output a structured JSON response ONLY.

Format:
{{
  "severity": 1-5,
  "severity_label": "LOW|MEDIUM|HIGH|CRITICAL|EXTREME",
  "incident_type": "medical|security|crowd|facility|weather|fire|other",
  "immediate_action": "string - first action in next 60 seconds",
  "resources_needed": ["Security", "Medical", "Fire", "Crowd Management", "Logistics"],
  "evacuation_needed": false,
  "crowd_impact": "LOW|MEDIUM|HIGH",
  "escalate_to": ["Duty Manager", "Stadium Director", "Emergency Services"],
  "estimated_resolution": "5-10 min|15-20 min|30+ min",
  "containment_strategy": "string",
  "communication_required": "PA Announcement|Social Media|Emergency Broadcast|None"
}}

GRAPH CONTEXT:
{graph_context}
"""

SEVERITY_RULES = {
    "medical":  {"keywords": ["heart","seizure","unconscious","injury","blood","broken"], "base": 4},
    "fire":     {"keywords": ["fire","smoke","flame","burning","evacuation"],              "base": 5},
    "security": {"keywords": ["fight","weapon","threat","bomb","suspicious"],              "base": 4},
    "crowd":    {"keywords": ["crush","panic","stampede","overflow","bottleneck"],         "base": 3},
    "facility": {"keywords": ["power","outage","flood","structural","collapse"],           "base": 4},
    "weather":  {"keywords": ["lightning","storm","tornado","hail","extreme"],             "base": 3},
}

class IncidentAgentState(TypedDict):
    messages:            Annotated[list, add_messages]
    incident_description: str
    location:            str
    venue_id:            str
    graph_context:       str
    incident_type:       str
    severity_estimate:   int
    parsed_response:     dict
    response:            str
    session_id:          str

class IncidentResponseGraph:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.llm       = get_llm(temperature=0.2, max_tokens=600)

    def compile(self):
        g = StateGraph(IncidentAgentState)
        g.add_node("ingest_incident",     self._ingest)
        g.add_node("fetch_graph_context", self._fetch_context)
        g.add_node("assess_severity",     self._assess_severity)
        g.add_node("generate_protocol",   self._generate_protocol)

        g.set_entry_point("ingest_incident")
        g.add_edge("ingest_incident",     "fetch_graph_context")
        g.add_edge("fetch_graph_context", "assess_severity")
        g.add_edge("assess_severity",     "generate_protocol")
        g.add_edge("generate_protocol",   END)
        return g.compile(checkpointer=memory)

    async def _ingest(self, state: IncidentAgentState) -> dict:
        desc = state.get("incident_description", "").lower()
        itype = "other"
        for t, rules in SEVERITY_RULES.items():
            if any(kw in desc for kw in rules["keywords"]):
                itype = t
                break
        return {"incident_type": itype}

    async def _fetch_context(self, state: IncidentAgentState) -> dict:
        try:
            loc = state.get("location", "")
            ctx = await self.retriever.retrieve_for_venue(
                state.get("venue_id","met"),
                f"emergency services medical security {loc} {state.get('incident_type','')}",
                top_k=5
            )
            return {"graph_context": ctx}
        except Exception:
            return {"graph_context": "Emergency context unavailable - follow standard protocols."}

    async def _assess_severity(self, state: IncidentAgentState) -> dict:
        itype = state.get("incident_type", "other")
        base  = SEVERITY_RULES.get(itype, {}).get("base", 2)
        desc  = state.get("incident_description", "").lower()
        # Boost severity for escalating keywords
        if any(w in desc for w in ["multiple","mass","many people","large","spreading"]):
            base = min(5, base + 1)
        if any(w in desc for w in ["urgent","critical","life","dying","not breathing"]):
            base = min(5, base + 1)
        return {"severity_estimate": base}

    async def _generate_protocol(self, state: IncidentAgentState) -> dict:
        ctx   = state.get("graph_context","")
        desc  = state.get("incident_description","")
        itype = state.get("incident_type","other")
        sev   = state.get("severity_estimate",3)
        loc   = state.get("location","Unknown")

        if self.llm is None:
            parsed = {
                "severity": sev, "severity_label": ["","LOW","LOW","MEDIUM","HIGH","CRITICAL"][sev],
                "incident_type": itype, "immediate_action": "Dispatch nearest response team",
                "resources_needed": ["Medical","Security"], "evacuation_needed": sev>=5,
                "crowd_impact": "HIGH" if sev>=4 else "MEDIUM",
                "escalate_to": ["Duty Manager"] + (["Stadium Director"] if sev>=4 else []),
                "estimated_resolution": "5-10 min" if sev<=2 else "15-20 min",
                "containment_strategy": "Isolate area and redirect crowd flow",
                "communication_required": "PA Announcement" if sev>=3 else "None",
            }
            resp = json.dumps(parsed, indent=2)
            return {"parsed_response": parsed, "response": resp, "messages": [AIMessage(content=resp)]}
        try:
            prompt = (f"Incident: {desc}\nLocation: {loc}\n"
                      f"Type: {itype} | Initial severity estimate: {sev}/5")
            system_msg = SystemMessage(content=INCIDENT_SYSTEM_PROMPT.format(graph_context=ctx[:1500]))
            result = await self.llm.ainvoke([system_msg, HumanMessage(content=prompt)])
            text = result.content
            try:
                m = __import__("re").search(r'\{[\s\S]*\}', text)
                parsed = json.loads(m.group()) if m else {}
            except Exception:
                parsed = {}
            return {"parsed_response": parsed, "response": text, "messages": [AIMessage(content=text)]}
        except Exception as e:
            log.error("Incident agent LLM error: %s", e)
            return {"parsed_response": {}, "response": "Incident protocol generation failed. Follow manual protocols.", "messages": []}
