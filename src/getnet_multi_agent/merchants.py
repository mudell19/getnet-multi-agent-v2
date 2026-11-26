"""Simulated merchant data loader. Offsets in data/merchants.json are resolved against today (UTC-03:00)."""

import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

BRT = timezone(timedelta(hours=-3))  # Brazil has no DST since 2019


def today_brt() -> date:
    return datetime.now(BRT).date()


def load_merchant(merchant_id: str, data_dir: str | Path = "data", today: date | None = None,
                  now: datetime | None = None) -> dict | None:
    raw = json.loads((Path(data_dir) / "merchants.json").read_text(encoding="utf-8"))
    m = raw["merchants"].get(merchant_id)
    if m is None:
        return None
    today = today or today_brt()
    now = now or datetime.now(UTC)
    terminals = []
    for t in m["terminals"]:
        terminals.append({
            "id": t["id"],
            "model": t["model"],
            "connectivity": t["connectivity"],
            "last_seen_at": (now - timedelta(minutes=t["last_seen_minutes_ago"])).isoformat(timespec="minutes"),
            "last_errors": [
                {"at": (now - timedelta(minutes=e["minutes_ago"])).isoformat(timespec="minutes"),
                 "code": e["code"], "kind": e["kind"], "message": e["message"]}
                for e in t["last_errors"]
            ],
            "suggested_actions": list(t["suggested_actions"]),
        })
    sales = [
        {
            "sale_date": (today + timedelta(days=s["day_offset"])).isoformat(),
            "settlement_date": (today + timedelta(days=s["settlement_day_offset"])).isoformat(),
            "amount": s["amount"],
            "payment_type": s["payment_type"],
        }
        for s in m["sales"]
    ]
    return {"merchant_id": merchant_id, "name": m["name"], "terminals": terminals, "sales": sales}
