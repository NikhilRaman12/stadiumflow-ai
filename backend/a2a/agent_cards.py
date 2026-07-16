"""
A2A Agent Cards — StadiumIQ
============================
Defines Agent Cards per Google's Agent-to-Agent (A2A) protocol specification.
Each card describes an agent's capabilities, endpoint, and I/O schemas.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal
import os


class AgentCapability(BaseModel):
    name:        str
    description: str

class AgentInputSchema(BaseModel):
    required: list[str]
    properties: dict[str, dict]

class AgentCard(BaseModel):
    agent_id:    str
    name:        str
    description: str
    version:     str  = "1.0.0"
    author:      str  = "StadiumIQ"
    endpoint:    str
    capabilities: list[AgentCapability]
    input_schema:  dict
    output_schema: dict
    supported_modes: list[Literal["sync", "async", "stream"]] = ["sync","async"]
    tags:          list[str] = []


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def get_all_agent_cards() -> list[AgentCard]:
    return [
        AgentCard(
            agent_id    = "fan-assistant-agent",
            name        = "ARIA — Fan Assistant Agent",
            description = "Multilingual AI assistant for fans: navigation, services, accessibility, itinerary.",
            endpoint    = f"{BASE_URL}/a2a/fan",
            tags        = ["fan","navigation","multilingual","accessibility"],
            capabilities= [
                AgentCapability(name="multilingual_chat",    description="Chat in 32 languages"),
                AgentCapability(name="navigation_guidance",  description="Seat & zone navigation"),
                AgentCapability(name="queue_predictions",    description="Real-time queue wait times"),
                AgentCapability(name="accessibility_routing",description="Wheelchair-accessible routes"),
                AgentCapability(name="itinerary_planning",   description="Personalized matchday plans"),
            ],
            input_schema  = {"type":"object","required":["user_query","venue_id"],"properties":{"user_query":{"type":"string"},"venue_id":{"type":"string"},"session_id":{"type":"string"},"crowd_data":{"type":"object"}}},
            output_schema = {"type":"object","properties":{"response":{"type":"string"},"intent":{"type":"string"},"language":{"type":"string"}}},
        ),
        AgentCard(
            agent_id    = "crowd-intelligence-agent",
            name        = "CrowdSense — Intelligence Agent",
            description = "Real-time crowd density analysis, bottleneck detection, flow optimization.",
            endpoint    = f"{BASE_URL}/a2a/crowd",
            tags        = ["crowd","density","bottleneck","operations"],
            capabilities= [
                AgentCapability(name="density_analysis",      description="Zone-by-zone crowd density"),
                AgentCapability(name="bottleneck_prediction", description="45-min ahead bottleneck forecasts"),
                AgentCapability(name="flow_optimization",     description="Gate & route recommendations"),
                AgentCapability(name="risk_assessment",       description="Crowd risk scoring LOW→CRITICAL"),
            ],
            input_schema  = {"type":"object","required":["venue_id"],"properties":{"venue_id":{"type":"string"},"user_query":{"type":"string"},"time_horizon_min":{"type":"integer"}}},
            output_schema = {"type":"object","properties":{"risk_level":{"type":"string"},"density_scores":{"type":"object"},"bottlenecks":{"type":"array"},"response":{"type":"string"}}},
        ),
        AgentCard(
            agent_id    = "incident-response-agent",
            name        = "IncidentGuard — Response Agent",
            description = "Incident classification, severity scoring, response protocol generation.",
            endpoint    = f"{BASE_URL}/a2a/incident",
            tags        = ["incident","safety","security","medical","emergency"],
            capabilities= [
                AgentCapability(name="incident_classification", description="Classify incident type & severity 1-5"),
                AgentCapability(name="protocol_generation",     description="Generate structured response protocols"),
                AgentCapability(name="resource_allocation",     description="Recommend staff & equipment deployment"),
                AgentCapability(name="escalation_routing",      description="Route to correct authority chains"),
            ],
            input_schema  = {"type":"object","required":["incident_description","location","venue_id"],"properties":{"incident_description":{"type":"string"},"location":{"type":"string"},"venue_id":{"type":"string"},"severity_hint":{"type":"integer"}}},
            output_schema = {"type":"object","properties":{"severity":{"type":"integer"},"severity_label":{"type":"string"},"parsed_response":{"type":"object"},"response":{"type":"string"}}},
        ),
        AgentCard(
            agent_id    = "transport-optimizer-agent",
            name        = "FlowRoute — Transport Agent",
            description = "Transport load balancing, parking optimization, post-match dispersal planning.",
            endpoint    = f"{BASE_URL}/a2a/transport",
            tags        = ["transport","parking","shuttle","metro","routing"],
            capabilities= [
                AgentCapability(name="load_balancing",      description="Shuttle & metro load optimization"),
                AgentCapability(name="parking_assignment",  description="Smart parking zone recommendations"),
                AgentCapability(name="dispersal_planning",  description="Post-match crowd dispersal simulation"),
                AgentCapability(name="route_optimization",  description="Hotel-to-stadium dynamic routing"),
            ],
            input_schema  = {"type":"object","required":["venue_id"],"properties":{"venue_id":{"type":"string"},"match_phase":{"type":"string","enum":["pre_match","in_match","post_match"]},"user_query":{"type":"string"}}},
            output_schema = {"type":"object","properties":{"optimized_routes":{"type":"array"},"transport_state":{"type":"object"},"response":{"type":"string"}}},
        ),
        AgentCard(
            agent_id    = "eco-scoring-agent",
            name        = "EcoScore — Sustainability Agent",
            description = "Carbon footprint calculation, sustainability scoring, eco advice for fans & venues.",
            endpoint    = f"{BASE_URL}/a2a/eco",
            tags        = ["eco","sustainability","carbon","green","sdg"],
            capabilities= [
                AgentCapability(name="carbon_calculation", description="Real CO2 calculations by transport mode"),
                AgentCapability(name="eco_scoring",        description="EcoScore 0-100 with EcoPoints"),
                AgentCapability(name="eco_recommendations",description="Personalized green travel & food tips"),
                AgentCapability(name="venue_eco_stats",    description="Venue sustainability metrics"),
            ],
            input_schema  = {"type":"object","properties":{"travel_mode":{"type":"string"},"travel_distance":{"type":"number"},"group_size":{"type":"integer"},"food_choices":{"type":"array"},"venue_id":{"type":"string"}}},
            output_schema = {"type":"object","properties":{"co2_kg":{"type":"number"},"eco_score":{"type":"integer"},"eco_points":{"type":"integer"},"recommendations":{"type":"array"},"response":{"type":"string"}}},
        ),
        AgentCard(
            agent_id    = "ops-command-agent",
            name        = "OpsCommand — Supervisor Agent",
            description = "Orchestrates all specialist agents, synthesizes operational intelligence, manages staff deployment.",
            endpoint    = f"{BASE_URL}/a2a/ops",
            tags        = ["operations","supervisor","staff","kpi","command"],
            capabilities= [
                AgentCapability(name="agent_orchestration", description="Coordinate all specialist agents via A2A"),
                AgentCapability(name="staff_deployment",    description="AI-optimized staff assignment by zone"),
                AgentCapability(name="kpi_monitoring",      description="Real-time KPI anomaly detection"),
                AgentCapability(name="ops_reporting",       description="Automated shift & incident reports"),
            ],
            input_schema  = {"type":"object","required":["user_query","venue_id"],"properties":{"user_query":{"type":"string"},"venue_id":{"type":"string"},"request_type":{"type":"string"}}},
            output_schema = {"type":"object","properties":{"staff_plan":{"type":"array"},"agent_reports":{"type":"object"},"ops_metrics":{"type":"object"},"response":{"type":"string"}}},
        ),
    ]
