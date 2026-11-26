from getnet_multi_agent.contracts import Plan

HUMAN = {"message": "I want to talk to a human agent", "user_id": "cliente1988"}


def escalate(client, auth):
    client.fake.responses["router"] = Plan(standalone="human", lang="en", escalate_reason="human_requested")
    d = client.post("/chat", json=HUMAN, headers=auth()).json()
    assert d["status"] == "awaiting_human" and d["route"] == "escalation" and d["ticket_id"]
    return d


def test_fr_042_list_tickets_by_status_operator_only(client, auth):
    d = escalate(client, auth)
    r = client.get("/operator/tickets?status=open", headers=auth("op1", "operator"))
    assert [t["id"] for t in r.json()["tickets"]] == [d["ticket_id"]]
    assert client.get("/operator/tickets", headers=auth()).status_code == 403


def test_fr_043_claim_is_atomic(client, auth):
    d = escalate(client, auth)
    op = auth("op1", "operator")
    assert client.post(f"/operator/tickets/{d['ticket_id']}/claim", headers=op).json()["status"] == "claimed"
    r = client.post(f"/operator/tickets/{d['ticket_id']}/claim", headers=auth("op2", "operator"))
    assert r.status_code == 409
    assert client.post("/operator/tickets/nope/claim", headers=op).status_code == 404


def test_fr_044_fr_045_resolve_edit_appends_to_conversation_with_audit(client, auth):
    from getnet_multi_agent.state import audit

    d = escalate(client, auth)
    op = auth("op1", "operator")
    tid = d["ticket_id"]
    assert client.post(f"/operator/tickets/{tid}/resolve", json={"action": "edit", "text": "x"},
                       headers=op).status_code == 409  # not claimed yet
    client.post(f"/operator/tickets/{tid}/claim", headers=op)
    r = client.post(f"/operator/tickets/{tid}/resolve",
                    json={"action": "edit", "text": "A specialist will call you today."}, headers=op)
    assert r.status_code == 200 and r.json()["ticket"]["status"] == "resolved"
    turns = client.get(f"/conversations/{d['conversation_id']}", headers=auth()).json()["turns"]
    assert "specialist will call you" in turns[-1]["text"]
    actions = [a["action"] for a in audit.list_audit(client.app.state.db, tid)]
    assert actions == ["escalated", "claimed", "edit"]


def test_fr_044_reject_and_approve(client, auth):
    op = auth("op1", "operator")
    d = escalate(client, auth)
    client.post(f"/operator/tickets/{d['ticket_id']}/claim", headers=op)
    r = client.post(f"/operator/tickets/{d['ticket_id']}/resolve",
                    json={"action": "reject", "text": "Not possible."}, headers=op)
    assert r.json()["ticket"]["status"] == "rejected" and "Not possible." in r.json()["turn"]["text"]
    d = escalate(client, auth)
    client.post(f"/operator/tickets/{d['ticket_id']}/claim", headers=op)
    r = client.post(f"/operator/tickets/{d['ticket_id']}/resolve",
                    json={"action": "approve", "text": "Approved answer."}, headers=op)
    assert r.json()["ticket"]["status"] == "resolved"


def test_fr_051_retrieval_endpoint(client, auth, monkeypatch):
    from getnet_multi_agent.api import operator

    from .conftest import CHUNK

    monkeypatch.setattr(operator, "retrieve", lambda s, llm, q, mode, k: [CHUNK])
    r = client.get("/operator/retrieval", params={"q": "payment link", "mode": "vector"},
                   headers=auth("op1", "operator"))
    assert r.json()["chunks"][0]["rank"] == 1 and r.json()["chunks"][0]["url"] == CHUNK.url
