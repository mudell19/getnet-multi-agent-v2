from datetime import date

from getnet_multi_agent.agents.prompts import (
    critic,
    knowledge,
    personality,
    router,
    support,
    synthesis,
)
from getnet_multi_agent.agents.support import support as support_agent
from getnet_multi_agent.agents.tools import (
    TOOL_SPECS,
    get_receivables,
    get_terminal_status,
    run_tool,
)
from getnet_multi_agent.contracts import Principal, Step
from getnet_multi_agent.core.llm import FunctionCall, LLMResult

P = Principal(sub="cliente1988", role="merchant")


def test_fr_025_get_receivables_validates_dates(settings):
    today = date(2026, 11, 26)
    r = get_receivables(settings.data_path, "cliente1988", "2026-11-25", "2026-11-25", today=today)
    assert r.merchant_found and len(r.items) >= 2 and r.total == round(sum(i.amount for i in r.items), 2)
    assert all(i.sale_date == "2026-11-25" and i.settlement_date for i in r.items)
    assert get_receivables(settings.data_path, "cliente1988", "25/11/2026", None).error
    assert get_receivables(settings.data_path, "cliente1988", "2026-11-25", "2026-11-01").error
    assert get_receivables(settings.data_path, "cliente1988", "2026-01-01", "2026-11-25").error


def test_fr_026_terminal_status_connectivity_errors_actions(settings):
    r = get_terminal_status(settings.data_path, "cliente1988")
    t = {x.id: x for x in r.terminals}
    assert t["T-1001"].connectivity == "offline" and t["T-1001"].suggested_actions
    decline = t["T-1002"].last_errors[0]
    assert decline.kind == "transaction_decline" and "insufficient funds" in decline.message


def test_fr_027_merchant_id_from_principal_and_not_found(settings, fake_llm):
    assert all("merchant" not in str(s.parameters) for s in TOOL_SPECS)
    assert run_tool("get_terminal_status", {"merchant_id": "cliente2000"}, settings.data_path,
                    "cliente1988")["terminals"][0]["id"] == "T-1001"
    assert get_terminal_status(settings.data_path, "cliente9999").merchant_found is False
    assert get_receivables(settings.data_path, "unknown").merchant_found is False


def test_fr_028_tool_loop_sends_untrusted_data_and_whole_model_content(settings, fake_llm):
    raw = object()
    fake_llm.responses["support"] = [
        LLMResult(function_calls=[FunctionCall(name="get_terminal_status", args={})], content=raw),
        LLMResult(text="Terminal T-1001 is offline."),
    ]
    obs = support_agent(Step(id="s1", agent="support", query="my machine?"), P, "en", fake_llm, settings)
    assert obs.status == "answered" and "get_terminal_status" in obs.data
    second = fake_llm.calls[1]["contents"]
    assert second[1].raw is raw  # model content sent back whole
    assert "untrusted_data" in second[2].tool_response
    assert "untrusted" in fake_llm.calls[0]["system"].lower()


def test_fr_056_every_agent_prompt_states_role_scope_format_refusals():
    prompts = [support.SYSTEM, knowledge.RAG_SYSTEM, router.SYSTEM, synthesis.SYSTEM,
               personality.SYSTEM]
    for p in prompts:
        assert "ROLE" in p and "OUTPUT FORMAT" in p or "JSON" in p
    for p in (support.SYSTEM, knowledge.RAG_SYSTEM, synthesis.SYSTEM, personality.SYSTEM):
        assert "REFUSALS" in p
    for p in (support.SYSTEM, knowledge.RAG_SYSTEM, router.SYSTEM, critic.COMPLETENESS_SYSTEM):
        assert "{today}" in p
