import pytest
from pydantic import ValidationError

from getnet_multi_agent.contracts import ChatResponse, Plan, Step
from getnet_multi_agent.core.llm import hash_embedding


def test_fr_002_plan_is_typed():
    plan = Plan.model_validate(
        {"steps": [{"id": "s1", "agent": "knowledge", "source": "rag", "query": "q"}],
         "lang": "pt", "standalone": "q"}
    )
    assert plan.steps[0].source == "rag" and plan.lang == "pt"
    with pytest.raises(ValidationError):
        Step.model_validate({"id": "s1", "agent": "poet", "query": "q"})
    with pytest.raises(ValidationError):
        Plan.model_validate({"steps": [], "lang": "es", "standalone": "q"})


def test_fr_047_chat_response_fields():
    r = ChatResponse(answer="a", status="refused", refusal_reason="unsafe", route="refusal",
                     conversation_id="c", request_id="r")
    d = r.model_dump()
    for key in ("answer", "status", "refusal_reason", "route", "sources", "ticket_id",
                "conversation_id", "request_id", "trace"):
        assert key in d


def test_fr_003_hash_embedding_is_deterministic_and_normalized():
    a = hash_embedding("Link de Pagamento WhatsApp")
    assert a == hash_embedding("Link de Pagamento WhatsApp")
    assert len(a) == 768 and abs(sum(v * v for v in a) - 1) < 1e-9
