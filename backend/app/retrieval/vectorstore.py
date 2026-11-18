"""A small persistent vector index (NumPy, cosine similarity).

For a single company's documents (thousands of chunks) an exact NumPy search
takes about a millisecond, so a separate vector database adds operations work
without improving results. The interface is small on purpose, so it can be
swapped for Qdrant or pgvector if the corpus grows to millions of chunks.
"""

import json
import threading
from pathlib import Path

import numpy as np


class VectorStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.ids: list[str] = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self._load()

    def _load(self):
        meta, mat = self.path.with_suffix(".json"), self.path.with_suffix(".npy")
        if meta.exists() and mat.exists():
            self.ids = json.loads(meta.read_text())
            self.matrix = np.load(mat)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.path.with_suffix(".npy"), self.matrix)
        self.path.with_suffix(".json").write_text(json.dumps(self.ids))

    def __len__(self):
        return len(self.ids)

    def add(self, ids: list[str], vectors: np.ndarray):
        if not ids:
            return
        with self._lock:
            if self.matrix.size == 0:
                self.matrix = vectors.astype(np.float32)
            else:
                self.matrix = np.vstack([self.matrix, vectors.astype(np.float32)])
            self.ids.extend(ids)
            self._save()

    def remove(self, ids: set[str]):
        with self._lock:
            keep = [i for i, cid in enumerate(self.ids) if cid not in ids]
            self.ids = [self.ids[i] for i in keep]
            self.matrix = self.matrix[keep] if keep else np.zeros((0, 0), dtype=np.float32)
            self._save()

    def clear(self):
        with self._lock:
            self.ids, self.matrix = [], np.zeros((0, 0), dtype=np.float32)
            self._save()

    def search(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        with self._lock:
            if not self.ids:
                return []
            scores = self.matrix @ query_vec
            k = min(k, len(self.ids))
            top = np.argpartition(-scores, k - 1)[:k]
            top = top[np.argsort(-scores[top])]
            return [(self.ids[i], float(scores[i])) for i in top]
