"""Human-review tickets: open -> claimed -> resolved | rejected, with atomic guarded updates."""

import json
import uuid
from datetime import datetime

from getnet_multi_agent.contracts import Ticket
from getnet_multi_agent.state.db import Database, dumps, now_iso


class TicketNotFound(Exception):
    pass


class AlreadyClaimed(Exception):
    pass


class NotClaimant(Exception):
    pass


_COLS = (
    "id, conversation_id, owner_sub, reason, status, claimed_by, resolution_json,"
    " created_at, updated_at"
)


def _ticket(row) -> Ticket:
    d = dict(row)
    raw = d.pop("resolution_json")
    d["resolution"] = json.loads(raw) if raw else None
    return Ticket.model_validate(d)


def open_ticket(
    db: Database, conversation_id: str, checkpoint_id: str, owner_sub: str, reason: str
) -> str:
    tid, now = str(uuid.uuid4()), now_iso()
    with db.conn() as c:
        c.execute(
            "INSERT INTO tickets (id, conversation_id, checkpoint_id, owner_sub, reason, status,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
            (tid, conversation_id, checkpoint_id, owner_sub, reason, now, now),
        )
    return tid


def get_ticket(db: Database, ticket_id: str) -> Ticket | None:
    with db.conn() as c:
        row = c.execute(f"SELECT {_COLS} FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return _ticket(row) if row else None


def list_tickets(db: Database, status: str | None = None) -> list[Ticket]:
    sql, args = f"SELECT {_COLS} FROM tickets", ()
    if status is not None:
        sql, args = sql + " WHERE status = ?", (status,)
    with db.conn() as c:
        rows = c.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
    return [_ticket(r) for r in rows]


def claim(db: Database, ticket_id: str, operator_sub: str) -> Ticket:
    with db.conn() as c:
        cur = c.execute(
            "UPDATE tickets SET status='claimed', claimed_by=?, updated_at=?"
            " WHERE id=? AND status='open'",
            (operator_sub, now_iso(), ticket_id),
        )
        if cur.rowcount == 0:
            exists = c.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            raise AlreadyClaimed(ticket_id) if exists else TicketNotFound(ticket_id)
    return get_ticket(db, ticket_id)


def resolve(
    db: Database, ticket_id: str, operator_sub: str, action: str, resolution: dict
) -> Ticket:
    status = "rejected" if action == "reject" else "resolved"
    with db.conn() as c:
        cur = c.execute(
            "UPDATE tickets SET status=?, resolution_json=?, updated_at=?"
            " WHERE id=? AND status='claimed' AND claimed_by=?",
            (status, dumps(resolution), now_iso(), ticket_id, operator_sub),
        )
        if cur.rowcount == 0:
            exists = c.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            raise NotClaimant(ticket_id) if exists else TicketNotFound(ticket_id)
    return get_ticket(db, ticket_id)


def open_stats(db: Database) -> tuple[int, float]:
    with db.conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n, MIN(created_at) AS oldest FROM tickets"
            " WHERE status IN ('open', 'claimed')"
        ).fetchone()
    if not row["n"]:
        return 0, 0.0
    age = (datetime.fromisoformat(now_iso()) - datetime.fromisoformat(row["oldest"])).total_seconds()
    return int(row["n"]), max(age, 0.0)
