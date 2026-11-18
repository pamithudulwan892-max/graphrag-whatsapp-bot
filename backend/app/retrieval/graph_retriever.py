"""Graph retrieval: link the question to entities, then walk the graph.

1. Entity linking: match entity names/aliases that appear in the question,
   plus the entities whose embeddings are closest to the question.
2. Personalized PageRank from those seed entities ranks the neighbourhood,
   so facts two hops away (product -> warranty plan -> warranty length) are found.
3. The best edges become "graph facts", and the chunks they came from are
   returned as a ranked list for fusion with vector and keyword search.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

import networkx as nx
import numpy as np

from ..graph.store import GraphStore, norm_key
from .bm25 import tokenize


@dataclass
class GraphFact:
    source: str
    relation: str
    target: str
    description: str
    chunk_id: str
    score: float

    def as_text(self) -> str:
        rel = self.relation.replace("_", " ").lower()
        base = f"{self.source} --{rel}--> {self.target}"
        return f"{base}: {self.description}" if self.description else base


@dataclass
class GraphResult:
    seeds: list[dict]
    facts: list[GraphFact]
    chunk_scores: list[tuple[str, float]]


def personalized_pagerank(g: nx.Graph, personalization: dict, alpha: float = 0.75, iters: int = 100, tol: float = 1e-8) -> dict:
    """Random walk that restarts at the question's entities with probability 1 - alpha.

    Written with NumPy because networkx.pagerank needs SciPy, a large extra dependency.
    """
    nodes = list(g.nodes)
    if not nodes:
        return {}
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    adj = np.zeros((n, n), dtype=np.float64)
    for u, v in g.edges():
        adj[idx[u], idx[v]] = adj[idx[v], idx[u]] = 1.0
    deg = adj.sum(axis=1)
    trans = np.divide(adj, deg[:, None], out=np.zeros_like(adj), where=deg[:, None] > 0)
    restart = np.array([personalization.get(x, 0.0) for x in nodes], dtype=np.float64)
    restart = restart / restart.sum() if restart.sum() > 0 else np.full(n, 1 / n)
    dangling = deg == 0
    p = restart.copy()
    for _ in range(iters):
        nxt = alpha * (p @ trans + p[dangling].sum() * restart) + (1 - alpha) * restart
        if np.abs(nxt - p).sum() < tol:
            p = nxt
            break
        p = nxt
    return {x: float(p[i]) for i, x in enumerate(nodes)}


class GraphRetriever:
    def __init__(self, store: GraphStore, embedder, hops: int = 2):
        self.store = store
        self.embedder = embedder
        self.hops = hops

    def link_entities(self, question: str, query_vec: np.ndarray | None, max_seeds: int = 6) -> dict[str, float]:
        g = self.store.g
        q_norm = f" {norm_key(question)} "
        q_tokens = set(tokenize(question))
        seeds: dict[str, float] = {}

        # Lexical matches on names and aliases.
        names = [(k, g.nodes[k]["name"]) for k in g.nodes]
        names += [(k, a) for a, k in self.store.alias_index.items() if k in g]
        for key, name in names:
            nk = norm_key(name)
            if len(nk) < 3:
                continue
            if f" {nk} " in q_norm:
                seeds[key] = max(seeds.get(key, 0), 1.0 + 0.05 * len(nk.split()))
                continue
            toks = set(tokenize(name))
            if len(toks) >= 2:
                overlap = len(toks & q_tokens) / len(toks)
                if overlap >= 0.67:
                    seeds[key] = max(seeds.get(key, 0), 0.6 * overlap)

        # Semantic matches on entity descriptions.
        if query_vec is not None and g.number_of_nodes():
            ids, mat = self.store.node_vectors(self.embedder)
            sims = mat @ query_vec
            for i in np.argsort(-sims)[:max_seeds]:
                if sims[i] >= 0.62:
                    seeds[ids[i]] = max(seeds.get(ids[i], 0), float(sims[i]) * 0.8)

        # Prefer specific entities: down-weight hubs such as the company name.
        for k in list(seeds):
            seeds[k] /= 1 + 0.15 * math.log1p(g.degree(k))
        return dict(sorted(seeds.items(), key=lambda x: -x[1])[:max_seeds])

    def retrieve(self, question: str, query_vec: np.ndarray | None, k_facts: int = 20, k_chunks: int = 20) -> GraphResult:
        g = self.store.g
        if g.number_of_nodes() == 0:
            return GraphResult([], [], [])
        seeds = self.link_entities(question, query_vec)
        if not seeds:
            return GraphResult([], [], [])

        # Neighbourhood within `hops` of any seed.
        ug = g.to_undirected(as_view=True)
        hood = set()
        for s in seeds:
            hood.update(nx.single_source_shortest_path_length(ug, s, cutoff=self.hops).keys())
        sub = nx.Graph(ug.subgraph(hood))
        total = sum(seeds.values())
        personalization = {n: seeds.get(n, 0.0) / total for n in sub.nodes}
        ppr = personalized_pagerank(sub, personalization, alpha=0.75)

        facts: list[GraphFact] = []
        seen = set()
        for u, v, d in g.subgraph(hood).edges(data=True):
            key = (u, v, d["relation"], d.get("chunk_id"))
            if key in seen:
                continue
            seen.add(key)
            bonus = 1.5 if (u in seeds or v in seeds) else 1.0
            score = (ppr.get(u, 0) + ppr.get(v, 0)) * bonus
            facts.append(GraphFact(g.nodes[u]["name"], d["relation"], g.nodes[v]["name"], d.get("description", ""), d.get("chunk_id"), score))
        facts.sort(key=lambda f: -f.score)
        facts = facts[:k_facts]

        chunk_scores: dict[str, float] = defaultdict(float)
        for f in facts:
            if f.chunk_id:
                chunk_scores[f.chunk_id] += f.score
        for n, score in sorted(ppr.items(), key=lambda x: -x[1])[:15]:
            for cid in g.nodes[n]["chunk_ids"]:
                chunk_scores[cid] += 0.3 * score

        seed_info = [{"id": k, "name": g.nodes[k]["name"], "type": g.nodes[k]["type"], "score": round(v, 3)} for k, v in seeds.items()]
        ranked = sorted(chunk_scores.items(), key=lambda x: -x[1])[:k_chunks]
        return GraphResult(seed_info, facts, ranked)
