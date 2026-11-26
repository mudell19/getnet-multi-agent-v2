"""Append-only audit trail of ticket actions (actor is already a pseudonym)."""

import json

from getnet_multi_agent.state.db import Database, dumps, now_iso


def record(
    db: Database, ticket_id: str, actor: str, action: str, detail: dict | None = None
) -> int:
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO audit (ticket_id, actor, action, detail_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (ticket_id, actor, action, dumps(detail) if detail is not None else None, now_iso()),
        )
        return int(cur.lastrowid)


def list_audit(db: Database, ticket_id: str | None = None) -> list[dict]:
    sql = "SELECT id, ticket_id, actor, action, detail_json, created_at FROM audit"
    args: tuple = ()
    if ticket_id is not None:
        sql += " WHERE ticket_id = ?"
        args = (ticket_id,)
    with db.conn() as c:
        rows = c.execute(sql + " ORDER BY id", args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        raw = d.pop("detail_json")
        d["detail"] = json.loads(raw) if raw else None
        out.append(d)
    return out
