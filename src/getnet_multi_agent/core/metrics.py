"""Prometheus metrics (module-level) and the /metrics renderer."""

from collections.abc import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from getnet_multi_agent.contracts import Usage

REQUESTS = Counter("getnet_requests_total", "Chat requests", ["route", "status"])
LATENCY = Histogram(
    "getnet_request_latency_seconds", "Request latency", buckets=(0.5, 1, 2, 4, 8, 15, 30, 60)
)
LLM_TOKENS = Counter("getnet_llm_tokens_total", "LLM tokens", ["model", "kind"])
LLM_COST = Counter("getnet_llm_cost_usd_total", "LLM cost in USD", ["model"])
REPLANS = Counter("getnet_replans_total", "Supervisor replans")
REFUSALS = Counter("getnet_refusals_total", "Refusals", ["reason"])
ESCALATIONS = Counter("getnet_escalations_total", "Escalations", ["reason"])
TICKETS_OPEN = Gauge("getnet_tickets_open", "Open tickets")
TICKET_OLDEST_AGE = Gauge("getnet_ticket_oldest_age_seconds", "Age of the oldest open ticket")

_ticket_stats: Callable[[], tuple[int, float]] | None = None


def set_ticket_stats_provider(fn: Callable[[], tuple[int, float]] | None) -> None:
    global _ticket_stats
    _ticket_stats = fn


def record_llm(usage: Usage) -> None:
    LLM_TOKENS.labels(usage.model, "prompt").inc(usage.prompt_tokens)
    LLM_TOKENS.labels(usage.model, "output").inc(usage.output_tokens)
    LLM_TOKENS.labels(usage.model, "thinking").inc(usage.thinking_tokens)
    LLM_COST.labels(usage.model).inc(usage.cost_usd)


def render() -> tuple[bytes, str]:
    if _ticket_stats is not None:
        count, oldest = _ticket_stats()
        TICKETS_OPEN.set(count)
        TICKET_OLDEST_AGE.set(oldest)
    return generate_latest(), CONTENT_TYPE_LATEST
