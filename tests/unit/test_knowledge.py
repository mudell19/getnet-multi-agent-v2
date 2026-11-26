import pytest

from getnet_multi_agent.agents import knowledge
from getnet_multi_agent.contracts import AgentResult, RankedChunk, Step
from getnet_multi_agent.core.llm import GroundingSource, LLMResult

BR = RankedChunk(id="a", url="https://site.getnet.com.br/crediario/", heading="Crediário",
                 text="Ofereça parcelamento em até 48x para o seu cliente. Cada emissor define o limite.",
                 site="br", is_rule=True, similarity=0.8, score=0.9)
GLOBAL = RankedChunk(id="b", url="https://www.getnet.net/en/our-solutions/in-person-payments",
                     heading="In-person", text="POS terminals for in-person payments.", site="global",
                     similarity=0.7, score=0.7)


@pytest.fixture
def chunks(monkeypatch):
    holder = {"chunks": [BR, GLOBAL]}
    monkeypatch.setattr(knowledge, "retrieve", lambda *a, **k: holder["chunks"])
    return holder


def step(q="How many installments with crediário?"):
    return Step(id="s1", agent="knowledge", source="rag", query=q)


def test_fr_021_grounded_answer_cites_sources_with_evidence(settings, fake_llm, chunks):
    fake_llm.responses["knowledge"] = AgentResult(answer="Up to 48 installments (48x).", grounded=True,
                                                  cited_ids=["0"])
    obs = knowledge.knowledge_rag(step(), "en", fake_llm, settings)
    assert obs.status == "answered" and obs.data["cited_urls"] == [BR.url]
    assert "48x" in obs.evidence[0].excerpt and obs.evidence[0].url == BR.url
    assert "<context>" in fake_llm.calls[0]["contents"]


def test_fr_021_no_grounding_does_not_guess(settings, fake_llm, chunks):
    fake_llm.responses["knowledge"] = AgentResult(answer="Not found.", grounded=False, cited_ids=[])
    obs = knowledge.knowledge_rag(step(), "en", fake_llm, settings)
    assert obs.status == "no_grounding" and obs.answer == ""
    chunks["chunks"] = []
    obs = knowledge.knowledge_rag(step(), "en", fake_llm, settings)
    assert obs.status == "no_grounding" and len(fake_llm.calls) == 1  # no LLM call without context


def test_fr_019_prompt_keeps_alternatives_and_rules(settings):
    from getnet_multi_agent.agents.prompts.knowledge import RAG_SYSTEM

    assert "alternative" in RAG_SYSTEM and "requirement" in RAG_SYSTEM


def test_fr_020_global_site_flagged(settings, fake_llm, chunks):
    fake_llm.responses["knowledge"] = AgentResult(answer="POS terminals.", grounded=True, cited_ids=["1"])
    obs = knowledge.knowledge_rag(step("in-person payments"), "en", fake_llm, settings)
    assert obs.data["global_site"] is True


def test_fr_022_web_search_is_a_search_only_call(settings, fake_llm):
    fake_llm.responses["knowledge"] = LLMResult(
        text="EUR/BRL 6.10", grounding=[GroundingSource(title="bcb.gov.br", uri="https://vertexaisearch/x")],
        search_queries=["euro hoje"])
    obs = knowledge.knowledge_web(Step(id="s1", agent="knowledge", source="web", query="euro rate"),
                                  "en", fake_llm, settings)
    call = fake_llm.calls[0]
    assert call["search"] is True and not call["tools"]
    assert obs.status == "answered" and obs.evidence[0].title == "bcb.gov.br"
