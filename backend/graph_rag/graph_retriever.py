"""
GraphRAG Retriever — StadiumIQ
===============================
Two-stage retrieval:
  1. Semantic  — FAISS vector search over node text chunks
  2. Structural — NetworkX BFS to expand retrieved nodes into
                  a meaningful subgraph (community context)

Returns rich, graph-structured context strings for LLM prompting.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import networkx as nx
import numpy as np

log = logging.getLogger("stadiumiq.graphrag")

try:
    import faiss
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    log.warning("faiss-cpu or langchain-google-genai not installed — falling back to keyword retrieval")


class GraphRAGRetriever:
    """
    GraphRAG retrieval pipeline:
      query  →  entity extraction  →  semantic FAISS search
             →  BFS subgraph expansion  →  context string
    """

    def __init__(self, kg) -> None:
        self.kg      = kg
        self.index   = None           # FAISS index
        self.chunks: list[dict] = []  # text chunks with metadata
        self.embedder = None

    # ── Indexing ──────────────────────────────────────────────────────

    async def build_index(self) -> None:
        """Embed all graph nodes and build FAISS index."""
        self.chunks = self.kg.to_text_chunks()

        if not FAISS_AVAILABLE or not os.getenv("GEMINI_API_KEY"):
            log.warning("FAISS unavailable or no API key — keyword-only retrieval active")
            return

        try:
            self.embedder = GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=os.getenv("GEMINI_API_KEY"),
            )
            texts = [c["text"] for c in self.chunks]
            log.info("Embedding %d graph chunks …", len(texts))

            # Batch embed (avoid rate limits)
            all_vecs: list[list[float]] = []
            batch_size = 50
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                vecs  = await asyncio.to_thread(self.embedder.embed_documents, batch)
                all_vecs.extend(vecs)
                if i + batch_size < len(texts):
                    await asyncio.sleep(0.5)   # rate-limit pause

            mat = np.array(all_vecs, dtype="float32")
            dim = mat.shape[1]
            self.index = faiss.IndexFlatIP(dim)          # inner-product similarity
            faiss.normalize_L2(mat)
            self.index.add(mat)
            log.info("FAISS index built — %d vectors, dim=%d", self.index.ntotal, dim)
        except Exception as e:
            log.error("FAISS index build failed: %s", e)
            self.index = None

    # ── Query ─────────────────────────────────────────────────────────

    async def retrieve(self, query: str, top_k: int = 8, hops: int = 1) -> str:
        """
        Retrieve graph-structured context for `query`.
        Returns a formatted context string suitable for LLM prompting.
        """
        if self.index is not None and self.embedder:
            node_ids = await self._semantic_search(query, top_k)
        else:
            node_ids = self._keyword_search(query, top_k)

        if not node_ids:
            return "No specific stadium context found for this query."

        # Expand with BFS subgraph
        subgraph = self.kg.get_subgraph(node_ids, hops=hops)
        context  = self._subgraph_to_context(subgraph, seed_ids=node_ids)
        return context

    async def retrieve_for_venue(self, venue_id: str, query: str, top_k: int = 6) -> str:
        """Venue-scoped retrieval — only nodes belonging to the given venue."""
        base_ctx = await self.retrieve(query, top_k=top_k)
        # Add venue-specific node directly
        vid  = f"venue:{venue_id}"
        if vid in self.kg.graph:
            attrs = self.kg.graph.nodes[vid]
            venue_text = attrs.get("text_summary", "")
            return f"[Venue: {attrs.get('name','?')}]\n{venue_text}\n\n{base_ctx}"
        return base_ctx

    # ── Internal ──────────────────────────────────────────────────────

    async def _semantic_search(self, query: str, top_k: int) -> list[str]:
        try:
            q_vec = await asyncio.to_thread(self.embedder.embed_query, query)
            q_arr = np.array([q_vec], dtype="float32")
            faiss.normalize_L2(q_arr)
            _, indices = self.index.search(q_arr, top_k)
            return [self.chunks[i]["id"] for i in indices[0] if 0 <= i < len(self.chunks)]
        except Exception as e:
            log.error("Semantic search failed: %s", e)
            return self._keyword_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int) -> list[str]:
        """Fallback: simple TF-like keyword matching over chunk texts."""
        kws    = query.lower().split()
        scored: list[tuple[float, str]] = []
        for chunk in self.chunks:
            text  = chunk["text"].lower()
            score = sum(text.count(kw) for kw in kws)
            if score > 0:
                scored.append((score, chunk["id"]))
        scored.sort(reverse=True)
        return [cid for _, cid in scored[:top_k]]

    @staticmethod
    def _subgraph_to_context(sg: nx.DiGraph, seed_ids: list[str]) -> str:
        """Serialize a subgraph into a readable context block for the LLM."""
        lines: list[str] = ["=== STADIUM KNOWLEDGE GRAPH CONTEXT ==="]

        # Seed nodes first (most relevant)
        lines.append("\n[Directly Relevant Nodes]")
        for nid in seed_ids:
            if nid in sg:
                a = sg.nodes[nid]
                lines.append(f"• [{a.get('type','?')}] {a.get('text_summary', nid)}")

        # Relationships
        rel_lines: list[str] = []
        for src, dst, attrs in sg.edges(data=True):
            rel  = attrs.get("relation", "RELATED_TO")
            sn   = sg.nodes[src].get("name", src)
            dn   = sg.nodes[dst].get("name", dst)
            rel_lines.append(f"  {sn} --[{rel}]--> {dn}")
        if rel_lines:
            lines.append("\n[Relationships]")
            lines.extend(rel_lines[:20])   # cap at 20 to keep context concise

        # Neighbouring context nodes
        lines.append("\n[Related Context]")
        for nid, attrs in sg.nodes(data=True):
            if nid in seed_ids:
                continue
            lines.append(f"• [{attrs.get('type','?')}] {attrs.get('text_summary', nid)}")

        return "\n".join(lines)
