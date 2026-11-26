"""Escalation checkpoints: the agent state needed to resume after human review."""

import json
import uuid

from getnet_multi_agent.state.db import Database, dumps, now_iso


def save_checkpoint(db: Database, conversation_id: str, request_id: str, state: dict) -> str:
    cp_id = str(uuid.uuid4())
    with db.conn() as c:
        c.execute(
            "INSERT INTO checkpoints (id, conversation_id, request_id, state_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (cp_id, conversation_id, request_id, dumps(state), now_iso()),
        )
    return cp_id


def load_checkpoint(db: Database, checkpoint_id: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT id, conversation_id, request_id, state_json, created_at"
            " FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["state"] = json.loads(d.pop("state_json"))
    return d
