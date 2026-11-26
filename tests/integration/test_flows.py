"""End-to-end flows over HTTP with the LLM faked at the wrapper."""

from getnet_multi_agent.contracts import Plan, Step

from .conftest import support_script


def test_fr_005_connectivity_flow_replans_over_http(client, auth):
    client.fake.responses["router"] = Plan(standalone="q", lang="en", parts=["q"],
                                           steps=[Step(id="s1", agent="support", query="won't connect")])
    client.fake.responses["support"] = support_script("Terminal T-1001 is offline.")
    d = client.post("/chat", json={"message": "My card machine won't connect to the internet, what should I do?",
                                   "user_id": "cliente1988"}, headers=auth()).json()
    assert d["route"] == "support>knowledge:rag"
    assert any(r["action"] == "add" for r in d["trace"]["plan_revisions"])


def test_fr_039_follow_up_uses_memory(client, auth):
    d = client.post("/chat", json={"message": "How does the Payment Link work?", "user_id": "cliente1988"},
                    headers=auth()).json()
    client.post("/chat", json={"message": "and how much is it?", "user_id": "cliente1988",
                               "conversation_id": d["conversation_id"]}, headers=auth())
    router_prompt = [c for c in client.fake.calls if c["task"] == "router"][-1]["contents"]
    assert "How does the Payment Link work?" in router_prompt and "and how much is it?" in router_prompt


def test_fr_030_planned_refusal_over_http(client, auth):
    client.fake.responses["router"] = Plan(standalone="poem", lang="en", refusal_reason="out_of_scope")
    d = client.post("/chat", json={"message": "Write me a poem", "user_id": "cliente1988"}, headers=auth()).json()
    assert (d["status"], d["refusal_reason"], d["route"]) == ("refused", "out_of_scope", "refusal")


def test_fr_055_llm_failure_returns_json_and_escalates(client, auth):
    from getnet_multi_agent.core.llm import LLMUnavailable

    client.fake.responses["router"] = LLMUnavailable("down")
    r = client.post("/chat", json={"message": "hello", "user_id": "cliente1988"}, headers=auth())
    assert r.status_code == 200 and r.json()["status"] == "awaiting_human" and r.json()["ticket_id"]
