"""Wires all components together and handles one customer message end to end."""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict

from .answer import HUMAN, Answer, Answerer, small_talk
from .config import Settings
from .db import Database
from .embeddings import Embedder, HashEmbedder
from .graph.extractor import HeuristicExtractor, LLMExtractor
from .graph.store import GraphStore
from .ingestion.pipeline import IngestionPipeline
from .llm import LLM
from .retrieval.hybrid import HybridRetriever, Reranker
from .retrieval.vectorstore import VectorStore

log = logging.getLogger(__name__)

RESET = {"reset", "restart", "start over", "/reset"}
RESUME = {"bot", "/bot"}
HANDOVER_TEXT = (
    "Thanks, I've passed your conversation to our customer care team. A team member will reply "
    "here soon (Mon-Sat, 9 AM - 6 PM). Reply *bot* any time to chat with me again."
)


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            q = self.events[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


class Services:
    def __init__(self, settings: Settings, embedder=None):
        self.settings = settings
        d = settings.data_dir
        self.db = Database(d / "app.db")
        if embedder is None:
            embedder = HashEmbedder() if settings.embedding_model == "hash" else Embedder(settings.embedding_model)
        self.embedder = embedder
        self.vectors = VectorStore(d / "vectors")
        self.graph = GraphStore(d / "graph.json")
        self.llm = LLM(settings)
        # The Gemini free tier allows few requests per minute, so extract with fewer parallel calls.
        workers = 2 if self.llm.provider == "gemini" else 4
        self.extractor = LLMExtractor(self.llm, workers=workers) if self.llm.enabled else HeuristicExtractor()
        self.reranker = Reranker(settings.reranker_model) if settings.use_reranker else None
        self.retriever = HybridRetriever(self.db, self.embedder, self.vectors, self.graph, self.reranker, settings)
        self.pipeline = IngestionPipeline(self.db, self.embedder, self.vectors, self.graph, self.extractor, settings, on_change=self.retriever.refresh)
        self.answerer = Answerer(self.llm, settings)
        self.limiter = RateLimiter(settings.rate_limit_per_minute)
        self.ingest_lock = threading.Lock()

    def warm_up(self):
        t0 = time.time()
        try:
            qvec = self.embedder.embed_query("opening hours")
            self.graph.node_vectors(self.embedder)
            if self.reranker:
                self.reranker.score("opening hours", ["We are open from 9 to 5."])
            self.retriever.graph.retrieve("opening hours", qvec)
            log.info("Warm-up finished in %.1fs", time.time() - t0)
        except Exception:
            log.exception("Warm-up failed")

    # ----------------------------------------------------------------------
    def ask(self, question: str, history: list[dict] | None = None, mode: str = "graphrag") -> dict:
        """Retrieval + answer without touching conversation state (used by eval and test chat)."""
        history = history or []
        standalone = self.answerer.standalone(question, history)
        res = self.retriever.retrieve(standalone, mode=mode)
        ans = self.answerer.answer(standalone, res, history)
        ans.standalone_question = standalone
        return {"answer": ans, "retrieval": res}

    def handle_message(self, phone: str, text: str, channel: str = "whatsapp", mode: str = "graphrag") -> dict:
        """Process an incoming customer message. Returns the reply (or None) plus debug info."""
        text = (text or "").strip()
        lower = text.lower()
        if not text:
            return {"reply": "Sorry, I can only read text messages for now. Please type your question.", "debug": None}

        if not self.limiter.allow(phone):
            return {"reply": "You're sending messages very quickly. Please wait a minute and try again.", "debug": None}

        if lower in RESET:
            self.db.clear_history(phone)
            self.db.set_handover(phone, False)
            return self._reply(phone, channel, "Done, I've started a fresh conversation. How can I help?", None, store_user=None)

        if lower in RESUME:
            self.db.set_handover(phone, False)
            self.db.add_message(phone, "user", text, channel)
            return self._reply(phone, channel, "I'm back! What would you like to know?", None)

        if self.db.handover_active(phone):
            # A human agent owns this conversation now; just log the message.
            self.db.add_message(phone, "user", text, channel, {"handover": True})
            return {"reply": None, "debug": {"handover": True}}

        history = self.db.history(phone, self.settings.memory_turns * 2)
        self.db.add_message(phone, "user", text, channel)

        if HUMAN.search(text) and len(text.split()) <= 12:
            self.db.set_handover(phone, True)
            self.db.add_unanswered(phone, text, "customer asked for a human")
            return self._reply(phone, channel, HANDOVER_TEXT, {"kind": "handover"}, store_user=False)

        st = small_talk(text, self.settings.company_name)
        if st:
            return self._reply(phone, channel, st.text, {"kind": "smalltalk"}, store_user=False)

        out = self.ask(text, history, mode)
        ans: Answer = out["answer"]
        res = out["retrieval"]
        if not ans.answerable:
            self.db.add_unanswered(phone, text, "not found in documents")
        elif ans.needs_human:
            self.db.add_unanswered(phone, text, "model suggested a human")

        reply = format_whatsapp(ans)
        debug = {
            "kind": ans.kind,
            "answerable": ans.answerable,
            "needs_human": ans.needs_human,
            "standalone_question": ans.standalone_question,
            "citations": ans.citations,
            "mode": res.mode,
            "seeds": res.seeds,
            "facts": [f.as_text() for f in res.facts[:10]],
            "chunks": [
                {"id": c.id, "title": c.doc_title, "section": c.section, "page": c.page, "score": c.score, "found_by": c.sources, "text": c.text[:400]}
                for c in res.chunks
            ],
            "timings": res.timings,
            "top_relevance": round(res.top_relevance, 3),
            "llm": self.llm.enabled,
        }
        return self._reply(phone, channel, reply, debug, store_user=False)

    def _reply(self, phone, channel, reply, debug, store_user=None):
        self.db.add_message(phone, "assistant", reply, channel, debug)
        return {"reply": reply, "debug": debug}

    def status(self) -> dict:
        return {
            "company": self.settings.company_name,
            "llm_enabled": self.llm.enabled,
            "llm_provider": self.llm.provider,
            "llm_model": self.llm.model,
            "extractor": self.extractor.name,
            "embedding_model": self.embedder.model_name,
            "reranker": self.settings.reranker_model if self.reranker else None,
            "whatsapp_provider": self.settings.whatsapp_provider,
            "whatsapp_dry_run": self.settings.whatsapp_dry_run,
            "llm_usage": self.llm.usage,
            **self.db.stats(),
            "graph": self.graph.stats(),
        }


def format_whatsapp(ans: Answer, limit: int = 1500) -> str:
    text = ans.text
    if ans.citations:
        seen, labels = set(), []
        for c in ans.citations:
            label = c["title"] + (f" p.{c['page']}" if c.get("page") else "")
            if label not in seen:
                seen.add(label)
                labels.append(f"[{c['n']}] {label}")
        text += "\n\n_Sources: " + "; ".join(labels) + "_"
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def answer_to_dict(ans: Answer) -> dict:
    return asdict(ans)
