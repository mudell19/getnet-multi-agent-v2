"""Customer Support tools over simulated merchant data. The merchant id always comes from the Principal."""

from datetime import date, timedelta

from pydantic import BaseModel, Field

from getnet_multi_agent.core.llm import ToolSpec
from getnet_multi_agent.merchants import load_merchant, today_brt

MAX_RANGE_DAYS = 90


class ReceivableItem(BaseModel):
    sale_date: str
    settlement_date: str
    amount: float
    payment_type: str


class ReceivablesResult(BaseModel):
    merchant_found: bool
    from_date: str | None = None
    to_date: str | None = None
    items: list[ReceivableItem] = Field(default_factory=list)
    total: float = 0.0
    error: str | None = None


class TerminalError(BaseModel):
    at: str
    code: str
    kind: str
    message: str


class TerminalInfo(BaseModel):
    id: str
    model: str
    connectivity: str
    last_seen_at: str
    last_errors: list[TerminalError] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class TerminalStatusResult(BaseModel):
    merchant_found: bool
    terminals: list[TerminalInfo] = Field(default_factory=list)
    error: str | None = None


def _parse(d: str | None, default: date) -> date:
    return date.fromisoformat(d) if d else default


def get_receivables(data_dir, merchant_id: str, from_date: str | None = None,
                    to_date: str | None = None, today: date | None = None) -> ReceivablesResult:
    today = today or today_brt()
    try:
        start = _parse(from_date, today - timedelta(days=7))
        end = _parse(to_date, today)
    except ValueError:
        return ReceivablesResult(merchant_found=True, error="invalid date: use YYYY-MM-DD")
    if start > end:
        return ReceivablesResult(merchant_found=True, error="from_date must be on or before to_date")
    if (end - start).days > MAX_RANGE_DAYS:
        return ReceivablesResult(merchant_found=True, error=f"range above {MAX_RANGE_DAYS} days")
    try:
        m = load_merchant(merchant_id, data_dir, today=today)
    except (OSError, ValueError) as e:
        return ReceivablesResult(merchant_found=False, error=f"data unavailable: {type(e).__name__}")
    if m is None:
        return ReceivablesResult(merchant_found=False, error="merchant not found")
    items = [ReceivableItem(**s) for s in m["sales"]
             if start.isoformat() <= s["sale_date"] <= end.isoformat()]
    return ReceivablesResult(merchant_found=True, from_date=start.isoformat(), to_date=end.isoformat(),
                             items=items, total=round(sum(i.amount for i in items), 2))


def get_terminal_status(data_dir, merchant_id: str) -> TerminalStatusResult:
    try:
        m = load_merchant(merchant_id, data_dir)
    except (OSError, ValueError) as e:
        return TerminalStatusResult(merchant_found=False, error=f"data unavailable: {type(e).__name__}")
    if m is None:
        return TerminalStatusResult(merchant_found=False, error="merchant not found")
    return TerminalStatusResult(merchant_found=True,
                                terminals=[TerminalInfo(**t) for t in m["terminals"]])


TOOL_SPECS = [
    ToolSpec(
        name="get_receivables",
        description="Sales of the authenticated merchant with settlement (deposit) dates and amounts, "
                    "filtered by sale date. Defaults to the last 7 days.",
        parameters={
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "first sale date, YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "last sale date, YYYY-MM-DD"},
            },
        },
    ),
    ToolSpec(
        name="get_terminal_status",
        description="Connectivity, last errors (including transaction declines with reason) and "
                    "suggested actions for each card machine of the authenticated merchant.",
        parameters={"type": "object", "properties": {}},
    ),
]


def run_tool(name: str, args: dict, data_dir, merchant_id: str) -> dict:
    """Dispatch a model function call. merchant_id comes from the authenticated principal only."""
    args = args or {}
    if name == "get_receivables":
        return get_receivables(data_dir, merchant_id, args.get("from_date"), args.get("to_date")).model_dump()
    if name == "get_terminal_status":
        return get_terminal_status(data_dir, merchant_id).model_dump()
    return {"error": f"unknown tool {name}"}
