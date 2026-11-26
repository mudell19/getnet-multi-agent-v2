import io
import json
import logging

from getnet_multi_agent.contracts import Usage
from getnet_multi_agent.core import metrics, request_context
from getnet_multi_agent.core.logging import JsonFormatter, get_logger


def test_request_context_defaults_and_usage():
    rid = request_context.start_request()
    assert len(rid) == 32 and request_context.get_request_id() == rid
    assert request_context.tokens_used() == 0
    request_context.add_usage(Usage(prompt_tokens=10, output_tokens=5, thinking_tokens=2))
    assert request_context.tokens_used() == 17
    assert len(request_context.usages()) == 1
    assert request_context.budget_remaining(20) == 3
    assert request_context.start_request("abc") == "abc"
    assert request_context.tokens_used() == 0 and request_context.usages() == []


def test_fr_057_log_line_is_json_with_request_id():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    log = get_logger("test.obs")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    request_context.start_request("req-123")
    log.info("hello", extra={"fields": {"task": "router", "tokens": 7}})
    log.removeHandler(handler)
    data = json.loads(buf.getvalue().strip())
    assert data["request_id"] == "req-123"
    assert data["msg"] == "hello" and data["task"] == "router" and data["tokens"] == 7
    assert {"ts", "level", "logger"} <= data.keys()


def test_fr_058_render_has_all_metrics_and_ticket_values():
    metrics.REQUESTS.labels("knowledge", "answered").inc()
    metrics.LATENCY.observe(1.2)
    metrics.record_llm(Usage(model="m", prompt_tokens=3, output_tokens=2, cost_usd=0.01))
    metrics.REPLANS.inc()
    metrics.REFUSALS.labels("unsafe").inc()
    metrics.ESCALATIONS.labels("no_grounding").inc()
    metrics.set_ticket_stats_provider(lambda: (4, 123.0))
    try:
        body, ctype = metrics.render()
    finally:
        metrics.set_ticket_stats_provider(None)
    text = body.decode()
    for name in (
        "getnet_requests_total", "getnet_request_latency_seconds", "getnet_llm_tokens_total",
        "getnet_llm_cost_usd_total", "getnet_replans_total", "getnet_refusals_total",
        "getnet_escalations_total", "getnet_tickets_open", "getnet_ticket_oldest_age_seconds",
    ):
        assert name in text
    assert "getnet_tickets_open 4.0" in text
    assert "getnet_ticket_oldest_age_seconds 123.0" in text
    assert ctype.startswith("text/plain")
