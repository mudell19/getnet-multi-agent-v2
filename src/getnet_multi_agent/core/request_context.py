"""Per-request context: request id, token counter and usage list. Safe outside a request."""

import uuid
from contextvars import ContextVar

from getnet_multi_agent.contracts import Usage

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_tokens: ContextVar[list[int] | None] = ContextVar("tokens", default=None)
_usages: ContextVar[list[Usage] | None] = ContextVar("usages", default=None)
_budget: ContextVar[int | None] = ContextVar("budget", default=None)


def start_request(request_id: str | None = None, budget: int | None = None) -> str:
    rid = request_id or uuid.uuid4().hex
    _request_id.set(rid)
    _tokens.set([0])
    _usages.set([])
    _budget.set(budget)
    return rid


def get_request_id() -> str:
    return _request_id.get()


def add_usage(usage: Usage) -> None:
    counter, items = _tokens.get(), _usages.get()
    if counter is None or items is None:
        counter, items = [0], []
        _tokens.set(counter)
        _usages.set(items)
    counter[0] += usage.prompt_tokens + usage.output_tokens + usage.thinking_tokens
    items.append(usage)


def tokens_used() -> int:
    counter = _tokens.get()
    return counter[0] if counter else 0


def usages() -> list[Usage]:
    return list(_usages.get() or [])


def budget_remaining(budget: int) -> int:
    return max(0, budget - tokens_used())
