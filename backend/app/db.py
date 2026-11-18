"""SQLite storage for documents, chunks, conversations, unanswered questions and the outbox."""

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    error TEXT,
    n_chunks INTEGER DEFAULT 0,
    n_entities INTEGER DEFAULT 0,
    n_relations INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    section TEXT,
    page INTEGER
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'whatsapp',
    meta TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_phone ON messages(phone, id);
CREATE TABLE IF NOT EXISTS unanswered (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    question TEXT NOT NULL,
    reason TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    to_number TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_events (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS handovers (
    phone TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # Documents -------------------------------------------------------------
    def create_document(self, title: str, source: str, kind: str) -> str:
        doc_id = uuid.uuid4().hex[:12]
        with self.tx() as c:
            c.execute(
                "INSERT INTO documents (id, title, source, kind, created_at) VALUES (?,?,?,?,?)",
                (doc_id, title, source, kind, time.time()),
            )
        return doc_id

    def update_document(self, doc_id: str, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))

    def list_documents(self) -> list[dict]:
        return self.query("SELECT * FROM documents ORDER BY created_at DESC")

    def get_document(self, doc_id: str) -> dict | None:
        return self.one("SELECT * FROM documents WHERE id = ?", (doc_id,))

    def delete_document(self, doc_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def insert_chunks(self, rows: list[dict]) -> None:
        with self.tx() as c:
            c.executemany(
                "INSERT INTO chunks (id, doc_id, idx, text, section, page) VALUES (:id,:doc_id,:idx,:text,:section,:page)",
                rows,
            )

    def all_chunks(self) -> list[dict]:
        return self.query(
            "SELECT c.*, d.title AS doc_title FROM chunks c JOIN documents d ON d.id = c.doc_id "
            "WHERE d.status = 'ready' ORDER BY c.doc_id, c.idx"
        )

    def doc_chunks(self, doc_id: str) -> list[dict]:
        return self.query("SELECT * FROM chunks WHERE doc_id = ? ORDER BY idx", (doc_id,))

    # Conversations ---------------------------------------------------------
    def add_message(self, phone: str, role: str, text: str, channel: str = "whatsapp", meta: dict | None = None):
        with self.tx() as c:
            c.execute(
                "INSERT INTO messages (phone, role, text, channel, meta, created_at) VALUES (?,?,?,?,?,?)",
                (phone, role, text, channel, json.dumps(meta) if meta else None, time.time()),
            )

    def history(self, phone: str, limit: int) -> list[dict]:
        rows = self.query(
            "SELECT role, text, created_at FROM messages WHERE phone = ? ORDER BY id DESC LIMIT ?",
            (phone, limit),
        )
        return list(reversed(rows))

    def clear_history(self, phone: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM messages WHERE phone = ?", (phone,))

    def conversations(self) -> list[dict]:
        return self.query(
            "SELECT phone, channel, COUNT(*) AS n_messages, MAX(created_at) AS last_at, "
            "(SELECT text FROM messages m2 WHERE m2.phone = m.phone ORDER BY id DESC LIMIT 1) AS last_text "
            "FROM messages m GROUP BY phone ORDER BY last_at DESC"
        )

    def conversation(self, phone: str) -> list[dict]:
        rows = self.query("SELECT * FROM messages WHERE phone = ? ORDER BY id", (phone,))
        for r in rows:
            r["meta"] = json.loads(r["meta"]) if r["meta"] else None
        return rows

    # Unanswered / handover -------------------------------------------------
    def add_unanswered(self, phone: str, question: str, reason: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO unanswered (phone, question, reason, created_at) VALUES (?,?,?,?)",
                (phone, question, reason, time.time()),
            )

    def list_unanswered(self) -> list[dict]:
        return self.query("SELECT * FROM unanswered ORDER BY resolved, created_at DESC")

    def resolve_unanswered(self, item_id: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE unanswered SET resolved = 1 WHERE id = ?", (item_id,))

    def set_handover(self, phone: str, active: bool) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO handovers (phone, active, created_at) VALUES (?,?,?) "
                "ON CONFLICT(phone) DO UPDATE SET active = excluded.active, created_at = excluded.created_at",
                (phone, int(active), time.time()),
            )

    def handover_active(self, phone: str) -> bool:
        row = self.one("SELECT active FROM handovers WHERE phone = ?", (phone,))
        return bool(row and row["active"])

    def list_handovers(self) -> list[dict]:
        return self.query("SELECT * FROM handovers WHERE active = 1 ORDER BY created_at DESC")

    # Outbox / idempotency --------------------------------------------------
    def add_outbox(self, provider: str, to: str, text: str, status: str, detail: str = "") -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO outbox (provider, to_number, text, status, detail, created_at) VALUES (?,?,?,?,?,?)",
                (provider, to, text, status, detail, time.time()),
            )

    def list_outbox(self, limit: int = 100) -> list[dict]:
        return self.query("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,))

    def seen_event(self, event_id: str) -> bool:
        """Return True if the event was already processed; otherwise record it."""
        with self.tx() as c:
            try:
                c.execute("INSERT INTO processed_events (id, created_at) VALUES (?, ?)", (event_id, time.time()))
                return False
            except sqlite3.IntegrityError:
                return True

    def stats(self) -> dict:
        def count(sql):
            return self.one(sql)["n"]

        return {
            "documents": count("SELECT COUNT(*) AS n FROM documents WHERE status = 'ready'"),
            "chunks": count("SELECT COUNT(*) AS n FROM chunks"),
            "conversations": count("SELECT COUNT(DISTINCT phone) AS n FROM messages"),
            "messages": count("SELECT COUNT(*) AS n FROM messages"),
            "unanswered_open": count("SELECT COUNT(*) AS n FROM unanswered WHERE resolved = 0"),
            "handovers_active": count("SELECT COUNT(*) AS n FROM handovers WHERE active = 1"),
        }
