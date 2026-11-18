"""Okapi BM25 keyword search. Catches exact terms (model numbers, prices,
branch names) that dense embeddings sometimes blur together."""

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
STOPWORDS = set(
    "a an the and or of to in on at for is are was were be been do does did can could i you we "
    "your my our it its this that these those with from by as what which who whom how when where "
    "why will would should please tell me about any have has there their them they us".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.ids: list[str] = []
        self.docs: list[Counter] = []
        self.lengths: list[int] = []
        self.df: Counter = Counter()
        self.avgdl = 0.0

    def fit(self, ids: list[str], texts: list[str]):
        self.ids = list(ids)
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.df = Counter()
        for d in self.docs:
            self.df.update(d.keys())
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        n = len(self.ids)
        q = tokenize(query)
        scores = []
        for i, doc in enumerate(self.docs):
            s = 0.0
            for term in q:
                tf = doc.get(term)
                if not tf:
                    continue
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                denom = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avgdl or 1))
                s += idf * tf * (self.k1 + 1) / denom
            if s > 0:
                scores.append((self.ids[i], s))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]
