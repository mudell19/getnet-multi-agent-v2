"""Operator routes: ticket queue (list, atomic claim, resolve) and retrieval inspection."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from getnet_multi_agent.agents.escalation import resume
from getnet_multi_agent.contracts import Principal
from getnet_multi_agent.core import metrics
from getnet_multi_agent.rag.retriever import retrieve
from getnet_multi_agent.security import guardrails
from getnet_multi_agent.security.auth import require_operator
from getnet_multi_agent.security.pseudonym import pseudonym
from getnet_multi_agent.state import audit, tickets
from getnet_multi_agent.state import conversations as conv

router = APIRouter(prefix="/operator")


class ResolveRequest(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str = ""


def _not_found():
    return HTTPException(404, detail={"code": "not_found", "message": "ticket not found"})


@router.get("/tickets")
def list_tickets(request: Request, status: Literal["open", "claimed", "resolved", "rejected"] | None = None,
                 principal: Principal = Depends(require_operator)):
    return {"tickets": [t.model_dump(mode="json") for t in tickets.list_tickets(request.app.state.db, status)]}


@router.post("/tickets/{ticket_id}/claim")
def claim(ticket_id: str, request: Request, principal: Principal = Depends(require_operator)):
    db = request.app.state.db
    try:
        t = tickets.claim(db, ticket_id, principal.sub)
    except tickets.TicketNotFound as e:
        raise _not_found() from e
    except tickets.AlreadyClaimed as e:
        raise HTTPException(409, detail={"code": "conflict", "message": "ticket already claimed"}) from e
    audit.record(db, ticket_id, pseudonym(principal.sub, request.app.state.settings), "claimed")
    return t.model_dump(mode="json")


@router.post("/tickets/{ticket_id}/resolve")
def resolve(ticket_id: str, body: ResolveRequest, request: Request,
            principal: Principal = Depends(require_operator)):
    app = request.app
    db = app.state.db
    if body.action in ("edit", "reject") and not body.text.strip():
        raise HTTPException(422, detail={"code": "validation_error", "message": "text is required for edit and reject"})
    ticket = tickets.get_ticket(db, ticket_id)
    if ticket is None:
        raise _not_found()
    if ticket.status != "claimed" or ticket.claimed_by != principal.sub:
        raise HTTPException(409, detail={"code": "conflict", "message": "ticket must be claimed by you"})
    try:
        final, _ = resume(db, app.state.settings, ticket_id, principal.sub, body.action,
                          guardrails.mask(body.text), app.state.llm)
    except tickets.NotClaimant as e:
        raise HTTPException(409, detail={"code": "conflict", "message": "ticket must be claimed by you"}) from e
    final = guardrails.mask(final)
    turn_id = conv.append_turn(db, ticket.conversation_id, "assistant", final, route="escalation",
                               status="answered", sources=[])
    metrics.TICKETS_OPEN.set(tickets.open_stats(db)[0])
    return {"ticket": tickets.get_ticket(db, ticket_id).model_dump(mode="json"),
            "turn": {"id": turn_id, "role": "assistant", "text": final}}


@router.get("/retrieval")
def retrieval(request: Request, q: str = Query(min_length=1, max_length=2000),
              mode: Literal["hybrid", "vector"] = "hybrid", k: int | None = Query(default=None, ge=1, le=50),
              principal: Principal = Depends(require_operator)):
    app = request.app
    chunks = retrieve(app.state.settings, app.state.llm, q, mode=mode, k=k)
    return {"chunks": [{"rank": i + 1, "url": c.url, "title": c.title, "heading": c.heading,
                        "score": round(c.score, 4), "similarity": round(c.similarity, 4),
                        "excerpt": c.text[:600]} for i, c in enumerate(chunks)]}
