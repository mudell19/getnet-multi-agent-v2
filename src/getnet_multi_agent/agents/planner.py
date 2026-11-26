"""Router: typed plan with steps, language and a standalone rewrite of the message."""

from getnet_multi_agent.agents.prompts.router import SYSTEM, USER
from getnet_multi_agent.contracts import Plan, Step
from getnet_multi_agent.core.llm import LLMClient, LLMResult
from getnet_multi_agent.merchants import today_brt


def _turns_text(turns: list[dict]) -> str:
    return "\n".join(f"{t['role']}: {t['text'][:600]}" for t in turns) or "(none)"


def normalize(plan: Plan, message: str) -> Plan:
    """Make the plan executable: unique ids, knowledge source set, support without source."""
    if plan.refusal_reason or plan.escalate_reason:
        plan.steps = []
        return plan
    steps = []
    for i, s in enumerate(plan.steps, 1):
        source = (s.source or "rag") if s.agent == "knowledge" else None
        if s.agent == "escalation":
            plan.escalate_reason = "human_requested"
            continue
        steps.append(Step(id=f"s{i}", agent=s.agent, source=source, query=s.query or plan.standalone))
    if not steps and not plan.escalate_reason:
        steps = [Step(id="s1", agent="knowledge", source="rag", query=plan.standalone or message)]
    plan.steps = steps
    plan.standalone = plan.standalone or message
    plan.parts = plan.parts or [plan.standalone]
    return plan


def plan(message: str, summary: str, last_turns: list[dict], llm: LLMClient) -> tuple[Plan, LLMResult]:
    system = SYSTEM.format(today=today_brt().isoformat())
    user = USER.format(summary=summary or "(none)", turns=_turns_text(last_turns), message=message)
    res = llm.generate("router", user, schema=Plan, system=system)
    return normalize(res.parsed, message), res
