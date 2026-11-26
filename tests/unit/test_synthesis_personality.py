from getnet_multi_agent.agents import escalation
from getnet_multi_agent.agents.personality import fact_lock_ok, personality
from getnet_multi_agent.agents.synthesis import synthesize
from getnet_multi_agent.contracts import Observation
from getnet_multi_agent.core.llm import LLMUnavailable
from getnet_multi_agent.state import audit, conversations, tickets
from getnet_multi_agent.state.db import connect


def test_fr_008_synthesis_keeps_every_part(fake_llm):
    obs = [Observation(step_id="s1", agent="support", status="answered", answer="R$ 1.250,00 on 2026-11-26"),
           Observation(step_id="s2", agent="knowledge", source="rag", status="answered", answer="Advance: credit sales")]
    fake_llm.responses["synthesis"] = "R$ 1.250,00 on 2026-11-26. Advance: credit sales."
    text, _ = synthesize("both?", obs, "en", fake_llm)
    body = fake_llm.calls[0]["contents"]
    assert "R$ 1.250,00" in body and "Advance" in body and "R$ 1.250,00" in text
    fake_llm.responses["synthesis"] = ""
    text, _ = synthesize("both?", obs, "en", fake_llm)
    assert "R$ 1.250,00" in text and "Advance" in text


def test_fr_009_fact_lock_both_directions(fake_llm):
    draft = "Up to 48x. See https://site.getnet.com.br/crediario/"
    assert fact_lock_ok(draft, "Great news: up to 48x! See https://site.getnet.com.br/crediario/")
    assert not fact_lock_ok(draft, "Up to 12x. See https://site.getnet.com.br/crediario/")  # changed
    assert not fact_lock_ok(draft, "Up to 48x.")  # removed URL
    assert not fact_lock_ok("Up to 48x.", "Up to 48x, fee 2,5%.")  # added number
    fake_llm.responses["personality"] = "Up to 12x!"
    text, _, note = personality("Up to 48x.", "en", fake_llm)
    assert text == "Up to 48x." and "fact lock" in note
    fake_llm.responses["personality"] = LLMUnavailable("x")
    assert personality("Up to 48x.", "en", fake_llm)[0] == "Up to 48x."


def test_fr_041_escalation_saves_checkpoint_ticket_and_audit(settings, fake_llm):
    db = connect(settings)
    cid = conversations.create_conversation(db, "cliente1988")
    tid, cp = escalation.escalate(db, settings, cid, "req1", "cliente1988", "no_grounding",
                                  {"lang": "en", "answered_text": "Part A.", "proposed_answer": "Part A."})
    t = tickets.get_ticket(db, tid)
    assert t.status == "open" and t.reason == "no_grounding"
    assert audit.list_audit(db, tid)[0]["action"] == "escalated"
    tickets.claim(db, tid, "op1")
    fake_llm.responses["personality"] = lambda **k: k["contents"].split("\n", 1)[1].rsplit("\n", 1)[0]
    final, _ = escalation.resume(db, settings, tid, "op1", "edit", "Part B from operator.", fake_llm)
    assert "Part A." in final and "Part B from operator." in final
    assert tickets.get_ticket(db, tid).status == "resolved"
    assert [a["action"] for a in audit.list_audit(db, tid)] == ["escalated", "edit"]
