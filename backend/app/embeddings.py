"""Local text embeddings with FastEmbed (ONNX, CPU-only, no API key needed).

BGE models work best when queries carry an instruction prefix, which
FastEmbed's query_embed adds for us.
"""

import hashlib
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self.dim = None

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    log.info("Loading embedding model %s", self.model_name)
                    self._model = TextEmbedding(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim or 384), dtype=np.float32)
        vecs = np.array(list(self._load().embed(texts, batch_size=32)), dtype=np.float32)
        self.dim = vecs.shape[1]
        return _normalize(vecs)

    def embed_query(self, text: str) -> np.ndarray:
        vec = np.array(list(self._load().query_embed(text))[0], dtype=np.float32)
        self.dim = vec.shape[0]
        return _normalize(vec[None, :])[0]


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder, used in unit tests."""

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.model_name = "hash"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in text.lower().split():
            tok = "".join(ch for ch in tok if ch.isalnum())
            if tok:
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return v

    def embed_documents(self, texts):
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalize(np.stack([self._vec(t) for t in texts]))

    def embed_query(self, text):
        return _normalize(self._vec(text)[None, :])[0]


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms
