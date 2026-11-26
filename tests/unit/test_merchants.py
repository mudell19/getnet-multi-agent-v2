from datetime import date
from pathlib import Path

from getnet_multi_agent.merchants import load_merchant

DATA = Path(__file__).resolve().parents[2] / "data"


def test_fr_024_cliente1988_terminals_and_relative_sales():
    m = load_merchant("cliente1988", DATA, today=date(2026, 11, 26))
    by_id = {t["id"]: t for t in m["terminals"]}
    assert by_id["T-1001"]["connectivity"] == "offline"
    assert by_id["T-1001"]["last_errors"][0]["kind"] == "connectivity"
    assert by_id["T-1002"]["connectivity"] == "online"
    assert by_id["T-1002"]["last_errors"][0]["kind"] == "transaction_decline"
    yesterday = [s for s in m["sales"] if s["sale_date"] == "2026-11-25"]
    assert len(yesterday) >= 2 and all(s["settlement_date"] and s["amount"] > 0 for s in yesterday)
    assert {s["sale_date"] for s in m["sales"]} >= {"2026-11-21", "2026-11-24"}


def test_fr_024_second_merchant_and_unknown():
    assert load_merchant("cliente2000", DATA)["terminals"][0]["id"] == "T-2001"
    assert load_merchant("cliente9999", DATA) is None
