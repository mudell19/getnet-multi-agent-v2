import threading
import time

import pytest

from getnet_multi_agent.state import audit, checkpoints, conversations, tickets
from getnet_multi_agent.state.db import connect


def _new_ticket(db, owner="alice", reason="low confidence"):
    cid = conversations.create_conversation(db, owner)
    cp = checkpoints.save_checkpoint(db, cid, "req-1", {"plan": ["a"], "lang": "pt"})
    return cid, cp, tickets.open_ticket(db, cid, cp, owner, reason)


def test_fr_041_open_ticket_and_checkpoint_round_trip(settings):
    db = connect(settings)
    cid, cp, tid = _new_ticket(db)
    t = tickets.get_ticket(db, tid)
    assert (t.status, t.conversation_id, t.owner_sub, t.reason) == (
        "open", cid, "alice", "low confidence")
    assert t.claimed_by is None and t.resolution is None
    loaded = checkpoints.load_checkpoint(db, cp)
    assert loaded["state"] == {"plan": ["a"], "lang": "pt"}
    assert loaded["conversation_id"] == cid and loaded["request_id"] == "req-1"
    assert checkpoints.load_checkpoint(db, "nope") is None
    assert tickets.get_ticket(db, "nope") is None


def test_fr_043_concurrent_claim_single_winner(settings):
    db = connect(settings)
    _, _, tid = _new_ticket(db)
    barrier = threading.Barrier(2)
    results = []

    def worker(op):
        barrier.wait()
        try:
            tickets.claim(db, tid, op)
            results.append(("ok", op))
        except tickets.AlreadyClaimed:
            results.append(("conflict", op))

    threads = [threading.Thread(target=worker, args=(f"op{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r[0] for r in results) == ["conflict", "ok"]
    winner = next(op for r, op in results if r == "ok")
    assert tickets.get_ticket(db, tid).claimed_by == winner


def test_fr_043_claim_resolved_or_missing(settings):
    db = connect(settings)
    _, _, tid = _new_ticket(db)
    tickets.claim(db, tid, "op1")
    tickets.resolve(db, tid, "op1", "approve", {"text": "ok"})
    with pytest.raises(tickets.AlreadyClaimed):
        tickets.claim(db, tid, "op2")
    with pytest.raises(tickets.TicketNotFound):
        tickets.claim(db, "missing", "op1")


def test_fr_044_resolve_rules(settings):
    db = connect(settings)
    _, _, t1 = _new_ticket(db)
    with pytest.raises(tickets.NotClaimant):  # still open
        tickets.resolve(db, t1, "op1", "approve", {})
    tickets.claim(db, t1, "op1")
    with pytest.raises(tickets.NotClaimant):
        tickets.resolve(db, t1, "op2", "approve", {})
    with pytest.raises(tickets.TicketNotFound):
        tickets.resolve(db, "missing", "op1", "approve", {})
    done = tickets.resolve(db, t1, "op1", "approve", {"text": "final"})
    assert done.status == "resolved" and done.resolution == {"text": "final"}
    assert tickets.get_ticket(db, t1).resolution == {"text": "final"}
    with pytest.raises(tickets.NotClaimant):  # cannot resolve twice
        tickets.resolve(db, t1, "op1", "approve", {})

    _, _, t2 = _new_ticket(db)
    tickets.claim(db, t2, "op1")
    rej = tickets.resolve(db, t2, "op1", "reject", {"reason": "wrong"})
    assert rej.status == "rejected" and rej.resolution == {"reason": "wrong"}


def test_fr_045_audit_recorded_per_ticket(settings):
    db = connect(settings)
    _, _, t1 = _new_ticket(db)
    _, _, t2 = _new_ticket(db)
    audit.record(db, t1, "pseud-sys", "escalated", {"reason": "x"})
    audit.record(db, t1, "pseud-op", "claimed")
    audit.record(db, t2, "pseud-sys", "escalated")
    entries = audit.list_audit(db, t1)
    assert [e["action"] for e in entries] == ["escalated", "claimed"]
    assert entries[0]["detail"] == {"reason": "x"} and entries[1]["detail"] is None
    assert entries[0]["actor"] == "pseud-sys"
    assert len(audit.list_audit(db)) == 3


def test_fr_042_list_tickets_filters_by_status(settings):
    db = connect(settings)
    ids = [_new_ticket(db)[2] for _ in range(3)]
    tickets.claim(db, ids[1], "op1")
    assert [t.id for t in tickets.list_tickets(db)] == ids
    assert [t.id for t in tickets.list_tickets(db, "open")] == [ids[0], ids[2]]
    assert [t.id for t in tickets.list_tickets(db, "claimed")] == [ids[1]]
    assert tickets.list_tickets(db, "resolved") == []


def test_fr_042_open_stats_count_and_age(settings):
    db = connect(settings)
    assert tickets.open_stats(db) == (0, 0.0)
    _, _, t1 = _new_ticket(db)
    _new_ticket(db)
    time.sleep(0.05)
    n, age = tickets.open_stats(db)
    assert n == 2 and age >= 0.05
    tickets.claim(db, t1, "op1")
    assert tickets.open_stats(db)[0] == 2
    tickets.resolve(db, t1, "op1", "approve", {})
    assert tickets.open_stats(db)[0] == 1
