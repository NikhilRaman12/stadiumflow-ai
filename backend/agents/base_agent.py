"""
LangGraph Base Agent - StadiumIQ
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


def get_llm(temperature: float = 0.7, max_tokens: int = 1024, api_key: str | None = None) -> ChatGoogleGenerativeAI | None:
    """Return a configured Gemini 1.5 Pro LLM, or None if no API key."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        log.warning("GEMINI_API_KEY not set - agents in simulation mode")
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
    """Rule-based intent classifier - feeds routing decisions in StateGraphs."""
    q = query.lower()
    # Check accessibility & emergencies FIRST to avoid general/navigation overrides
    if any(w in q for w in [
        "emergency","medical","sick","hurt","injured","help","danger","fire","lost","sos","first aid","doctor","police","security",
        "urgencia","emergencia","médico","medico","ayuda","danger","feuer","secours","pompiers","policía","policia",
        "socorro","ambulancia","accident","rettung","krank","notfall","طوارئ","إسعاف","طبيب","شرطة","مساعدة"
    ]):
        return "emergency"
    if any(w in q for w in [
        "wheelchair","accessible","disability","ramp","lift","elevator","quiet zone","assistance","escort",
        "accesible","silla de ruedas","elevador","ascensor","fauteuil","rampe","rampa",
        "cadeira de rodas","elevador","rollstuhl","aufzug","الكرسي","المتحرك","الميسر","مصعد","ممر","سهولة"
    ]):
        return "accessibility"
    if any(w in q for w in ["incident","alert","security","staff","deploy","crowd crush","ops","operation"]):
        return "operations"
    if any(w in q for w in ["seat","section","gate","navigate","find","where","asiento","siège","sitz"]):
        return "navigation"
    if any(w in q for w in ["crowd","busy","queue","wait","concession","food","line","cola"]):
        return "crowd_services"
    if any(w in q for w in ["bus","metro","train","parking","transport","shuttle","taxi","ride"]):
        return "transport"
    if any(w in q for w in ["carbon","eco","green","environment","sustainability","footprint","co2"]):
        return "eco"
    if any(w in q for w in ["itinerary","plan","schedule","timeline","match","kick"]):
        return "itinerary"
    return "general"


SIMULATED_RESPONSES = {
    "navigation":      "🎯 Follow the colored pathways from your gate. Check ticket QR for Gate + Section + Row. Staff at every junction! (Simulated)",
    "crowd_services":  "🍔 Best queue: Level 2 (4 min ✅). Level 1 (8 min). Eco pick: veggie burger saves 2.1kg CO₂! 🌱 (Simulated)",
    "accessibility":   "♿ Accessible entrance: Gate A (ramp). Lifts on all levels. Accessible seats: Section F, Rows 1-2. (Simulated)",
    "transport":       "🚌 Metro Line 3: 12-min wait ✅ | Shuttle Zone C: 6 min ✅ | Parking A: 95% full ❌ → use Zone D (Simulated)",
    "eco":             "🌱 Your matchday footprint: ~7.1kg CO₂. Metro vs driving saved 4.2kg! 336 tonnes saved if all fans chose metro. (Simulated)",
    "emergency":       "🚨 **EMERGENCY ESCALATION REGISTERED (UNCONFIRMED)**\n• **Immediate Action**: Call 911 directly or press the physical RED SOS button on any stadium column. AEDs are located every 100m on the concourse.\n• **Escalation Path**: Incident has been logged. Duty Manager is notified.\n⚠️ **Human Supervisor Approval Required**: Staff dispatch, medical team deployment, or area evacuation cannot be executed automatically. A human operator must confirm the dispatch in the Ops Dashboard.",
    "operations":      "⚡ **AI OPERATIONS RECOMMENDATIONS (PENDING HUMAN APPROVAL)**\n• **Crowd Management**: Recommendation to redirect flow from Gate D (82% density) to Gate E.\n• **Incident Control**: Recommendation to escalate security response.\n• **Access Control**: Recommendation to restrict entry.\n⚠️ **Human Supervisor Approval Required**: Action pending operator confirmation. Do not redirect crowd flow, dispatch stewards, or restrict entry without explicit human supervisor sign-off.",
    "itinerary":       "📅 T-3h: Arrive Gate A | T-2h: Fan zone & food | T-1h: Seat by kick-off | HT: concourse level 2 | FT+30: Metro exit (Simulated)",
    "general":         "🤖 Hi! I'm ARIA - your FIFA WC 2026 AI. Ask me about navigation, queues, transport, accessibility, or eco tips!",
}


async def simulate_response(intent: str, query: str, context: str = "") -> str:
    """Return a realistic simulated response when LLM is unavailable."""
    ql = query.lower()
    venue_id = "met"
    for v in ["met", "dal", "la", "atz", "bc", "sf"]:
        if v in ql:
            venue_id = v
            break

    if intent == "accessibility":
        try:
            from run_local import ACCESSIBILITY_DATA
            details = ACCESSIBILITY_DATA.get(venue_id, ACCESSIBILITY_DATA["met"])
        except Exception:
            details = {
                "gate": "Gate A or Gate C (fully accessible with flat ramps)",
                "lifts": "Lifts A1, A2, and B1 are fully operational. Note: Lift B3 is temporarily closed for maintenance.",
                "routes": "Use Level 1 concourse elevator lobby for access to upper deck. Follow the blue accessibility paths.",
                "quiet_zone": "Quiet Room / Sensory Room is located on Plaza Level near Section 117.",
                "assistance": "Press the blue assistance button at Gate A/C, or text 'ACCESS' to 84444 for staff-assistance escort (15-min ETA)."
            }
        return (
            f"♿ **Accessibility Guide — {venue_id.upper()} Venue (Simulated)**\n"
            f"• **Accessible Entry**: Enter through {details['gate']}.\n"
            f"• **Elevators/Lifts**: {details['lifts']}\n"
            f"• **Alternative Routes**: {details['routes']}\n"
            f"• **Quiet Zone**: {details['quiet_zone']}\n"
            f"• **Staff Assistance**: {details['assistance']}"
        )

    base = SIMULATED_RESPONSES.get(intent, SIMULATED_RESPONSES["general"])
    if context:
        return f"{base}\n\n📚 Graph context: {context[:200]}…"
    return base
