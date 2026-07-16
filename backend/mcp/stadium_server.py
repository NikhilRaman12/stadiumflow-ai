"""
Stadium MCP Server — StadiumIQ
================================
Model Context Protocol server exposing stadium data as tools.
Tools are called by LangGraph agents to get structured venue data.
"""
from __future__ import annotations
import json, logging
from pathlib import Path

log = logging.getLogger("stadiumiq.mcp.stadium")

class StadiumMCPServer:
    """In-process MCP tool server for stadium data."""

    _kg = None
    _tools: dict = {}

    @classmethod
    def start(cls, kg) -> None:
        cls._kg = kg
        cls._tools = {
            "get_venue_info":       cls.get_venue_info,
            "get_zone_info":        cls.get_zone_info,
            "get_gate_status":      cls.get_gate_status,
            "get_accessible_routes":cls.get_accessible_routes,
            "get_services_nearby":  cls.get_services_nearby,
            "search_venue_entities":cls.search_venue_entities,
        }
        log.info("StadiumMCPServer started — %d tools registered", len(cls._tools))

    @classmethod
    def stop(cls) -> None:
        log.info("StadiumMCPServer stopped")

    @classmethod
    def call(cls, tool_name: str, **kwargs) -> dict:
        if tool_name not in cls._tools:
            return {"error": f"Unknown tool: {tool_name}", "available": list(cls._tools.keys())}
        try:
            return cls._tools[tool_name](**kwargs)
        except Exception as e:
            log.error("MCP tool error [%s]: %s", tool_name, e)
            return {"error": str(e)}

    # ── Tool Implementations ──────────────────────────────────────────

    @classmethod
    def get_venue_info(cls, venue_id: str) -> dict:
        """Get full venue information including zones, gates, and services."""
        node_id = f"venue:{venue_id}"
        if cls._kg and node_id in cls._kg.graph:
            attrs = dict(cls._kg.graph.nodes[node_id])
            zones = [dict(cls._kg.graph.nodes[n]) for n in cls._kg.graph.successors(node_id)
                     if cls._kg.graph.nodes[n].get("type") == "Zone"]
            gates = [dict(cls._kg.graph.nodes[n]) for n in cls._kg.graph.successors(node_id)
                     if cls._kg.graph.nodes[n].get("type") == "Gate"]
            return {"venue": attrs, "zones": zones, "gates": gates, "found": True}
        return {"found": False, "venue_id": venue_id, "message": "Venue not in knowledge graph"}

    @classmethod
    def get_zone_info(cls, venue_id: str, zone_id: str) -> dict:
        """Get specific zone capacity and status."""
        node_id = f"zone:{venue_id}:{zone_id}"
        if cls._kg and node_id in cls._kg.graph:
            return {"zone": dict(cls._kg.graph.nodes[node_id]), "found": True}
        return {"found": False, "zone_id": zone_id}

    @classmethod
    def get_gate_status(cls, venue_id: str, gate_id: str) -> dict:
        """Get gate accessibility and current status."""
        node_id = f"gate:{venue_id}:{gate_id}"
        if cls._kg and node_id in cls._kg.graph:
            return {"gate": dict(cls._kg.graph.nodes[node_id]), "found": True}
        return {"found": False, "gate_id": gate_id}

    @classmethod
    def get_accessible_routes(cls, venue_id: str, destination: str) -> dict:
        """Get wheelchair-accessible routes to a destination."""
        if not cls._kg:
            return {"routes": [], "error": "KG not initialized"}
        accessible_gates = [
            dict(cls._kg.graph.nodes[n])
            for n in cls._kg.graph.nodes
            if cls._kg.graph.nodes[n].get("type") == "Gate"
            and cls._kg.graph.nodes[n].get("venue_id") == venue_id
            and cls._kg.graph.nodes[n].get("accessible", False)
        ]
        return {
            "accessible_gates": accessible_gates,
            "route": f"Enter via accessible gate → take lift to your level → follow blue accessibility markings to {destination}",
            "escort_available": True,
            "estimated_time_minutes": 5,
        }

    @classmethod
    def get_services_nearby(cls, venue_id: str, service_type: str) -> dict:
        """Find services of a specific type at the venue."""
        if not cls._kg:
            return {"services": []}
        services = [
            dict(cls._kg.graph.nodes[n])
            for n in cls._kg.graph.nodes
            if cls._kg.graph.nodes[n].get("type") == "Service"
            and cls._kg.graph.nodes[n].get("venue_id") == venue_id
            and service_type.lower() in cls._kg.graph.nodes[n].get("service_type","").lower()
        ]
        return {"services": services, "count": len(services)}

    @classmethod
    def search_venue_entities(cls, venue_id: str, keyword: str) -> dict:
        """Full-text search across venue knowledge graph nodes."""
        if not cls._kg:
            return {"results": []}
        results = cls._kg.search_nodes(keyword)
        venue_results = [r for r in results if r.get("venue_id") == venue_id]
        return {"results": venue_results[:10], "total": len(venue_results)}


class CrowdMCPServer:
    """In-process MCP tool server for real-time crowd data."""
    import random as _random

    @classmethod
    def start(cls) -> None:
        log.info("CrowdMCPServer started")

    @classmethod
    def stop(cls) -> None:
        pass

    @classmethod
    def call(cls, tool_name: str, **kwargs) -> dict:
        import random
        if tool_name == "get_crowd_density":
            venue_id = kwargs.get("venue_id","met")
            zone_id  = kwargs.get("zone_id","north")
            density  = random.randint(20,99)
            return {"venue_id":venue_id,"zone_id":zone_id,"density_pct":density,
                    "status": "low" if density<50 else "medium" if density<75 else "high" if density<90 else "critical",
                    "timestamp":"2026-07-16T07:00:00Z"}
        if tool_name == "get_bottleneck_predictions":
            return {"predictions":[
                {"zone":"Gate D concourse","density_predicted":87,"eta_min":15,"severity":"high"},
                {"zone":"North concession","density_predicted":72,"eta_min":30,"severity":"medium"},
            ]}
        if tool_name == "get_safe_routes":
            return {"safe_routes":["Gate E → Section 12","Gate A → Accessible concourse","Gate B → East stand"]}
        return {"error": f"Unknown crowd tool: {tool_name}"}


class TransportMCPServer:
    """In-process MCP tool server for transport data."""

    @classmethod
    def start(cls) -> None:
        log.info("TransportMCPServer started")

    @classmethod
    def stop(cls) -> None:
        pass

    @classmethod
    def call(cls, tool_name: str, **kwargs) -> dict:
        import random
        if tool_name == "get_transport_options":
            return {"options":[
                {"mode":"metro","wait_min":random.randint(4,15),"load_pct":random.randint(30,95),"recommended":True},
                {"mode":"shuttle","wait_min":random.randint(5,20),"load_pct":random.randint(25,85),"recommended":False},
                {"mode":"taxi","wait_min":random.randint(8,35),"surge":round(random.uniform(1.0,3.5),1),"recommended":False},
            ]}
        if tool_name == "get_parking_availability":
            return {"zones":{"A":random.randint(60,100),"B":random.randint(30,80),"C":random.randint(10,60),"D":random.randint(5,40)}}
        if tool_name == "get_post_match_routes":
            return {"dispersal_plan":{"phase1":"Sections A-C exit first (T+0 to T+15)","phase2":"Sections D-F (T+15 to T+30)","metro_surge":"Expected T+10 to T+40","recommended":"Metro Line 2 or shuttle Zone D"}}
        return {"error": f"Unknown transport tool: {tool_name}"}


class EcoMCPServer:
    """In-process MCP tool server for sustainability data."""

    @classmethod
    def start(cls) -> None:
        log.info("EcoMCPServer started")

    @classmethod
    def stop(cls) -> None:
        pass

    @classmethod
    def call(cls, tool_name: str, **kwargs) -> dict:
        if tool_name == "calculate_carbon_footprint":
            factors = {"flight":0.255,"car_petrol":0.171,"metro":0.041,"bus":0.089,"shuttle":0.072,"walk":0.0}
            mode  = kwargs.get("transport","metro")
            dist  = kwargs.get("distance",25.0)
            group = kwargs.get("group_size",1)
            co2   = factors.get(mode,0.1) * dist
            return {"co2_kg":round(co2,2),"transport":mode,"distance_km":dist,"eco_score":max(0,int(100-(co2/20)*100))}
        if tool_name == "get_venue_eco_stats":
            return {"solar_kwh_today":4200,"waste_diverted_pct":78,"water_saved_litres":12000,"co2_avoided_kg":2100,"eco_rating":"A"}
        if tool_name == "get_eco_recommendations":
            return {"tips":["Take metro — saves 75% vs car","Choose veggie meal — saves 2.7kg CO₂","Use refill water stations","Return waste to colour-coded bins"]}
        return {"error": f"Unknown eco tool: {tool_name}"}
