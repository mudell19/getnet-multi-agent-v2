import pytest

from getnet_multi_agent.contracts import RankedChunk
from getnet_multi_agent.core.settings import Settings
from getnet_multi_agent.rag.glossary import expand, matched_groups
from getnet_multi_agent.rag.ingest import ingest
from getnet_multi_agent.rag.retriever import retrieve, score_chunk
from tests.conftest import ROOT, FakeLLM

QUERY = "Can I sell through WhatsApp using the Payment Link?"


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    data = tmp_path_factory.mktemp("kb")
    s = Settings(_env_file=None, DATA_DIR=str(data), LLM_MODE="stub", RAG_MIN_SIMILARITY=0.0)
    llm = FakeLLM()
    ingest(s, llm, cache_dir=ROOT / "data" / "crawl_cache")
    return s, llm


def test_fr_017_glossary_maps_payment_link_to_pt():
    assert matched_groups("Payment Link") == matched_groups("link de pagamento") != set()
    assert "Link de Pagamento".lower() in expand("How does the Payment Link work?").lower()
    assert matched_groups("antecipação") == matched_groups("ANTECIPACAO")
    assert matched_groups("my pixel") == set()  # whole-word matching


def test_fr_017_payment_link_query_returns_link_page(kb):
    s, llm = kb
    out = retrieve(s, llm, QUERY, mode="hybrid", k=6)
    assert any("/link-de-pagamento" in c.url for c in out)


def test_fr_018_rule_outranks_mention_at_equal_similarity():
    rule = score_chunk(0.5, 1, True)
    mention = score_chunk(0.5, 1, False)
    assert rule == pytest.approx(mention + 0.10)
    assert score_chunk(0.5, 5, False) == pytest.approx(0.7)  # glossary boost capped at 0.20
    assert score_chunk(0.5, 1, True, hybrid=False) == 0.5


def test_fr_018_min_similarity_threshold(kb):
    s, llm = kb
    strict = s.model_copy(update={"RAG_MIN_SIMILARITY": 5.0})
    assert retrieve(strict, llm, QUERY) == []


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
def test_fr_051_modes_return_sorted_ranked_chunks(kb, mode):
    s, llm = kb
    out = retrieve(s, llm, QUERY, mode=mode, k=5)
    assert 0 < len(out) <= 5
    assert all(isinstance(c, RankedChunk) for c in out)
    scores = [c.score for c in out]
    assert scores == sorted(scores, reverse=True)
    if mode == "vector":
        assert all(c.score == c.similarity for c in out)
