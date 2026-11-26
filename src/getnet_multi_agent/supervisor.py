"""Bounded supervisor loop: plan → execute steps → observe → critic (replan) → synthesis → Personality."""

import time
from dataclasses import dataclass, field

from getnet_multi_agent.agents import critic as critic_mod
from getnet_multi_agent.agents import planner
from getnet_multi_agent.agents.knowledge import knowledge_rag, knowledge_web
from getnet_multi_agent.agents.personality import personality
from getnet_multi_agent.agents.support import support
from getnet_multi_agent.agents.synthesis import synthesize
from getnet_multi_agent.contracts import (
    Observation,
    Plan,
    PlanRevision,
    Principal,
    SourceRef,
    Step,
    Trace,
    TraceTotal,
    Usage,
)
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.llm import BudgetExceeded, LLMClient, LLMUnavailable
from getnet_multi_agent.security.dlp import dlp_check
from getnet_multi_agent.security.guardrails import detect_lang, refusal_message

GLOBAL_NOTE = {
    "en": "Note: part of this information comes from Getnet's global site (getnet.net) and is not confirmed for Brazil.",
    "pt": "Observação: parte desta informação vem do site global da Getnet (getnet.net) e não está confirmada para o Brasil.",
}
UNAVAILABLE = {
    "en": "I couldn't complete your request right now.",
    "pt": "Não consegui concluir sua solicitação agora.",
}


@dataclass
class RunOutcome:
    answer: str
    status: str  # answered | awaiting_human | refused
    route: str
    lang: str = "en"
    refusal_reason: str | None = None
    sources: list[SourceRef] = field(default_factory=list)
    trace: Trace = field(default_factory=Trace)
    escalation_reason: str | None = None
    escalated_parts: list[str] = field(default_factory=list)
    answered_text: str = ""
    standalone: str = ""
    plan: Plan | None = None


def _route(executed: list[Observation]) -> str:
    names = []
    for o in executed:
        name = "support" if o.agent == "support" else f"knowledge:{o.source}"
        if not names or names[-1] != name:
            names.append(name)
    return ">".join(names)


def _execute(step: Step, plan: Plan, principal: Principal, llm: LLMClient, settings) -> Observation:
    try:
        if step.agent == "support":
            return support(step, principal, plan.lang, llm, settings)
        if step.source == "web":
            return knowledge_web(step, plan.lang, llm, settings)
        return knowledge_rag(step, plan.lang, llm, settings)
    except LLMUnavailable as e:
        return Observation(step_id=step.id, agent=step.agent, source=step.source, status="failed",
                           unanswered=[step.query], error=f"llm unavailable: {e}"[:300])
    except BudgetExceeded:
        raise
    except Exception as e:  # tool or retrieval failure: typed observation, escalated by the critic
        return Observation(step_id=step.id, agent=step.agent, source=step.source, status="failed",
                           unanswered=[step.query], error=f"{type(e).__name__}: {e}"[:300])


def _sources(answered: list[Observation]) -> list[SourceRef]:
    out: dict[str, SourceRef] = {}
    for o in answered:
        if o.source == "rag":
            urls = (o.data or {}).get("cited_urls", [])
            for ev in o.evidence:
                if ev.url in urls and ev.url not in out:
                    out[ev.url] = SourceRef(title=ev.title, url=ev.url)
        elif o.source == "web":
            for ev in o.evidence:
                out.setdefault(ev.url, SourceRef(title=ev.title, url=ev.url))
    return list(out.values())


def run(message: str, principal: Principal, summary: str, last_turns: list[dict],
        llm: LLMClient, settings) -> RunOutcome:
    t0 = time.monotonic()
    trace = Trace()
    usage: list[Usage] = []
    lang = detect_lang(message)

    def finish(outcome: RunOutcome) -> RunOutcome:
        trace.steps_usage = usage
        trace.total = TraceTotal(
            tokens=sum(u.prompt_tokens + u.output_tokens + u.thinking_tokens for u in usage),
            cost_usd=round(sum(u.cost_usd for u in usage), 6),
            latency_ms=int((time.monotonic() - t0) * 1000))
        outcome.trace = trace
        return outcome

    try:
        plan, res = planner.plan(message, summary, last_turns, llm)
        usage.append(res.usage)
    except (LLMUnavailable, AttributeError, ValueError) as e:
        trace.critic_notes.append(f"router failed: {type(e).__name__}")
        return finish(RunOutcome(answer=UNAVAILABLE[lang], status="awaiting_human", route="escalation",
                                 lang=lang, escalation_reason="llm_failure", standalone=message))
    except BudgetExceeded:
        return finish(RunOutcome(answer=UNAVAILABLE[lang], status="awaiting_human", route="escalation",
                                 lang=lang, escalation_reason="budget_exceeded", standalone=message))
    lang = plan.lang
    trace.plan_revisions.append(PlanRevision(
        iteration=0, action="add", step_id=",".join(s.id for s in plan.steps) or "-",
        reason=f"initial plan: {[f'{s.id}:{s.agent}:{s.source or ''}' for s in plan.steps]}"))

    if plan.refusal_reason:
        return finish(RunOutcome(answer=refusal_message(plan.refusal_reason, lang), status="refused",
                                 route="refusal", lang=lang, refusal_reason=plan.refusal_reason,
                                 standalone=plan.standalone, plan=plan))
    if plan.escalate_reason:
        return finish(RunOutcome(answer="", status="awaiting_human", route="escalation", lang=lang,
                                 escalation_reason="human_requested", standalone=plan.standalone,
                                 plan=plan))

    observations: dict[str, Observation] = {}
    executed: list[Observation] = []
    pending = list(plan.steps)
    retried: set[str] = set()
    budget_hit = False
    for iteration in range(1, settings.MAX_SUPERVISOR_ITERATIONS + 1):
        try:
            for step in pending:
                obs = _execute(step, plan, principal, llm, settings)
                usage.extend(obs.usage)
                observations[step.id] = obs
                executed.append(obs)
            pending = []
            allow_more = iteration < settings.MAX_SUPERVISOR_ITERATIONS
            verdict, new_steps = critic_mod.review(message, plan, list(observations.values()),
                                                   iteration, retried, llm, allow_more)
        except BudgetExceeded:
            budget_hit = True
            trace.critic_notes.append("token budget exceeded: stop")
            break
        trace.plan_revisions.extend(verdict.revisions)
        trace.critic_notes.extend(f"iter {iteration}: {n}" for n in verdict.notes)
        if verdict.revisions:
            metrics.REPLANS.inc(len(verdict.revisions))
        # a retried step supersedes its original observation
        for s in new_steps:
            if s.id.endswith("r"):
                observations.pop(s.id[:-1], None)
        pending = new_steps
        if not pending:
            break
    trace.observations = executed

    answered = [o for o in observations.values() if o.status in ("answered", "partial")]
    unresolved = [o for o in observations.values() if o.status in ("failed", "no_grounding")]
    escalated_parts = [q for o in unresolved for q in (o.unanswered or [o.step_id])]

    if not answered:
        reason = "budget_exceeded" if budget_hit else (
            "no_grounding" if any(o.status == "no_grounding" for o in unresolved) else
            "llm_failure" if any("llm" in (o.error or "") for o in unresolved) else "tool_failure")
        return finish(RunOutcome(answer="", status="awaiting_human", route="escalation", lang=lang,
                                 escalation_reason=reason, escalated_parts=escalated_parts,
                                 standalone=plan.standalone, plan=plan))

    try:
        if len(answered) > 1:
            draft, u = synthesize(plan.standalone, answered, lang, llm)
            usage.append(u)
        else:
            draft = answered[0].answer
        text, p_usage, note = personality(draft, lang, llm)
        usage.extend(p_usage)
        trace.critic_notes.append(note)
    except (LLMUnavailable, BudgetExceeded) as e:
        draft = "\n\n".join(o.answer for o in answered)
        text = draft
        trace.critic_notes.append(f"synthesis/personality skipped: {type(e).__name__}")

    if any((o.data or {}).get("global_site") for o in answered):
        text = f"{text}\n\n{GLOBAL_NOTE.get(lang, GLOBAL_NOTE['en'])}"
    text = dlp_check(text, principal.sub)
    sources = _sources(answered)
    executed_answering = [o for o in executed if o in answered]
    if unresolved or budget_hit:
        reason = "budget_exceeded" if budget_hit else (
            "no_grounding" if any(o.status == "no_grounding" for o in unresolved) else "tool_failure")
        return finish(RunOutcome(answer=text, status="awaiting_human", route="escalation", lang=lang,
                                 sources=sources, escalation_reason=reason,
                                 escalated_parts=escalated_parts, answered_text=text,
                                 standalone=plan.standalone, plan=plan))
    return finish(RunOutcome(answer=text, status="answered", route=_route(executed_answering),
                             lang=lang, sources=sources, answered_text=text,
                             standalone=plan.standalone, plan=plan))
