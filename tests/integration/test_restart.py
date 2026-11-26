from fastapi.testclient import TestClient

from getnet_multi_agent.api.app import create_app
from getnet_multi_agent.core.settings import get_settings


def test_fr_038_conversation_survives_restart(client, auth, settings, fake_llm):
    d = client.post("/chat", json={"message": "How does the Payment Link work?", "user_id": "cliente1988"},
                    headers=auth()).json()
    cid = d["conversation_id"]
    # a brand-new app instance on the same database file
    app2 = create_app(settings, fake_llm, run_ingestion=False)
    app2.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app2) as c2:
        turns = c2.get(f"/conversations/{cid}", headers=auth()).json()["turns"]
        assert [t["role"] for t in turns] == ["user", "assistant"]
        r = c2.post("/chat", json={"message": "and how much is it?", "user_id": "cliente1988",
                                   "conversation_id": cid}, headers=auth())
        assert r.status_code == 200 and r.json()["conversation_id"] == cid
