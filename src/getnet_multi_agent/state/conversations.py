"""Conversations, turns and rolling summaries."""

import json
import uuid

from getnet_multi_agent.state.db import Database, dumps, now_iso


def create_conversation(db: Database, owner_sub: str) -> str:
    cid = str(uuid.uuid4())
    with db.conn() as c:
        c.execute(
            "INSERT INTO conversations (id, owner_sub, created_at) VALUES (?, ?, ?)",
            (cid, owner_sub, now_iso()),
        )
    return cid


def get_conversation(db: Database, conversation_id: str, owner_sub: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT id, owner_sub, created_at FROM conversations WHERE id = ? AND owner_sub = ?",
            (conversation_id, owner_sub),
        ).fetchone()
    return dict(row) if row else None


def append_turn(
    db: Database,
    conversation_id: str,
    role: str,
    text: str,
    route: str | None = None,
    status: str | None = None,
    sources: list | None = None,
    request_id: str | None = None,
) -> int:
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO turns (conversation_id, role, text, route, status, sources_json,"
            " request_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id, role, text, route, status,
                dumps(sources) if sources is not None else None, request_id, now_iso(),
            ),
        )
        return int(cur.lastrowid)


def _turn(row) -> dict:
    d = dict(row)
    d["sources"] = json.loads(d.pop("sources_json") or "[]")
    return d


_COLS = "id, role, text, route, status, sources_json, request_id, created_at"


def list_turns(db: Database, conversation_id: str) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM turns WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
    return [_turn(r) for r in rows]


def last_turns(db: Database, conversation_id: str, n: int) -> list[dict]:
    with db.conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM turns WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, n),
        ).fetchall()
    return [_turn(r) for r in reversed(rows)]


def get_summary(db: Database, conversation_id: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT text, last_turn_id, updated_at FROM summaries WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
    return dict(row) if row else None


def save_summary(db: Database, conversation_id: str, text: str, last_turn_id: int) -> None:
    with db.conn() as c:
        c.execute(
            "INSERT INTO summaries (conversation_id, text, last_turn_id, updated_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT(conversation_id) DO UPDATE SET"
            " text = excluded.text, last_turn_id = excluded.last_turn_id,"
            " updated_at = excluded.updated_at",
            (conversation_id, text, last_turn_id, now_iso()),
        )
