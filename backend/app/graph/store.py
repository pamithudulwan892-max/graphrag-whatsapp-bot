"""Knowledge graph store built on NetworkX, persisted as JSON.

Nodes are entities, merged by a normalized name key (entity resolution).
Edges are relations; every edge remembers the chunk it came from, so a graph
fact can always be cited back to the source document.
"""

import json
import re
import threading
from pathlib import Path

import networkx as nx
import numpy as np

from .extractor import Extraction

_SUFFIXES = re.compile(r"\b(?:\(pvt\)|pvt|ltd|limited|inc|plc|co)\b\.?", re.I)


def norm_key(name: str) -> str:
    s = name.lower().replace("’", "'")
    s = _SUFFIXES.sub(" ", s)
    s = re.sub(r"^(?:the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9.,:+@ ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,")
    return s


class GraphStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.g = nx.MultiDiGraph()
        self.alias_index: dict[str, str] = {}
        self._node_vecs: np.ndarray | None = None
        self._node_ids: list[str] = []
        self._load()

    # Persistence -----------------------------------------------------------
    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.g = nx.node_link_graph(data["graph"], directed=True, multigraph=True, edges="edges")
            for n, attrs in self.g.nodes(data=True):
                attrs["chunk_ids"] = set(attrs.get("chunk_ids", []))
                attrs["doc_ids"] = set(attrs.get("doc_ids", []))
            self.alias_index = data.get("aliases", {})

    def save(self):
        with self._lock:
            g = self.g.copy()
            for _, attrs in g.nodes(data=True):
                attrs["chunk_ids"] = sorted(attrs["chunk_ids"])
                attrs["doc_ids"] = sorted(attrs["doc_ids"])
            data = {"graph": nx.node_link_data(g, edges="edges"), "aliases": self.alias_index}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.path)

    # Building --------------------------------------------------------------
    def resolve(self, name: str) -> str | None:
        key = norm_key(name)
        if key in self.g:
            return key
        return self.alias_index.get(key)

    def _upsert_node(self, name: str, etype: str, description: str, chunk_id: str, doc_id: str) -> str:
        key = self.resolve(name) or norm_key(name)
        if not key:
            return ""
        if key not in self.g:
            self.g.add_node(key, name=name, type=etype, descriptions=[], chunk_ids=set(), doc_ids=set())
        node = self.g.nodes[key]
        if node["type"] in ("Other", "") and etype not in ("Other", ""):
            node["type"] = etype
        if len(name) > len(node["name"]) and norm_key(name) == key:
            node["name"] = name
        if description and description not in node["descriptions"] and len(node["descriptions"]) < 5:
            node["descriptions"].append(description)
        node["chunk_ids"].add(chunk_id)
        node["doc_ids"].add(doc_id)
        return key

    def add_extractions(self, doc_id: str, extractions: list[Extraction]) -> tuple[int, int]:
        n_ents, n_rels = 0, 0
        with self._lock:
            for ex in extractions:
                local: dict[str, str] = {}
                for e in ex.entities:
                    key = self._upsert_node(e.name, e.type, e.description, ex.chunk_id, doc_id)
                    if not key:
                        continue
                    local[e.name.lower()] = key
                    for alias in e.aliases:
                        ak = norm_key(alias)
                        if ak and ak != key and ak not in self.g:
                            self.alias_index[ak] = key
                        local[alias.lower()] = key
                    n_ents += 1
                for r in ex.relations:
                    s = local.get(r.source.lower()) or self.resolve(r.source)
                    t = local.get(r.target.lower()) or self.resolve(r.target)
                    if not s or not t or s == t:
                        continue
                    self.g.add_edge(s, t, relation=r.relation, description=r.description, chunk_id=ex.chunk_id, doc_id=doc_id)
                    n_rels += 1
            self._node_vecs = None
        return n_ents, n_rels

    def remove_document(self, doc_id: str):
        with self._lock:
            drop = [(u, v, k) for u, v, k, d in self.g.edges(keys=True, data=True) if d.get("doc_id") == doc_id]
            self.g.remove_edges_from(drop)
            for n in list(self.g.nodes):
                attrs = self.g.nodes[n]
                attrs["doc_ids"].discard(doc_id)
                if not attrs["doc_ids"]:
                    self.g.remove_node(n)
            self.alias_index = {a: k for a, k in self.alias_index.items() if k in self.g}
            self._node_vecs = None
            self.save()

    def remove_chunks(self, chunk_ids: set[str]):
        with self._lock:
            for n in self.g.nodes:
                self.g.nodes[n]["chunk_ids"] -= chunk_ids

    def clear(self):
        with self._lock:
            self.g.clear()
            self.alias_index = {}
            self._node_vecs = None
            self.save()

    # Queries ---------------------------------------------------------------
    def node_text(self, key: str) -> str:
        n = self.g.nodes[key]
        desc = n["descriptions"][0] if n["descriptions"] else ""
        return f"{n['name']} ({n['type']}). {desc}"

    def node_vectors(self, embedder) -> tuple[list[str], np.ndarray]:
        with self._lock:
            if self._node_vecs is None or len(self._node_ids) != self.g.number_of_nodes():
                self._node_ids = list(self.g.nodes)
                texts = [self.node_text(k) for k in self._node_ids]
                self._node_vecs = embedder.embed_documents(texts) if texts else np.zeros((0, 1), dtype=np.float32)
            return self._node_ids, self._node_vecs

    def stats(self) -> dict:
        types: dict[str, int] = {}
        for _, d in self.g.nodes(data=True):
            types[d["type"]] = types.get(d["type"], 0) + 1
        rels: dict[str, int] = {}
        for _, _, d in self.g.edges(data=True):
            rels[d["relation"]] = rels.get(d["relation"], 0) + 1
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "entity_types": dict(sorted(types.items(), key=lambda x: -x[1])),
            "relation_types": dict(sorted(rels.items(), key=lambda x: -x[1])[:25]),
        }

    def export(self, limit: int = 600, doc_id: str | None = None, search: str | None = None) -> dict:
        """Nodes and links for the dashboard's force-directed view."""
        with self._lock:
            nodes = list(self.g.nodes)
            if doc_id:
                nodes = [n for n in nodes if doc_id in self.g.nodes[n]["doc_ids"]]
            if search:
                q = search.lower()
                hits = [n for n in nodes if q in self.g.nodes[n]["name"].lower()]
                around = set(hits)
                for h in hits:
                    around.update(self.g.successors(h))
                    around.update(self.g.predecessors(h))
                nodes = [n for n in nodes if n in around]
            nodes = sorted(nodes, key=lambda n: -self.g.degree(n))[:limit]
            keep = set(nodes)
            links = []
            seen = set()
            for u, v, d in self.g.edges(data=True):
                if u in keep and v in keep and (u, v, d["relation"]) not in seen:
                    seen.add((u, v, d["relation"]))
                    links.append({"source": u, "target": v, "relation": d["relation"], "description": d["description"]})
            return {
                "nodes": [
                    {
                        "id": n,
                        "name": self.g.nodes[n]["name"],
                        "type": self.g.nodes[n]["type"],
                        "description": (self.g.nodes[n]["descriptions"] or [""])[0],
                        "degree": self.g.degree(n),
                    }
                    for n in nodes
                ],
                "links": links,
            }
