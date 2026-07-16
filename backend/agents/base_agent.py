"""
LangGraph Base Agent — StadiumIQ
==================================
Shared utilities, LLM client, and common graph node factories
used by all 6 specialized LangGraph StateGraph agents.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts  import ChatPromptTemplate
from langgraph.graph          import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

log = logging.getLogger("stadiumiq.agents")


def get_llm(temperature: float = 0.7, max_tokens: int = 1024) -> ChatGoogleGenerativeAI | None:
    """Return a configured Gemini 1.5 Pro LLM, or None if no API key."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        log.warning("GEMINI_API_KEY not set — agents in simulation mode")
        return None
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-pro",
        google_api_key=key,
        temperature=temperature,
        max_output_tokens=max_tokens,
        convert_system_message_to_human=True,
    )


# Shared in-memory checkpointer (replace with SqliteSaver for persistence)
memory = MemorySaver()


def detect_language_node(state: dict) -> dict:
    """
    Heuristic language detection from user query.
    In production, replace with langdetect or Gemini itself.
    """
    q = state.get("user_query", "").lower()
    lang_hints = {
        "es": ["hola","gracias","por","como","donde","silla","asiento","ayuda"],
        "fr": ["bonjour","merci","où","comment","siège","aide","fauteuil"],
        "pt": ["olá","obrigado","como","onde","assento","ajuda"],
        "de": ["hallo","danke","wie","wo","sitz","hilfe"],
        "ar": ["مرحبا","شكرا","أين","كيف"],
        "zh": ["你好","谢谢","在哪","如何"],
        "ja": ["こんにちは","ありがとう","どこ","どうやって"],
        "ko": ["안녕","감사","어디","어떻게"],
        "hi": ["नमस्ते","धन्यवाद","कहाँ","कैसे"],
        "it": ["ciao","grazie","dove","come","posto"],
    }
    detected = "en"
    for lang, words in lang_hints.items():
        if any(w in q for w in words):
            detected = lang
            break
    return {"detected_language": detected}


def classify_intent(query: str) -> str:
    """Rule-based intent classifier — feeds routing decisions in StateGraphs."""
    q = query.lower()
    if any(w in q for w in ["seat","section","gate","navigate","find","where","asiento","siège","sitz"]):
        return "navigation"
    if any(w in q for w in ["crowd","busy","queue","wait","concession","food","line","cola"]):
        return "crowd_services"
    if any(w in q for w in ["wheelchair","accessible","disability","ramp","lift","elevator","silla de ruedas","fauteuil"]):
        return "accessibility"
    if any(w in q for w in ["bus","metro","train","parking","transport","shuttle","taxi","ride"]):
        return "transport"
    if any(w in q for w in ["carbon","eco","green","environment","sustainability","footprint"]):
        return "eco"
    if any(w in q for w in ["emergency","medical","sick","injured","help","danger","fire","lost"]):
        return "emergency"
    if any(w in q for w in ["incident","alert","security","staff","deploy","crowd crush"]):
        return "operations"
    if any(w in q for w in ["itinerary","plan","schedule","timeline","match","kick"]):
        return "itinerary"
    return "general"


SIMULATED_RESPONSES = {
    "navigation":      "🎯 Follow the colored pathways from your gate. Check ticket QR for Gate + Section + Row. Staff at every junction!",
    "crowd_services":  "🍔 Best queue: Level 2 (4 min ✅). Level 1 (8 min). Eco pick: veggie burger saves 2.1kg CO₂! 🌱",
    "accessibility":   "♿ Accessible entrance: Gate A (ramp). Lifts on all levels. Accessible seats: Section F, Rows 1-2.",
    "transport":       "🚌 Metro Line 3: 12-min wait ✅ | Shuttle Zone C: 6 min ✅ | Parking A: 95% full ❌ → use Zone D",
    "eco":             "🌱 Your matchday footprint: ~7.1kg CO₂. Metro vs driving saved 4.2kg! 336 tonnes saved if all fans chose metro.",
    "emergency":       "🚨 Nearest first aid: Gate B entrance (2 min). Call 911 or press RED button on any column. AED every 100m.",
    "operations":      "⚡ RISK: MEDIUM | Gate D 78% capacity → redirect to Gate E (32%). Deploy 2 stewards. Act in next 5 min.",
    "itinerary":       "📅 T-3h: Arrive Gate A | T-2h: Fan zone & food | T-1h: Seat by kick-off | HT: concourse level 2 | FT+30: Metro exit",
    "general":         "🤖 Hi! I'm ARIA — your FIFA WC 2026 AI. Ask me about navigation, queues, transport, accessibility, or eco tips!",
}


async def simulate_response(intent: str, query: str, context: str = "") -> str:
    """Return a realistic simulated response when LLM is unavailable."""
    base = SIMULATED_RESPONSES.get(intent, SIMULATED_RESPONSES["general"])
    if context and len(context) > 50:
        return f"{base}\n\n📚 Graph context: {context[:200]}…"
    return base
