"""Human Escalation agent: checkpoint + ticket + audit, and resumption after an operator decision."""

from getnet_multi_agent.agents.personality import personality
from getnet_multi_agent.core.llm import LLMClient
from getnet_multi_agent.security.pseudonym import pseudonym
from getnet_multi_agent.state import audit, checkpoints, tickets

HANDOFF = {
    "en": "I've forwarded {what} to a human specialist (ticket {ticket}). You'll get the answer in this conversation.",
    "pt": "Encaminhei {what} para um especialista humano (ticket {ticket}). Você receberá a resposta nesta conversa.",
}
WHAT = {
    "en": ("your request", "the part I could not answer reliably ({parts})"),
    "pt": ("sua solicitação", "a parte que não consegui responder com segurança ({parts})"),
}
REJECT = {
    "en": "A specialist reviewed your request and could not fulfil it.",
    "pt": "Um especialista analisou sua solicitação e não pôde atendê-la.",
}


def handoff_text(lang: str, ticket_id: str, parts: list[str]) -> str:
    lang = lang if lang in HANDOFF else "en"
    what = WHAT[lang][1].format(parts="; ".join(parts)) if parts else WHAT[lang][0]
    return HANDOFF[lang].format(what=what, ticket=ticket_id)


def escalate(db, settings, conversation_id: str, request_id: str, owner_sub: str, reason: str,
             state: dict) -> tuple[str, str]:
    checkpoint_id = checkpoints.save_checkpoint(db, conversation_id, request_id, state)
    ticket_id = tickets.open_ticket(db, conversation_id, checkpoint_id, owner_sub, reason)
    audit.record(db, ticket_id, "system", "escalated", {"reason": reason, "request_id": request_id})
    return ticket_id, checkpoint_id


def resume(db, settings, ticket_id: str, operator_sub: str, action: str, text: str,
           llm: LLMClient) -> tuple[str, dict]:
    """Resolve a claimed ticket and return the final answer for the merchant (via Personality)."""
    ticket = tickets.get_ticket(db, ticket_id)
    if ticket is None:
        raise tickets.TicketNotFound(ticket_id)
    cp = checkpoints.load_checkpoint(db, ticket.resolution.get("checkpoint_id")) if (
        ticket.resolution and ticket.resolution.get("checkpoint_id")) else None
    if cp is None:
        cp = _checkpoint_for(db, ticket)
    state = (cp or {}).get("state", {})
    lang = state.get("lang", "en")
    answered = state.get("answered_text", "")
    if action == "approve":
        draft = state.get("proposed_answer") or text or answered
    elif action == "edit":
        draft = "\n\n".join(p for p in (answered, text) if p)
    else:
        draft = REJECT.get(lang, REJECT["en"]) + (f" {text}" if text else "")
    final, usages, note = personality(draft, lang, llm)
    resolution = {"action": action, "text": text, "personality": note,
                  "checkpoint_id": (cp or {}).get("id")}
    tickets.resolve(db, ticket_id, operator_sub, action, resolution)
    audit.record(db, ticket_id, pseudonym(operator_sub, settings), action, {"personality": note})
    return final, {"lang": lang, "usages": [u.model_dump() for u in usages]}


def _checkpoint_for(db, ticket) -> dict | None:
    with db.conn() as c:
        row = c.execute("SELECT checkpoint_id FROM tickets WHERE id=?", (ticket.id,)).fetchone()
    return checkpoints.load_checkpoint(db, row["checkpoint_id"]) if row else None
