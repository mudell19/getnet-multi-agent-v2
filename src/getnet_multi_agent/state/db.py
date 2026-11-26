"""SQLite state store: one connection per call (thread-safe under FastAPI's threadpool), WAL."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, owner_sub TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'operator')),
    text TEXT NOT NULL, route TEXT, status TEXT, sources_json TEXT, request_id TEXT,
    created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns(conversation_id, id);
CREATE TABLE IF NOT EXISTS summaries (
    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id),
    text TEXT NOT NULL, last_turn_id INTEGER NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, request_id TEXT NOT NULL,
    state_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, checkpoint_id TEXT NOT NULL,
    owner_sub TEXT NOT NULL, reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'claimed', 'resolved', 'rejected')),
    claimed_by TEXT, resolution_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('escalated', 'claimed', 'approve', 'edit', 'reject')),
    detail_json TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_audit_ticket ON audit(ticket_id, id);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            yield c
        finally:
            c.close()

    def init_schema(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)

    def ping(self) -> bool:
        try:
            with self.conn() as c:
                c.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False


def connect(settings) -> Database:
    db = Database(settings.state_path / "app.db")
    db.init_schema()
    return db
