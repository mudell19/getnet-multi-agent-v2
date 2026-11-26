"""Critic: deterministic rules first, then a lite-model completeness check. May add or retry steps."""

from pydantic import BaseModel, Field

from getnet_multi_agent.agents.prompts.critic import COMPLETENESS_SYSTEM, REWRITE_SYSTEM
from getnet_multi_agent.contracts import CriticVerdict, Observation, Plan, PlanRevision, Step
from getnet_multi_agent.core.llm import LLMClient, LLMUnavailable
from getnet_multi_agent.merchants import today_brt

TROUBLESHOOT = {
    ("connectivity", "en"): "Card machine not connecting to the internet: troubleshooting steps, chip, Wi-Fi and communication test (teste de comunicação)",
    ("connectivity", "pt"): "Maquininha sem conexão com a internet: como resolver, chip, Wi-Fi e teste de comunicação",
    ("error", "en"): "Card machine showing a transaction declined error: what the merchant should do (transação negada)",
    ("error", "pt"): "Maquininha com erro de transação negada: o que fazer",
}


class Completeness(BaseModel):
    complete: bool
    missing_parts: list[str] = Field(default_factory=list)


class Rewrite(BaseModel):
    query: str


DECLINE_WORDS = ("declin", "negad", "recusad", "transaction error", "erro de transa")


def terminal_problem(obs: Observation, query: str = "") -> str | None:
    """'error' when the user asks about a decline/error that a terminal shows, 'connectivity' for an
    offline terminal, 'error' for other recent terminal errors, else None."""
    status = (obs.data or {}).get("get_terminal_status") or {}
    terminals = status.get("terminals") or []
    has_errors = any(t.get("last_errors") for t in terminals)
    if has_errors and any(w in query.lower() for w in DECLINE_WORDS):
        return "error"
    if any(t.get("connectivity") != "online" for t in terminals):
        return "connectivity"
    return "error" if has_errors else None


def _next_id(plan: Plan) -> str:
    return f"s{len(plan.steps) + 1}"


def rewrite_query(query: str, llm: LLMClient) -> str:
    try:
        res = llm.generate("critic", query, schema=Rewrite, system=REWRITE_SYSTEM)
        return res.parsed.query.strip() or query
    except (LLMUnavailable, AttributeError):
        return query


def review(message: str, plan: Plan, observations: list[Observation], iteration: int,
           retried: set[str], llm: LLMClient, allow_more_steps: bool) -> tuple[CriticVerdict, list[Step]]:
    """Return the verdict and the new steps to execute next (already appended to plan.steps)."""
    revisions: list[PlanRevision] = []
    notes: list[str] = []
    new_steps: list[Step] = []
    has_rag = any(s.agent == "knowledge" and s.source == "rag" for s in plan.steps)

    # Rule 1: an offline terminal or terminal error adds a Knowledge rag troubleshooting step.
    for obs in observations:
        step = next((s for s in plan.steps if s.id == obs.step_id), None)
        problem = terminal_problem(obs, f"{message} {step.query if step else ''}") if obs.agent == "support" else None
        if problem and not has_rag and allow_more_steps:
            step = Step(id=_next_id(plan), agent="knowledge", source="rag",
                        query=TROUBLESHOOT[(problem, plan.lang)])
            plan.steps.append(step)
            new_steps.append(step)
            has_rag = True
            reason = ("terminal offline: add site troubleshooting steps" if problem == "connectivity"
                      else "terminal error: add site guidance")
            revisions.append(PlanRevision(iteration=iteration, action="add", step_id=step.id, reason=reason))

    # Rule 2: a rag step without grounding is retried once with a rewritten query.
    for obs in observations:
        if obs.source == "rag" and obs.status == "no_grounding" and obs.step_id not in retried and allow_more_steps:
            original = next((s for s in plan.steps if s.id == obs.step_id), None)
            if original is None:
                continue
            retried.add(obs.step_id)
            step = Step(id=f"{obs.step_id}r", agent="knowledge", source="rag",
                        query=rewrite_query(original.query, llm))
            new_steps.append(step)
            revisions.append(PlanRevision(iteration=iteration, action="retry", step_id=obs.step_id,
                                          reason=f"no grounding; retry with rewritten query: {step.query}"))

    # Rule 3: failures and exhausted retries escalate that part only.
    for obs in observations:
        if obs.status == "failed" or (obs.status == "no_grounding" and (obs.step_id.endswith("r") or not allow_more_steps)):
            notes.append(f"{obs.step_id}: {obs.status}, escalate this part")

    if new_steps:
        return CriticVerdict(complete=False, revisions=revisions, notes=notes), new_steps

    # Lite-model check that every part of the message was answered.
    answers = [o for o in observations if o.status in ("answered", "partial")]
    if not answers:
        return CriticVerdict(complete=False, revisions=revisions, notes=notes + ["no answered step"]), []
    body = "<user_message>\n" + message + "\n</user_message>\n" + "\n".join(
        f'<answer step="{o.step_id}">\n{o.answer[:1500]}\n</answer>' for o in answers)
    try:
        res = llm.generate("critic", body, schema=Completeness,
                           system=COMPLETENESS_SYSTEM.format(today=today_brt().isoformat()))
        c: Completeness = res.parsed
    except LLMUnavailable:
        return CriticVerdict(complete=True, notes=notes + ["completeness check unavailable"]), []
    if not c.complete and c.missing_parts and allow_more_steps:
        for part in c.missing_parts[:2]:
            step = Step(id=_next_id(plan), agent="knowledge", source="rag", query=part)
            plan.steps.append(step)
            new_steps.append(step)
            revisions.append(PlanRevision(iteration=iteration, action="add", step_id=step.id,
                                          reason=f"part not answered: {part}"))
    notes.append("complete" if c.complete else f"missing: {c.missing_parts}")
    return CriticVerdict(complete=c.complete or not new_steps, missing_parts=c.missing_parts,
                         revisions=revisions, notes=notes), new_steps
