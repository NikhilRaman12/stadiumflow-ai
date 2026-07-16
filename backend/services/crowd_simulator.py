"""
Services: CrowdSimulator, TransportOptimizer, IncidentManager
===============================================================
Real-time simulation engines for crowd, transport, and incident data.
"""
import random, math, uuid
from datetime import datetime
from typing import Optional


class CrowdSimulator:
    """Simulates realistic crowd density for all venues."""

    VENUES = ["met","dal","la","atz","bc","sf"]
    ZONES  = ["north","south","east","west","field","upper"]

    def __init__(self):
        self._state = {v: {z: {"density": random.randint(20,65), "flow": random.randint(200,600)}
                           for z in self.ZONES} for v in self.VENUES}
        self._tick_count = 0

    def tick(self) -> dict:
        self._tick_count += 1
        updates = {}
        for venue in self.VENUES:
            updates[venue] = {}
            for zone in self.ZONES:
                cur = self._state[venue][zone]["density"]
                delta = random.randint(-5, 8)    # Slightly upward trend pre-match
                new_density = max(5, min(100, cur + delta))
                self._state[venue][zone]["density"] = new_density
                self._state[venue][zone]["flow"]    = random.randint(100, 900)
                updates[venue][zone] = {"density": new_density, "flow": self._state[venue][zone]["flow"]}
        return {"tick": self._tick_count, "venues": updates, "ts": datetime.utcnow().isoformat()}

    def get_full_state(self) -> dict:
        return {"venues": self._state, "tick": self._tick_count, "ts": datetime.utcnow().isoformat()}

    def get_venue_state(self, venue_id: str) -> dict:
        zones = self._state.get(venue_id, {z: {"density":50,"flow":400} for z in self.ZONES})
        densities = [v["density"] for v in zones.values()]
        avg  = sum(densities) / len(densities) if densities else 50
        risk = "LOW" if avg<50 else "MEDIUM" if avg<75 else "HIGH" if avg<90 else "CRITICAL"
        return {"venue_id":venue_id,"zones":zones,"avg_density":round(avg,1),"risk_level":risk,"ts":datetime.utcnow().isoformat()}

    def get_kpis(self) -> dict:
        all_d = [z["density"] for v in self._state.values() for z in v.values()]
        avg   = sum(all_d)/len(all_d) if all_d else 50
        return {"avg_density_pct": round(avg,1), "max_density_pct": max(all_d,default=0),
                "venues_at_high_risk": sum(1 for v in self.VENUES if self.get_venue_state(v)["risk_level"] in ("HIGH","CRITICAL"))}


class TransportOptimizer:
    """Simulates transport system state for all venues."""

    def __init__(self):
        self._state = {
            "shuttle":    {"wait_min":8, "load_pct":55, "active_routes":12},
            "metro":      {"wait_min":10,"load_pct":62, "lines_active":3},
            "parking":    {"zone_a":82, "zone_b":61, "zone_c":38, "zone_d":22},
            "taxi_surge": 1.4,
        }
        self._tick = 0

    def tick(self) -> dict:
        self._tick += 1
        self._state["shuttle"]["wait_min"]  = max(2, self._state["shuttle"]["wait_min"] + random.randint(-2,3))
        self._state["shuttle"]["load_pct"]  = min(100, max(20, self._state["shuttle"]["load_pct"] + random.randint(-3,5)))
        self._state["metro"]["wait_min"]    = max(3, self._state["metro"]["wait_min"] + random.randint(-2,4))
        self._state["metro"]["load_pct"]    = min(100, max(25, self._state["metro"]["load_pct"] + random.randint(-4,6)))
        self._state["parking"]["zone_a"]    = min(100, self._state["parking"]["zone_a"] + random.randint(0,3))
        self._state["taxi_surge"]           = round(max(1.0, self._state["taxi_surge"] + random.uniform(-0.1,0.15)), 1)
        return {"tick":self._tick, **self._state, "ts":datetime.utcnow().isoformat()}

    def get_full_state(self) -> dict:
        return {**self._state, "tick":self._tick, "ts":datetime.utcnow().isoformat()}

    def get_kpis(self) -> dict:
        return {"shuttle_wait_min": self._state["shuttle"]["wait_min"],
                "metro_wait_min":   self._state["metro"]["wait_min"],
                "parking_a_pct":    self._state["parking"]["zone_a"],
                "taxi_surge":       self._state["taxi_surge"]}


class IncidentManager:
    """Manages incident lifecycle: create, update, resolve."""

    def __init__(self):
        self._incidents: dict[str, dict] = {}

    def create_incident(self, data: dict) -> dict:
        iid = data.get("id", str(uuid.uuid4())[:8].upper())
        self._incidents[iid] = {**data, "id": iid, "status":"OPEN",
                                "created_at":datetime.utcnow().isoformat()}
        return self._incidents[iid]

    def resolve(self, incident_id: str) -> bool:
        if incident_id in self._incidents:
            self._incidents[incident_id]["status"]      = "RESOLVED"
            self._incidents[incident_id]["resolved_at"] = datetime.utcnow().isoformat()
            return True
        return False

    def get_active(self, venue_id: Optional[str] = None) -> list:
        active = [i for i in self._incidents.values() if i["status"] == "OPEN"]
        if venue_id:
            active = [i for i in active if i.get("venue_id") == venue_id]
        return active

    def get_kpis(self) -> dict:
        return {"open":    len([i for i in self._incidents.values() if i["status"]=="OPEN"]),
                "resolved":len([i for i in self._incidents.values() if i["status"]=="RESOLVED"]),
                "total":   len(self._incidents)}
