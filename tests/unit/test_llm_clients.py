from types import SimpleNamespace as NS

import pytest
from google.genai import errors, types

from getnet_multi_agent.contracts import Plan
from getnet_multi_agent.core import request_context
from getnet_multi_agent.core.gemini_client import GeminiClient
from getnet_multi_agent.core.llm import BudgetExceeded, LLMUnavailable, Message, ToolSpec
from getnet_multi_agent.core.stub_client import StubClient


def make_response(text="ok", usage=(10, 5, 2), queries=None, chunks=None, fcs=None):
    um = None if usage is None else NS(
        prompt_token_count=usage[0], candidates_token_count=usage[1], thoughts_token_count=usage[2]
    )
    gm = NS(
        grounding_chunks=[NS(web=NS(title=t, uri=u)) for t, u in (chunks or [])],
        web_search_queries=queries,
    )
    content = types.Content(role="model", parts=[types.Part(text=text)])
    return NS(
        text=text, parsed=None, usage_metadata=um, function_calls=fcs,
        candidates=[NS(content=content, grounding_metadata=gm)],
    )


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, **kw):
        self.calls.append(kw)
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    def embed_content(self, **kw):
        self.calls.append(kw)
        return NS(embeddings=[NS(values=[0.1, 0.2]) for _ in kw["contents"]])


def client_with(settings, *outcomes):
    models = FakeModels(outcomes)
    gc = GeminiClient(settings, client=NS(models=models), sleep=lambda s: None)
    return gc, models


@pytest.fixture(autouse=True)
def _ctx():
    request_context.start_request()


def test_fr053_usage_none_is_zero(settings):
    gc, _ = client_with(settings, make_response(usage=None))
    r = gc.generate("knowledge", "hi")
    assert r.usage.prompt_tokens == r.usage.output_tokens == r.usage.thinking_tokens == 0
    assert r.usage.cost_usd == 0


def test_fr053_cost_formula_with_search(settings):
    gc, _ = client_with(
        settings, make_response(usage=(1000, 200, 300), queries=["a", "b"],
                                chunks=[("Site", "https://v/x")])
    )
    r = gc.generate("knowledge", "hi", search=True)
    expected = 1000 * 0.75 / 1e6 + 500 * 3.75 / 1e6 + 2 * 14.0 / 1000
    assert r.usage.cost_usd == pytest.approx(expected)
    assert r.usage.search_queries == 2
    assert [(g.title, g.uri) for g in r.grounding] == [("Site", "https://v/x")]  # FR-022
    assert request_context.tokens_used() == 1500


def test_fr053_retry_once_on_429(settings):
    err = errors.APIError(429, {"error": {"message": "rate"}})
    gc, models = client_with(settings, err, make_response("fine"))
    assert gc.generate("knowledge", "hi").text == "fine"
    assert len(models.calls) == 2


def test_fr053_second_failure_unavailable(settings):
    err = errors.APIError(503, {"error": {"message": "down"}})
    gc, models = client_with(settings, err, err)
    with pytest.raises(LLMUnavailable):
        gc.generate("knowledge", "hi")
    assert len(models.calls) == 2


def test_fr053_400_no_retry(settings):
    gc, models = client_with(settings, errors.APIError(400, {"error": {"message": "bad"}}))
    with pytest.raises(LLMUnavailable):
        gc.generate("knowledge", "hi")
    assert len(models.calls) == 1


def test_fr053_raw_content_roundtrip(settings):
    gc, models = client_with(settings, make_response("first"), make_response("second"))
    r1 = gc.generate("support", "q")
    assert r1.content is not None
    msgs = [Message(role="user", text="q"), r1.as_message(),
            Message(role="tool", tool_name="t", tool_response={"v": 1})]
    gc.generate("support", msgs)
    sent = models.calls[1]["contents"]
    assert sent[1] is r1.content
    assert sent[0].role == "user" and sent[2].parts[0].function_response.name == "t"


def test_fr022_search_and_tools_rejected_before_call(settings):
    gc, models = client_with(settings, make_response())
    tool = ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})
    with pytest.raises(ValueError):
        gc.generate("knowledge", "hi", tools=[tool], search=True)
    assert models.calls == []


def test_tools_declared_and_function_calls_parsed(settings):
    fcs = [NS(name="get_sales", args={"days": 7})]
    gc, models = client_with(settings, make_response(fcs=fcs))
    tool = ToolSpec(name="get_sales", description="d",
                    parameters={"type": "object", "properties": {"days": {"type": "integer"}}})
    r = gc.generate("support", "sales?", tools=[tool])
    assert r.function_calls[0].name == "get_sales" and r.function_calls[0].args == {"days": 7}
    cfg = models.calls[0]["config"]
    assert cfg.automatic_function_calling.disable is True
    assert cfg.tools[0].function_declarations[0].parameters_json_schema == tool.parameters


@pytest.mark.parametrize(
    ("task", "model_attr", "think_attr"),
    [
        ("router", "GEMINI_ROUTER_MODEL", "minimal"),
        ("knowledge", "GEMINI_MODEL", "low"),
        ("judge", "GEMINI_JUDGE_MODEL", "high"),
    ],
)
def test_fr054_task_mapping(settings, task, model_attr, think_attr):
    gc, models = client_with(settings, make_response())
    gc.generate(task, "hi")
    call = models.calls[0]
    assert call["model"] == getattr(settings, model_attr)
    assert call["config"].thinking_config.thinking_level.value.lower() == think_attr


def test_fr055_budget_exceeded_before_call(settings):
    gc, models = client_with(settings, make_response())
    request_context.add_usage(
        request_context.Usage(prompt_tokens=settings.REQUEST_TOKEN_BUDGET)
    )
    with pytest.raises(BudgetExceeded):
        gc.generate("knowledge", "hi")
    assert models.calls == []


def test_embed_batches_and_dimension(settings):
    gc, models = client_with(settings)
    out = gc.embed(["x"] * 150, "RETRIEVAL_DOCUMENT")
    assert len(out) == 150 and len(models.calls) == 2
    assert models.calls[0]["config"].output_dimensionality == 768


def test_stub_plan_routes_euro_to_knowledge_web(settings):
    r = StubClient(settings).generate("router", "What's the euro exchange rate today?", schema=Plan)
    assert isinstance(r.parsed, Plan)
    assert (r.parsed.steps[0].agent, r.parsed.steps[0].source) == ("knowledge", "web")
    assert r.parsed.lang == "en"


def test_stub_support_and_embed(settings):
    stub = StubClient(settings)
    p = stub.generate("router", "Minhas vendas caíram, como funciona a antecipação?",
                      schema=Plan).parsed
    assert [s.agent for s in p.steps] == ["support", "knowledge"] and p.lang == "pt"
    assert len(stub.embed(["a"], "RETRIEVAL_QUERY")[0]) == 768
    assert stub.generate("knowledge", "hello", search=True).grounding[0].title == "stub"


def test_fr_053_embed_sends_one_content_per_text_and_checks_count(settings):
    from google.genai import types

    from getnet_multi_agent.core.gemini_client import GeminiClient
    from getnet_multi_agent.core.llm import LLMUnavailable

    class Aggregating:  # gemini-embedding-2 behaviour with a plain list of strings
        def embed_content(self, **kw):
            assert all(isinstance(c, types.Content) for c in kw["contents"])
            return NS(embeddings=[NS(values=[0.1])])

    gc = GeminiClient(settings, client=NS(models=Aggregating()), sleep=lambda s: None)
    with pytest.raises(LLMUnavailable):
        gc.embed(["a", "b"], "RETRIEVAL_DOCUMENT")
