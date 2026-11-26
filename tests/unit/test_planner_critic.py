from getnet_multi_agent.agents import critic, planner
from getnet_multi_agent.contracts import Observation, Plan, Step
from getnet_multi_agent.core.llm import LLMUnavailable

OFFLINE = {"get_terminal_status": {"merchant_found": True, "terminals": [
    {"id": "T-1001", "connectivity": "offline", "last_errors": [{"kind": "connectivity"}]}]}}


def test_fr_002_plan_normalized_and_typed(fake_llm):
    fake_llm.responses["router"] = Plan(steps=[Step(id="x", agent="knowledge", query="q")],
                                        lang="en", standalone="q")
    plan, _ = planner.plan("q", "", [], fake_llm)
    assert plan.steps[0].id == "s1" and plan.steps[0].source == "rag" and plan.parts == ["q"]


def test_fr_039_router_receives_summary_and_turns(fake_llm):
    fake_llm.responses["router"] = Plan(steps=[], lang="en", standalone="How much is the Payment Link?")
    plan, _ = planner.plan("and how much is it?", "Talked about Payment Link",
                           [{"role": "user", "text": "How does the Payment Link work?"}], fake_llm)
    prompt = fake_llm.calls[0]["contents"]
    assert "Talked about Payment Link" in prompt and "How does the Payment Link work?" in prompt
    assert plan.standalone == "How much is the Payment Link?"


def test_fr_030_planned_refusal_has_no_steps(fake_llm):
    fake_llm.responses["router"] = Plan(steps=[Step(id="s1", agent="knowledge", query="poem")],
                                        lang="en", standalone="poem", refusal_reason="out_of_scope")
    plan, _ = planner.plan("write a poem", "", [], fake_llm)
    assert plan.refusal_reason == "out_of_scope" and plan.steps == []


def test_fr_005_offline_terminal_adds_knowledge_rag(fake_llm):
    plan = Plan(steps=[Step(id="s1", agent="support", query="machine won't connect")], standalone="x")
    obs = Observation(step_id="s1", agent="support", status="answered", answer="T-1001 offline", data=OFFLINE)
    verdict, new = critic.review("x", plan, [obs], 1, set(), fake_llm, True)
    assert new and new[0].agent == "knowledge" and new[0].source == "rag"
    assert verdict.revisions[0].action == "add" and "offline" in verdict.revisions[0].reason
    assert fake_llm.calls == []  # deterministic rule, no LLM


def test_fr_006_no_grounding_retried_once_then_escalated(fake_llm):
    fake_llm.responses["critic"] = {"query": "chave Pix conta de recebimento"}
    plan = Plan(steps=[Step(id="s1", agent="knowledge", source="rag", query="pix bank account")], standalone="x")
    obs = Observation(step_id="s1", agent="knowledge", source="rag", status="no_grounding", unanswered=["pix"])
    retried: set[str] = set()
    verdict, new = critic.review("x", plan, [obs], 1, retried, fake_llm, True)
    assert new[0].id == "s1r" and new[0].query == "chave Pix conta de recebimento"
    assert verdict.revisions[0].action == "retry"
    obs2 = Observation(step_id="s1r", agent="knowledge", source="rag", status="no_grounding")
    verdict, new = critic.review("x", plan, [obs2], 2, retried, fake_llm, True)
    assert not new and any("escalate" in n for n in verdict.notes)


def test_fr_004_lite_check_adds_step_for_missing_part(fake_llm):
    fake_llm.responses["critic"] = {"complete": False, "missing_parts": ["how does advance work"]}
    plan = Plan(steps=[Step(id="s1", agent="support", query="deposit")], standalone="x")
    obs = Observation(step_id="s1", agent="support", status="answered", answer="Deposit on 2026-11-26",
                      data={"get_receivables": {}})
    verdict, new = critic.review("deposit and advance?", plan, [obs], 1, set(), fake_llm, True)
    assert new and new[0].query == "how does advance work" and not verdict.complete
    fake_llm.responses["critic"] = LLMUnavailable("down")
    verdict, new = critic.review("x", plan, [obs], 2, set(), fake_llm, True)
    assert verdict.complete and not new
