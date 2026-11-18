"""Hybrid retrieval: vector + BM25 + knowledge graph, fused and re-ranked.

Modes (used by the evaluation to compare approaches):
- "vector":   plain dense retrieval, the classic RAG baseline.
- "hybrid":   vector + BM25 fused with Reciprocal Rank Fusion, then cross-encoder re-ranking.
- "graphrag": hybrid + graph traversal. Chunks behind the best graph paths join the fusion
              as a third ranked list, and the graph facts themselves go to the LLM.
"""

import logging
import math
import threading
import time
from dataclasses import dataclass, field

from .bm25 import BM25
from .graph_retriever import GraphFact, GraphRetriever

log = logging.getLogger(__name__)

MODES = ("vector", "hybrid", "graphrag")


@dataclass
class RetrievedChunk:
    id: str
    doc_id: str
    doc_title: str
    text: str
    section: str | None
    page: int | None
    score: float
    sources: list[str] = field(default_factory=list)  # which retrievers found it


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    facts: list[GraphFact]
    seeds: list[dict]
    mode: str
    timings: dict
    top_relevance: float  # 0..1 re-ranker confidence for the best chunk


def rrf(ranked_lists: list[list[str]], weights: list[float], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for lst, w in zip(ranked_lists, weights):
        for rank, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
    return scores


class Reranker:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    self._model = TextCrossEncoder(self.model_name)
        return [float(s) for s in self._model.rerank(query, texts)]


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class HybridRetriever:
    def __init__(self, db, embedder, vectors, graph_store, reranker: Reranker | None, settings):
        self.db = db
        self.embedder = embedder
        self.vectors = vectors
        self.graph = GraphRetriever(graph_store, embedder, hops=settings.graph_hops)
        self.reranker = reranker
        self.settings = settings
        self.bm25 = BM25()
        self.chunks: dict[str, dict] = {}
        self.refresh()

    def refresh(self):
        """Reload the chunk table and rebuild the keyword index (after ingestion/deletion)."""
        rows = self.db.all_chunks()
        self.chunks = {r["id"]: r for r in rows}
        self.bm25.fit([r["id"] for r in rows], [r["text"] for r in rows])

    def _make(self, cid: str, score: float, sources: list[str]) -> RetrievedChunk | None:
        r = self.chunks.get(cid)
        if not r:
            return None
        return RetrievedChunk(cid, r["doc_id"], r["doc_title"], r["text"], r["section"], r["page"], score, sources)

    def retrieve(self, question: str, mode: str = "graphrag", k: int | None = None) -> RetrievalResult:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        k = k or self.settings.top_k
        t0 = time.perf_counter()
        timings = {}
        qvec = self.embedder.embed_query(question)
        vec_hits = [h for h in self.vectors.search(qvec, 20) if h[0] in self.chunks]
        timings["vector_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        if mode == "vector":
            chunks = [self._make(cid, s, ["vector"]) for cid, s in vec_hits[:k]]
            chunks = [c for c in chunks if c]
            top_rel = self._relevance(question, chunks[:1])
            timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return RetrievalResult(chunks, [], [], mode, timings, top_rel)

        t1 = time.perf_counter()
        bm_hits = self.bm25.search(question, 20)
        timings["bm25_ms"] = round((time.perf_counter() - t1) * 1000, 1)

        lists = [[c for c, _ in vec_hits], [c for c, _ in bm_hits]]
        weights = [1.0, 1.0]
        found_by: dict[str, list[str]] = {}
        for name, lst in zip(("vector", "keyword"), lists):
            for c in lst:
                found_by.setdefault(c, []).append(name)

        facts, seeds, graph_ids = [], [], []
        if mode == "graphrag":
            t2 = time.perf_counter()
            gres = self.graph.retrieve(question, qvec)
            timings["graph_ms"] = round((time.perf_counter() - t2) * 1000, 1)
            facts, seeds = gres.facts, gres.seeds
            graph_ids = [c for c, _ in gres.chunk_scores if c in self.chunks]
            lists.append(graph_ids)
            weights.append(1.0)
            for c in graph_ids:
                found_by.setdefault(c, []).append("graph")

        fused = rrf(lists, weights)
        candidates = sorted(fused, key=lambda c: -fused[c])[: self.settings.rerank_candidates]

        # Re-ranking: blend the cross-encoder's relevance with the fused rank, so one weak
        # re-ranker score cannot throw away a chunk that every retriever agreed on.
        t3 = time.perf_counter()
        rerank_scores: dict[str, float] = {}
        final: dict[str, float] = {}
        if self.reranker and self.settings.use_reranker and candidates:
            # Cross-encoder cost grows with length; the first 600 characters carry the topic.
            texts = [self.chunks[c]["text"][:600] for c in candidates]
            for c, s in zip(candidates, self.reranker.score(question, texts)):
                rerank_scores[c] = s
            top_fused = max(fused[c] for c in candidates)
            w = self.settings.rerank_weight
            for c in candidates:
                final[c] = w * sigmoid(rerank_scores[c]) + (1 - w) * fused[c] / top_fused
        else:
            final = {c: fused[c] for c in candidates}
        ordered = sorted(candidates, key=lambda c: -final[c])
        timings["rerank_ms"] = round((time.perf_counter() - t3) * 1000, 1)

        selected = ordered[:k]

        chunks = []
        for c in selected:
            score = final.get(c, 0.0)
            rc = self._make(c, round(score, 4), found_by.get(c, []))
            if rc:
                chunks.append(rc)
        top_rel = max((sigmoid(rerank_scores[c]) for c in selected if c in rerank_scores), default=self._relevance(question, chunks[:1]))
        timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return RetrievalResult(chunks, facts[:15], seeds, mode, timings, top_rel)

    def _relevance(self, question: str, chunks: list[RetrievedChunk]) -> float:
        if not chunks:
            return 0.0
        if self.reranker and self.settings.use_reranker:
            return sigmoid(self.reranker.score(question, [chunks[0].text])[0])
        return float(chunks[0].score)
