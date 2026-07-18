"""
Fan Assistant - LangGraph StateGraph Agent
==========================================
Handles all fan-facing queries: navigation, services,
multilingual chat, accessibility, itinerary planning.

StateGraph flow:
  detect_language
      ↓
  fetch_graph_context  (GraphRAG)
      ↓
  classify_intent
      ↓
  ┌─────────────────────────────────┐
  │  navigation  crowd  eco  ...    │
  └─────────────────────────────────┘
      ↓
  generate_response  (Gemini 1.5 Pro)
      ↓
  END
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict, Literal, Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from .base_agent import get_llm, memory, detect_language_node, classify_intent, simulate_response

log = logging.getLogger("stadiumiq.agents.fan")

FAN_SYSTEM_PROMPT = """You are ARIA - the official AI assistant for StadiumIQ at FIFA World Cup 2026.
You help fans navigate stadiums, find services, plan their day, and stay safe.
Be friendly, concise, and always safety-first.
AUTO-DETECT the user's language and RESPOND in that same language.
Use emojis for quick scanning. Keep replies under 150 words unless complex routing.

GRAPH CONTEXT (stadium knowledge):
{graph_context}

CURRENT CONDITIONS:
- Crowd data: {crowd_data}
- Venue: {venue_id}
"""


class FanAgentState(TypedDict):
    messages:          Annotated[list, add_messages]
    user_query:        str
    detected_language: str
    venue_id:          str
    intent:            str
    graph_context:     str
    crowd_data:        str
    response:          str
    session_id:        str


class FanAssistantGraph:
    def __init__(self, retriever) -> None:
        self.retriever = retriever
        self.llm       = get_llm(temperature=0.75, max_tokens=512)

    def compile(self):
        g = StateGraph(FanAgentState)

        g.add_node("detect_language",     self._detect_language)
        g.add_node("fetch_graph_context", self._fetch_graph_context)
        g.add_node("classify_intent",     self._classify_intent)
        g.add_node("generate_response",   self._generate_response)

        g.set_entry_point("detect_language")
        g.add_edge("detect_language",     "fetch_graph_context")
        g.add_edge("fetch_graph_context", "classify_intent")
        g.add_edge("classify_intent",     "generate_response")
        g.add_edge("generate_response",   END)

        return g.compile(checkpointer=memory)

    # ── Nodes ──────────────────────────────────────────────────────

    async def _detect_language(self, state: FanAgentState) -> dict:
        return detect_language_node(state)

    async def _fetch_graph_context(self, state: FanAgentState) -> dict:
        try:
            venue_id = state.get("venue_id", "met")
            ctx = await self.retriever.retrieve_for_venue(
                venue_id, state["user_query"], top_k=6
            )
            return {"graph_context": ctx}
        except Exception as e:
            log.error("GraphRAG fetch error: %s", e)
            return {"graph_context": "Stadium context unavailable."}

    async def _classify_intent(self, state: FanAgentState) -> dict:
        intent = classify_intent(state["user_query"])
        return {"intent": intent}

    async def _generate_response(self, state: FanAgentState, config: RunnableConfig = None) -> dict:
        intent  = state.get("intent", "general")
        context = state.get("graph_context", "")
        query   = state["user_query"]

        api_key = config.configurable.get("api_key") if config and hasattr(config, "configurable") and config.configurable else None
        llm = get_llm(temperature=0.75, max_tokens=512, api_key=api_key) if api_key else self.llm

        if llm is None:
            resp = await simulate_response(intent, query, context)
            return {"response": resp, "messages": [AIMessage(content=resp)]}

        try:
            system_msg = SystemMessage(content=FAN_SYSTEM_PROMPT.format(
                graph_context=context[:2000],
                crowd_data=state.get("crowd_data", "Normal conditions"),
                venue_id=state.get("venue_id", "MetLife Stadium"),
            ))
            # Include conversation history (last 6 messages)
            history = state.get("messages", [])[-6:]
            all_msgs = [system_msg] + history + [HumanMessage(content=query)]
            result = await llm.ainvoke(all_msgs)
            resp = result.content
            return {"response": resp, "messages": [AIMessage(content=resp)]}
        except Exception as e:
            log.error("LLM error in fan agent: %s", e)
            fallback = await simulate_response(intent, query, context)
            return {"response": fallback, "messages": [AIMessage(content=fallback)]}
