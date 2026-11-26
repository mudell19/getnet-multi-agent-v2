import pytest

from getnet_multi_agent import supervisor
from getnet_multi_agent.agents import knowledge
from getnet_multi_agent.contracts import AgentResult, Plan, Principal, RankedChunk, Step
from getnet_multi_agent.core.llm import BudgetExceeded, FunctionCall, LLMResult

P = Principal(sub="cliente1988", role="merchant")
CHUNK = RankedChunk(id="a", url="https://site.getnet.com.br/duvidas/", heading="Chip",
                    text="Faça um teste de comunicação para verificar a conectividade do seu chip.",
                    site="br", similarity=0.8, score=0.9)


@pytest.fixture(autouse=True)
def fixed_retrieval(monkeypatch):
    monkeypatch.setattr(knowledge, "retrieve", lambda *a, **k: [CHUNK])


def tool_then_text(name, text):
    return [LLMResult(function_calls=[FunctionCall(name=name)], content="raw"), LLMResult(text=text)]


def script(fake_llm, steps, support=None, knowledge_answer="Run the communication test (teste de comunicação).",
           complete=True):
    fake_llm.responses["router"] = Plan(steps=steps, lang="en", standalone="q", parts=["q"])
    if support:
        fake_llm.responses["support"] = support
    fake_llm.responses["knowledge"] = AgentResult(answer=knowledge_answer, grounded=True, cited_ids=["0"])
    fake_llm.responses["critic"] = {"complete": complete, "missing_parts": []}
    fake_llm.responses["synthesis"] = lambda **k: "Merged: " + " ".join(
        p.split(">", 1)[1].split("</agent_answer")[0].strip() for p in k["contents"].split("<agent_answer")[1:])
    fake_llm.responses["personality"] = lambda **k: k["contents"].split("\n", 1)[1].rsplit("\n", 1)[0]


def test_fr_001_and_fr_005_connectivity_replans_support_then_knowledge(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="support", query="won't connect")],
           support=tool_then_text("get_terminal_status", "Terminal T-1001 is offline."))
    out = supervisor.run("My card machine won't connect to the internet", P, "", [], fake_llm, settings)
    assert out.status == "answered" and out.route == "support>knowledge:rag"
    assert any(r.action == "add" and "offline" in r.reason for r in out.trace.plan_revisions)
    assert "T-1001" in out.answer and "teste de comunicação" in out.answer


def test_fr_003_observations_and_fr_049_trace_usage(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="knowledge", source="rag", query="chip")])
    out = supervisor.run("chip?", P, "", [], fake_llm, settings)
    obs = out.trace.observations[0]
    assert obs.status == "answered" and obs.evidence[0].url == CHUNK.url and obs.evidence[0].excerpt
    assert out.trace.total.tokens > 0 and out.trace.steps_usage


def test_fr_010_sources_attached_by_code(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="knowledge", source="rag", query="chip")])
    out = supervisor.run("chip?", P, "", [], fake_llm, settings)
    assert [s.url for s in out.sources] == [CHUNK.url] and CHUNK.url not in out.answer


def test_fr_048_route_vocabulary_compound(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="support", query="deposit"),
                      Step(id="s2", agent="knowledge", source="rag", query="advance")],
           support=tool_then_text("get_receivables", "R$ 1.250,00 settles on 2026-11-26."))
    out = supervisor.run("deposit and advance?", P, "", [], fake_llm, settings)
    assert out.route == "support>knowledge:rag" and "R$ 1.250,00" in out.answer


def test_fr_007_loop_bounded_and_partial_escalation(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="support", query="deposit"),
                      Step(id="s2", agent="knowledge", source="rag", query="unknown topic")],
           support=tool_then_text("get_receivables", "R$ 1.250,00 settles on 2026-11-26."))
    fake_llm.responses["knowledge"] = AgentResult(answer="", grounded=False)
    fake_llm.responses["critic"] = lambda **k: (
        {"query": "tópico desconhecido"} if k["schema"].__name__ == "Rewrite" else {"complete": True})
    out = supervisor.run("deposit and unknown?", P, "", [], fake_llm, settings)
    assert out.status == "awaiting_human" and out.route == "escalation"
    assert "R$ 1.250,00" in out.answer and out.escalated_parts  # answered part kept
    assert sum(1 for c in fake_llm.calls if c["task"] == "knowledge") == 2  # original + one retry


def test_fr_055_budget_exceeded_escalates(settings, fake_llm):
    fake_llm.responses["router"] = BudgetExceeded("spent")
    out = supervisor.run("hi", P, "", [], fake_llm, settings)
    assert out.status == "awaiting_human" and out.escalation_reason == "budget_exceeded"


def test_fr_030_planned_refusal_and_human_request(settings, fake_llm):
    fake_llm.responses["router"] = Plan(steps=[], lang="pt", standalone="poema", refusal_reason="out_of_scope")
    out = supervisor.run("escreva um poema", P, "", [], fake_llm, settings)
    assert out.status == "refused" and out.route == "refusal" and out.refusal_reason == "out_of_scope"
    fake_llm.responses["router"] = Plan(steps=[], lang="en", standalone="human", escalate_reason="human_requested")
    out = supervisor.run("I want a human", P, "", [], fake_llm, settings)
    assert out.status == "awaiting_human" and out.escalation_reason == "human_requested"


def test_fr_005_ungrounded_enrichment_is_dropped_not_escalated(settings, fake_llm):
    script(fake_llm, [Step(id="s1", agent="support", query="decline error")],
           support=tool_then_text("get_terminal_status", "T-1002 decline 51 insufficient funds."))
    fake_llm.responses["knowledge"] = AgentResult(answer="", grounded=False)
    fake_llm.responses["critic"] = lambda **k: (
        {"query": "transação negada"} if k["schema"].__name__ == "Rewrite" else {"complete": True})
    out = supervisor.run("My card machine is showing a transaction decline error.", P, "", [],
                         fake_llm, settings)
    assert out.status == "answered" and out.route == "support" and "T-1002" in out.answer
    assert [r.action for r in out.trace.plan_revisions][1:] == ["add", "retry", "drop"]
