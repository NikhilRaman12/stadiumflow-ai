"""
GraphRAG Knowledge Graph Builder — StadiumIQ
=============================================
Builds a rich NetworkX knowledge graph of stadium entities and
relationships for use by the GraphRAG retrieval pipeline.

Nodes : Venue · Zone · Gate · Service · Staff · Incident · Transport · Match
Edges : HAS_ZONE · HAS_GATE · CONNECTS_TO · HAS_SERVICE · MANAGES ·
        OCCURRED_IN · ROUTES_TO · ACCESSIBLE_VIA · HOSTS
"""
from __future__ import annotations

import json
import os
import asyncio
import logging
from pathlib import Path
from typing import Any

import networkx as nx

log = logging.getLogger("stadiumiq.graphrag")

DATA_DIR = Path(__file__).parent.parent / "data"


class StadiumKnowledgeGraph:
    """
    Builds and maintains a NetworkX DiGraph representing all FIFA WC 2026
    stadium knowledge. Each node carries rich attribute dicts that are used
    both for graph traversal (structural RAG) and as text chunks (semantic RAG).
    """

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()

    # ── Public API ────────────────────────────────────────────────────

    async def build(self) -> None:
        """Load data files and populate the knowledge graph."""
        log.info("Building StadiumIQ Knowledge Graph …")
        stadiums = self._load_json("stadiums.json")
        matches  = self._load_json("matches.json")

        for venue in stadiums:
            self._add_venue(venue)

        for match in matches:
            self._add_match(match)

        self._add_synthetic_staff()
        self._add_transport_nodes()
        self._add_service_nodes()

        log.info(
            "KG ready — %d nodes / %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    def get_subgraph(self, node_ids: list[str], hops: int = 1) -> nx.DiGraph:
        """Return neighbourhood subgraph around given node IDs (BFS up to `hops`)."""
        seeds = set(node_ids) & set(self.graph.nodes)
        visited: set[str] = set()
        frontier = set(seeds)
        for _ in range(hops):
            next_frontier: set[str] = set()
            for n in frontier:
                next_frontier.update(self.graph.predecessors(n))
                next_frontier.update(self.graph.successors(n))
            frontier = next_frontier - visited
            visited.update(next_frontier)
        return self.graph.subgraph(seeds | visited).copy()

    def search_nodes(self, keyword: str, node_type: str | None = None) -> list[dict]:
        """Simple keyword search over node text attributes."""
        results = []
        kw = keyword.lower()
        for nid, attrs in self.graph.nodes(data=True):
            if node_type and attrs.get("type") != node_type:
                continue
            text = json.dumps(attrs).lower()
            if kw in text:
                results.append({"id": nid, **attrs})
        return results

    def to_text_chunks(self) -> list[dict[str, str]]:
        """Convert every node to a text chunk for vector indexing."""
        chunks = []
        for nid, attrs in self.graph.nodes(data=True):
            text = self._node_to_text(nid, attrs)
            chunks.append({"id": nid, "text": text, "type": attrs.get("type", "unknown")})
        # Also add edge-relationship chunks
        for src, dst, attrs in self.graph.edges(data=True):
            rel   = attrs.get("relation", "RELATED_TO")
            src_a = self.graph.nodes[src]
            dst_a = self.graph.nodes[dst]
            text  = (
                f"{src_a.get('name', src)} {rel.replace('_',' ').lower()} "
                f"{dst_a.get('name', dst)}. "
            )
            chunks.append({"id": f"{src}_{rel}_{dst}", "text": text, "type": "relation"})
        return chunks

    # ── Private builders ──────────────────────────────────────────────

    def _add_venue(self, v: dict) -> None:
        vid = f"venue:{v['id']}"
        self.graph.add_node(vid, type="Venue", **v,
            text_summary=(
                f"{v['name']} in {v['city']}, {v['country']}. "
                f"Capacity: {v['capacity']:,}. "
                f"Gates: {', '.join(v.get('gates', []))}. "
                f"Accessible gates: {', '.join(v.get('accessible_gates', []))}. "
                f"Medical stations: {v.get('medical_stations', 0)}. "
                f"Eco features: {'; '.join(v.get('eco_features', []))}."
            )
        )
        for zone in v.get("zones", []):
            zid = f"zone:{v['id']}:{zone['id']}"
            self.graph.add_node(zid, type="Zone", venue_id=v['id'], **zone,
                text_summary=(
                    f"Zone '{zone['name']}' in {v['name']}. "
                    f"Capacity: {zone['capacity']:,}. Level: {zone['level']}."
                )
            )
            self.graph.add_edge(vid, zid, relation="HAS_ZONE")

        for gate in v.get("gates", []):
            gid = f"gate:{v['id']}:{gate}"
            accessible = gate in v.get("accessible_gates", [])
            self.graph.add_node(gid, type="Gate", name=f"Gate {gate}",
                venue_id=v['id'], accessible=accessible,
                text_summary=(
                    f"Gate {gate} at {v['name']}. "
                    f"Wheelchair accessible: {'Yes' if accessible else 'No'}."
                )
            )
            self.graph.add_edge(vid, gid, relation="HAS_GATE")

        transport = v.get("transport", {})
        for mode, detail in transport.items():
            if mode == "parking_zones":
                continue
            tid = f"transport:{v['id']}:{mode}"
            self.graph.add_node(tid, type="Transport", mode=mode, detail=detail,
                venue_id=v['id'],
                text_summary=f"{mode.upper()} transport to {v['name']}: {detail}."
            )
            self.graph.add_edge(tid, vid, relation="ROUTES_TO")

    def _add_match(self, m: dict) -> None:
        mid = f"match:{m['id']}"
        vid = f"venue:{m['venue_id']}"
        self.graph.add_node(mid, type="Match", **m,
            text_summary=(
                f"Match {m.get('home','')} vs {m.get('away','')} on {m.get('date','')} "
                f"at {m.get('venue_name','')}. Kick-off: {m.get('time','')}. "
                f"Stage: {m.get('stage','')}."
            )
        )
        if vid in self.graph:
            self.graph.add_edge(vid, mid, relation="HOSTS")

    def _add_synthetic_staff(self) -> None:
        roles = ["Security Lead", "Medical Coordinator", "Crowd Manager",
                 "Accessibility Officer", "Transport Liaison", "Sustainability Officer"]
        for venue_id in ["met", "dal", "la", "atz", "bc", "sf"]:
            for i, role in enumerate(roles):
                sid = f"staff:{venue_id}:{i}"
                self.graph.add_node(sid, type="Staff", role=role,
                    venue_id=venue_id, shift="Match Day",
                    text_summary=f"{role} at venue {venue_id}. Available on match days."
                )
                vid = f"venue:{venue_id}"
                if vid in self.graph:
                    self.graph.add_edge(sid, vid, relation="MANAGES")

    def _add_transport_nodes(self) -> None:
        shared = [
            {"id": "metro_nyc",  "mode": "metro",   "name": "NJ Transit Meadowlands Line",  "venue_id": "met"},
            {"id": "shuttle_la", "mode": "shuttle",  "name": "SoFi Stadium Shuttle Service", "venue_id": "la"},
            {"id": "metro_mx",   "mode": "metro",    "name": "Metro CDMX Línea 2",           "venue_id": "atz"},
            {"id": "skytrain_bc","mode": "skytrain", "name": "SkyTrain Expo Line",            "venue_id": "bc"},
        ]
        for t in shared:
            tid = f"transport:shared:{t['id']}"
            vid = f"venue:{t['venue_id']}"
            self.graph.add_node(tid, type="Transport", **t,
                text_summary=f"{t['name']} serves {t['venue_id']} stadium via {t['mode']}."
            )
            self.graph.add_edge(tid, vid, relation="ROUTES_TO")

    def _add_service_nodes(self) -> None:
        service_types = [
            "First Aid", "Lost & Found", "Fan Services", "Concessions",
            "Restrooms", "Merchandise", "ATM", "Prayer Room",
        ]
        for venue_id in ["met", "dal", "la", "atz", "bc", "sf"]:
            vid = f"venue:{venue_id}"
            for i, stype in enumerate(service_types):
                sid = f"service:{venue_id}:{i}"
                self.graph.add_node(sid, type="Service", service_type=stype,
                    venue_id=venue_id, location=f"Gate A, Level {(i % 3) + 1}",
                    text_summary=(
                        f"{stype} service at {venue_id} stadium. "
                        f"Location: Gate A, Level {(i % 3) + 1}."
                    )
                )
                if vid in self.graph:
                    self.graph.add_edge(vid, sid, relation="HAS_SERVICE")

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _load_json(filename: str) -> list[dict]:
        path = DATA_DIR / filename
        if not path.exists():
            log.warning("Data file not found: %s", path)
            return []
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def _node_to_text(node_id: str, attrs: dict) -> str:
        if "text_summary" in attrs:
            return attrs["text_summary"]
        parts = [f"ID: {node_id}", f"Type: {attrs.get('type', 'unknown')}"]
        for k, v in attrs.items():
            if k not in ("type", "text_summary") and isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}: {v}")
        return ". ".join(str(p) for p in parts)
