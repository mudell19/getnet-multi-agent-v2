"""POST /chat: auth → guardrails → memory → supervisor → escalation/persistence → response."""

import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from getnet_multi_agent.agents.escalation import escalate, handoff_text
from getnet_multi_agent.agents.synthesis import summarize
from getnet_multi_agent.contracts import ChatRequest, ChatResponse, Principal, Trace
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.logging import get_logger
from getnet_multi_agent.core.request_context import get_request_id
from getnet_multi_agent.security import guardrails
from getnet_multi_agent.security.auth import require_merchant
from getnet_multi_agent.security.dlp import mask_obj
from getnet_multi_agent.security.pseudonym import pseudonym
from getnet_multi_agent.state import conversations as conv
from getnet_multi_agent.supervisor import run

router = APIRouter()
log = get_logger("chat")


def refresh_summary(db, llm, conversation_id: str, request_id: str) -> None:
    try:
        turns = conv.list_turns(db, conversation_id)
        if len(turns) < 4:
            return
        prev = conv.get_summary(db, conversation_id)
        since = prev["last_turn_id"] if prev else 0
        new = [t for t in turns if t["id"] > since]
        text = summarize(prev["text"] if prev else "", new, llm)
        if text:
            conv.save_summary(db, conversation_id, guardrails.mask(text), turns[-1]["id"])
    except Exception as e:
        log.warning("summary refresh failed", extra={"fields": {"error": type(e).__name__,
                                                                 "request_id": request_id}})


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, background: BackgroundTasks,
         principal: Principal = Depends(require_merchant)) -> ChatResponse:
    t0 = time.monotonic()
    app = request.app
    settings, db, llm = app.state.settings, app.state.db, app.state.llm
    if req.user_id != principal.sub:
        raise HTTPException(403, detail={"code": "forbidden", "message": "user_id does not match token"})
    if req.conversation_id:
        if conv.get_conversation(db, req.conversation_id, principal.sub) is None:
            raise HTTPException(404, detail={"code": "not_found", "message": "conversation not found"})
        conversation_id = req.conversation_id
    else:
        conversation_id = conv.create_conversation(db, principal.sub)
    request_id = get_request_id()
    masked = guardrails.mask(req.message)

    refusal = guardrails.check(req.message, principal.sub, settings)
    if refusal is not None:
        conv.append_turn(db, conversation_id, "user", masked[:settings.MAX_MESSAGE_CHARS], request_id=request_id)
        conv.append_turn(db, conversation_id, "assistant", refusal.message, route="refusal",
                         status="refused", sources=[], request_id=request_id)
        metrics.REFUSALS.labels(reason=refusal.reason).inc()
        return _respond(ChatResponse(answer=refusal.message, status="refused", refusal_reason=refusal.reason,
                                     route="refusal", conversation_id=conversation_id,
                                     request_id=request_id, trace=Trace()), t0)

    summary = (conv.get_summary(db, conversation_id) or {}).get("text", "")
    last = conv.last_turns(db, conversation_id, settings.MEMORY_LAST_TURNS)
    conv.append_turn(db, conversation_id, "user", masked, request_id=request_id)
    outcome = run(masked, principal, summary, last, llm, settings)

    ticket_id = None
    answer = outcome.answer
    if outcome.status == "awaiting_human":
        state = mask_obj({
            "lang": outcome.lang, "message": masked, "standalone": outcome.standalone,
            "plan": outcome.plan.model_dump() if outcome.plan else None,
            "observations": [o.model_dump() for o in outcome.trace.observations],
            "answered_text": outcome.answered_text, "proposed_answer": outcome.answered_text,
            "escalated_parts": outcome.escalated_parts, "reason": outcome.escalation_reason,
        })
        ticket_id, _ = escalate(db, settings, conversation_id, request_id, principal.sub,
                                outcome.escalation_reason or "llm_failure", state)
        note = handoff_text(outcome.lang, ticket_id, outcome.escalated_parts if outcome.answered_text else [])
        answer = f"{outcome.answer}\n\n{note}".strip() if outcome.answered_text else note
        metrics.ESCALATIONS.labels(reason=outcome.escalation_reason or "llm_failure").inc()
    elif outcome.status == "refused":
        metrics.REFUSALS.labels(reason=outcome.refusal_reason).inc()

    sources = [s.model_dump() for s in outcome.sources]
    conv.append_turn(db, conversation_id, "assistant", guardrails.mask(answer), route=outcome.route,
                     status=outcome.status, sources=sources, request_id=request_id)
    background.add_task(refresh_summary, db, llm, conversation_id, request_id)
    log.info("chat", extra={"fields": {"user": pseudonym(principal.sub, settings), "route": outcome.route,
                                       "status": outcome.status, "tokens": outcome.trace.total.tokens,
                                       "cost_usd": outcome.trace.total.cost_usd}})
    return _respond(ChatResponse(answer=answer, status=outcome.status, refusal_reason=outcome.refusal_reason,
                                 route=outcome.route, sources=outcome.sources, ticket_id=ticket_id,
                                 conversation_id=conversation_id, request_id=request_id,
                                 trace=outcome.trace), t0)


def _respond(resp: ChatResponse, t0: float) -> ChatResponse:
    metrics.REQUESTS.labels(route=resp.route, status=resp.status).inc()
    metrics.LATENCY.observe(time.monotonic() - t0)
    return resp
