"""Static checks of delivery artefacts. Behaviour is proven by promtool, the container smoke test and
the clean-clone run; these tests only keep the contracts from drifting."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return (ROOT / p).read_text()


def test_fr_059_alert_rules_each_have_promtool_tests():
    rules, tests = read("ops/prometheus/alerts.yml"), read("ops/prometheus/alerts_test.yml")
    for alert in ("HighErrorRate", "HighLatencyP95", "HighCostPerHour", "StaleTicket"):
        assert f"alert: {alert}" in rules and alert in tests


def test_fr_060_dashboard_provisioned_under_profile():
    dash = json.loads(read("ops/grafana/dashboards/getnet.json"))
    exprs = json.dumps(dash)
    for metric in ("getnet_requests_total", "getnet_request_latency_seconds", "getnet_llm_cost_usd_total",
                   "getnet_tickets_open", "getnet_ticket_oldest_age_seconds", "getnet_refusals_total"):
        assert metric in exprs
    compose = read("compose.yaml")
    assert compose.count("observability") >= 2


def test_fr_069_image_and_compose_contract():
    df, compose = read("Dockerfile"), read("compose.yaml")
    assert re.search(r"FROM python:3\.12-slim@sha256:[0-9a-f]{64}", df)
    assert "USER app" in df and "HEALTHCHECK" in df and "--frozen" in df
    assert "max-size" in compose and "healthcheck" in compose and "/app/data/state" in compose
    assert ".env" in read(".dockerignore").split()


def test_fr_070_ci_workflows():
    ci, live = read(".github/workflows/ci.yml"), read(".github/workflows/live-eval.yml")
    for needle in ("ruff", "pytest", "LLM_MODE", "promtool"):
        assert needle in ci
    assert "sessao-*" in live and "evals/run.py" in live and "evals/retrieval.py" in live


def test_fr_071_readme_sections():
    readme = read("README.md")
    for topic in ("Quick start", "Architecture", "Supervisor", "RAG", "Tools", "Human", "Evaluation",
                  "Observability", "CI", "Known limits"):
        assert topic.lower() in readme.lower(), topic
    assert "docs/agent-workflow.png" in readme


def test_fr_072_threat_model_maps_requirements():
    tm = read("docs/threat-model.md")
    assert "prompt injection" in tm.lower() and len(set(re.findall(r"FR-\d{3}", tm))) >= 10
