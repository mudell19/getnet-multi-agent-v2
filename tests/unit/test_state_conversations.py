from getnet_multi_agent.state import conversations as conv
from getnet_multi_agent.state.db import connect


def test_fr_037_other_owner_gets_none(settings):
    db = connect(settings)
    cid = conv.create_conversation(db, "alice")
    assert conv.get_conversation(db, cid, "alice")["id"] == cid
    assert conv.get_conversation(db, cid, "bob") is None
    assert conv.get_conversation(db, "missing", "alice") is None


def test_fr_038_data_survives_new_database_object(settings):
    db = connect(settings)
    cid = conv.create_conversation(db, "alice")
    t1 = conv.append_turn(db, cid, "user", "oi")
    t2 = conv.append_turn(db, cid, "assistant", "ola", route="faq", status="answered")
    conv.save_summary(db, cid, "resumo", t2)

    db2 = connect(settings)
    assert db2 is not db and db2.path == db.path
    assert [t["id"] for t in conv.list_turns(db2, cid)] == [t1, t2]
    summary = conv.get_summary(db2, cid)
    assert summary["text"] == "resumo" and summary["last_turn_id"] == t2
    with db2.conn() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db2.ping()


def test_fr_038_summary_upsert(settings):
    db = connect(settings)
    cid = conv.create_conversation(db, "alice")
    assert conv.get_summary(db, cid) is None
    conv.save_summary(db, cid, "v1", 1)
    conv.save_summary(db, cid, "v2", 2)
    assert conv.get_summary(db, cid)["text"] == "v2"


def test_fr_040_list_turns_in_order_with_sources_list(settings):
    db = connect(settings)
    cid = conv.create_conversation(db, "alice")
    src = [{"url": "https://x", "title": "X"}]
    conv.append_turn(db, cid, "user", "q", request_id="r1")
    conv.append_turn(db, cid, "assistant", "a", route="faq", status="answered", sources=src,
                     request_id="r1")
    turns = conv.list_turns(db, cid)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["sources"] == []
    assert turns[1]["sources"] == src
    assert turns[1]["route"] == "faq" and turns[1]["request_id"] == "r1"


def test_fr_039_last_turns_chronological(settings):
    db = connect(settings)
    cid = conv.create_conversation(db, "alice")
    for i in range(5):
        conv.append_turn(db, cid, "user", f"m{i}")
    assert [t["text"] for t in conv.last_turns(db, cid, 3)] == ["m2", "m3", "m4"]
    assert len(conv.last_turns(db, cid, 10)) == 5
