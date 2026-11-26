"""HTTP-level fixtures: the real FastAPI app with the LLM faked at the wrapper (FakeLLM)."""

import pytest
from fastapi.testclient import TestClient

from getnet_multi_agent.agents import knowledge
from getnet_multi_agent.api.app import create_app
from getnet_multi_agent.contracts import AgentResult, Plan, RankedChunk, Step
from getnet_multi_agent.core.llm import FunctionCall, LLMResult
from getnet_multi_agent.core.settings import get_settings
from getnet_multi_agent.security.auth import issue_token

CHUNK = RankedChunk(id="c1", url="https://site.getnet.com.br/link-de-pagamento/", heading="Link de Pagamento",
                    text="Faça vendas usando o WhatsApp ou sua rede social com o Link de Pagamento.",
                    site="br", similarity=0.8, score=0.9)


def passthrough(**k):
    return k["contents"].split("\n", 1)[1].rsplit("\n", 1)[0]


def default_responses(fake_llm, steps, lang="en"):
    fake_llm.responses.update({
        "router": Plan(standalone="q", lang=lang, parts=["q"], steps=steps),
        "knowledge": AgentResult(answer="Yes, via WhatsApp with the Link de Pagamento.", grounded=True,
                                 cited_ids=["0"]),
        "critic": {"complete": True, "missing_parts": []},
        "personality": passthrough,
        "summary": "summary",
        "synthesis": "merged",
    })


def support_script(text, tool="get_terminal_status"):
    return [LLMResult(function_calls=[FunctionCall(name=tool)], content="raw"), LLMResult(text=text)]


RAG = [Step(id="s1", agent="knowledge", source="rag", query="q")]


@pytest.fixture
def client(settings, fake_llm, monkeypatch):
    monkeypatch.setattr(knowledge, "retrieve", lambda *a, **k: [CHUNK])
    app = create_app(settings, fake_llm, run_ingestion=False)
    app.dependency_overrides[get_settings] = lambda: settings
    default_responses(fake_llm, RAG)
    with TestClient(app) as c:
        c.fake = fake_llm
        c.settings = settings
        yield c


@pytest.fixture
def auth(settings):
    def _h(sub="cliente1988", role="merchant"):
        return {"Authorization": f"Bearer {issue_token(settings, sub, role)}"}
    return _h
