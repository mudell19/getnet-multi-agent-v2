"""T029: eval runner and judge (FR-063, FR-064, FR-065, FR-068). No network, no real LLM."""

import hashlib
import importlib.util
import json
from pathlib import Path

import httpx

from tests.conftest import FakeLLM

EVALS = Path(__file__).resolve().parents[2] / "evals"


def _load(name):
    import sys

    sys.path.insert(0, str(EVALS))
    spec = importlib.util.spec_from_file_location(f"eval_{name}", EVALS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run = _load("run")
URL = "https://site.getnet.com.br/crediario/"


def chat_body(route="knowledge:rag", status="answered", answer="Up to 48 installments.", sources=True, **kw):
    return {
        "answer": answer, "status": status, "refusal_reason": None, "route": route,
        "sources": [{"title": "t", "url": URL}] if sources else [], "ticket_id": kw.get("ticket_id"),
        "conversation_id": "c1", "request_id": "r1",
        "trace": {"observations": [{"evidence": [{"url": URL, "title": "t", "score": 1, "excerpt": "ate 48x"}]}],
                  "total": {"tokens": 10, "cost_usd": 0.01, "latency_ms": 5}},
    }


def case(**kw):
    base = dict(id="x1", lang="en", category="scenario", user_id="cliente1988", message="q",
                expected_route="knowledge:rag", must_mention=["48 installments"], must_not=[],
                source_url=URL, must_contain=["48"])
    base.update(kw)
    return base


def write(tmp_path, cases):
    p = tmp_path / "ds.jsonl"
    p.write_text("".join(json.dumps(c) + "\n" for c in cases))
    return p


def go(tmp_path, cases, handler, llm=None, extra=(), **kw):
    ds = write(tmp_path, cases)
    argv = ["--dataset", str(ds), "--out", str(tmp_path / "report.md"),
            "--results", str(tmp_path / "results.jsonl"), *extra]
    code = run.main(argv, transport=httpx.MockTransport(handler), llm=llm,
                    token_fn=lambda sub, role: f"{sub}:{role}", **kw)
    rep = (tmp_path / "report.md").read_text() if (tmp_path / "report.md").exists() else ""
    return code, rep


def ok_handler(body_fn=lambda msg: chat_body()):
    def h(req: httpx.Request):
        if req.url.path == "/chat":
            if "authorization" not in req.headers:
                return httpx.Response(401, json={"detail": "no token"})
            return httpx.Response(200, json=body_fn(json.loads(req.content)["message"]))
        return httpx.Response(404, json={})
    return h


JUDGE_OK = {"correctness": 5, "groundedness": 5, "relevance": 5, "helpfulness": 5,
            "items": [{"criterion": "48 installments", "kind": "must_mention", "verdict": "pass", "rationale": "ok"}]}


def test_fr_063_code_checks_and_judge_parsing(tmp_path):
    llm = FakeLLM({"judge": JUDGE_OK})
    code, rep = go(tmp_path, [case()], ok_handler(), llm=llm)
    assert code == 0
    res = [json.loads(ln) for ln in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert res[0]["code_pass"] and res[0]["judge_items"][0]["verdict"] == "pass"
    assert res[0]["scores"][0]["correctness"] == 5
    prompt = llm.calls[0]["contents"]
    assert "ate 48x" in prompt and URL in prompt and "48 installments" in prompt
    assert llm.calls[0]["task"] == "judge"


def test_code_check_failures():
    rec = {"http": 200, "errors": [], "final_text": "no number here",
           "body": chat_body(route="support", sources=False)}
    chk = run.code_checks(case(), rec)
    assert not chk["ok"] and chk["route_ok"] is False and chk["source_ok"] is False
    assert any("missing '48'" in f for f in chk["fails"])
    good = run.code_checks(case(source_url=URL.rstrip("/")), {**rec, "body": chat_body(), "final_text": "48"})
    assert good["ok"] and good["cited"] is True
    ref = run.code_checks(case(expected_route="refusal", source_url="", must_contain=[]),
                          {**rec, "body": chat_body(route="refusal", status="refused", sources=False)})
    assert ref["ok"] and ref["refusal_ok"] is True


def test_fr_064_report_metrics_adjudication_and_threshold_exit(tmp_path):
    bad = {**JUDGE_OK, "items": [{"criterion": "48 installments", "kind": "must_mention",
                                  "verdict": "fail", "rationale": "x"}], "correctness": 2, "groundedness": 2}
    code, rep = go(tmp_path, [case()], ok_handler(), llm=FakeLLM({"judge": bad}))
    assert code == 1  # judge averages below 4.0
    for s in ("routing_accuracy", "citation_rate", "source_match",
              "refusal_rate", "correctness", "groundedness", "p50", "p95", "Cost per request",
              "Repetition policy", "`1+3`", "Verdict: FAIL", "## Human adjudication", "`x1`"):
        assert s in rep, s
    assert "## Results by language" in rep and "| en |" in rep


def test_exit_zero_when_all_thresholds_met_and_no_judge(tmp_path):
    code, rep = go(tmp_path, [case()], ok_handler(), extra=["--no-judge"])
    assert code == 0 and "Judge disabled" in rep and "Verdict: PASS" in rep


def test_routing_below_threshold(tmp_path):
    h = ok_handler(lambda m: chat_body(route="support"))
    code, _ = go(tmp_path, [case()], h, extra=["--no-judge"])
    assert code == 1


def test_fr_065_failed_case_rerun_three_times_majority(tmp_path):
    calls = []

    def body_fn(msg):
        calls.append(msg)
        return chat_body(route="support") if len(calls) == 1 else chat_body()

    code, rep = go(tmp_path, [case()], ok_handler(body_fn), extra=["--no-judge"])
    assert len(calls) == 4 and code == 0  # 3 of 4 runs pass
    assert "| 3/4 | yes |" in rep and "`1+3`" in rep


def test_failed_case_always_failing_runs_four_and_fails(tmp_path):
    calls = []
    h = ok_handler(lambda m: calls.append(m) or chat_body(route="support"))
    code, rep = go(tmp_path, [case()], h, extra=["--no-judge"])
    assert len(calls) == 4 and code == 1 and "| 0/4 | no |" in rep


def test_authorization_and_http_expectation(tmp_path):
    c = case(id="z1", expected_route="", expected_http=401, token_role="none", must_contain=[],
             must_mention=[], source_url="")
    code, _ = go(tmp_path, [c], ok_handler(), extra=["--no-judge"])
    assert code == 0
    res = json.loads((tmp_path / "results.jsonl").read_text().splitlines()[0])
    assert res["http"] == 401 and res["code_pass"]


def test_memory_turns_and_operator_flow(tmp_path):
    seen = []

    def h(req):
        p = req.url.path
        if p == "/chat":
            payload = json.loads(req.content)
            seen.append(payload)
            return httpx.Response(200, json=chat_body(route="escalation", status="awaiting_human",
                                                      answer="escalated", sources=False, ticket_id="t9"))
        if p.startswith("/operator/tickets/t9/"):
            assert req.headers["authorization"].endswith(":operator")
            if p.endswith("/resolve"):
                seen.append(json.loads(req.content))
            return httpx.Response(200, json={})
        if p == "/conversations/c1":
            return httpx.Response(200, json={"id": "c1", "turns": [
                {"role": "user", "text": "hi"}, {"role": "assistant", "text": "Hello, a specialist will call you."}]})
        return httpx.Response(404, json={})

    c = case(id="h2", category="hitl", expected_route="escalation", must_contain=["specialist"],
             source_url="", must_mention=[], turns=["first turn"],
             operator={"action": "edit", "text": "Hello, a specialist will call you."})
    code, _ = go(tmp_path, [c], h, extra=["--no-judge"])
    assert code == 0
    assert "conversation_id" not in seen[0] and seen[1]["conversation_id"] == "c1"
    assert seen[1]["message"] == "q" and seen[2] == c["operator"]


def test_fr_068_heldout_hash_mismatch_aborts_and_match_accepted(tmp_path):
    held = write(tmp_path, [case()])
    hashfile = tmp_path / "h.sha256"
    hashfile.write_text("0" * 64 + "  heldout.jsonl\n")
    argv = ["--heldout", str(held), "--no-judge", "--out", str(tmp_path / "r.md"),
            "--results", str(tmp_path / "r.jsonl")]
    kw = dict(transport=httpx.MockTransport(ok_handler()), token_fn=lambda s, r: "t", heldout_hash_file=hashfile)
    assert run.main(argv, **kw) == 2 and not (tmp_path / "r.md").exists()
    hashfile.write_text(hashlib.sha256(held.read_bytes()).hexdigest() + "  heldout.jsonl\n")
    assert run.main(argv, **kw) == 0 and (tmp_path / "r.md").exists()
    assert run.main(argv, **{**kw, "heldout_hash_file": tmp_path / "missing"}) == 2


def test_fr_061_fr_062_shipped_dataset_parses_with_required_fields():
    rows = run.load_jsonl(EVALS / "dataset.jsonl")
    need = {"id", "lang", "category", "user_id", "message", "expected_route", "must_mention",
            "must_not", "source_url"}
    assert all(need <= r.keys() for r in rows) and len({r["id"] for r in rows}) == len(rows)
    assert {"scenario", "compound", "adversarial", "authorization", "memory", "hitl"} <= {r["category"] for r in rows}


def test_judge_evidence_includes_tool_results_and_marks_web_sources():
    obs = [
        {"agent": "support", "source": None, "evidence": [],
         "data": {"get_receivables": {"items": [{"amount": 1250.0, "settlement_date": "2026-11-26"}]}}},
        {"agent": "knowledge", "source": "web",
         "evidence": [{"url": "https://w.example/eur", "title": "Euro rate", "excerpt": ""}]},
        {"agent": "knowledge", "source": "rag", "evidence": [{"url": URL, "excerpt": "ate 48x"}]},
    ]
    lines = run.judge_mod.evidence_lines(obs)
    assert any(ln.startswith("- [tool get_receivables] ") and "1250.0" in ln for ln in lines)
    assert "- [web] Euro rate (https://w.example/eur)" in lines
    assert f"- {URL}: ate 48x" in lines


def test_each_judgment_starts_with_a_fresh_token_budget():
    from getnet_multi_agent.contracts import Usage
    from getnet_multi_agent.core import request_context

    seen = []

    def judge_resp(**kw):
        seen.append(request_context.tokens_used())
        request_context.add_usage(Usage(prompt_tokens=50_000))  # above REQUEST_TOKEN_BUDGET
        return JUDGE_OK

    llm = FakeLLM({"judge": judge_resp})
    for _ in range(3):
        run.judge_mod.judge(case(), chat_body(), llm)
    assert seen == [0, 0, 0]


def test_answer_evidence_and_judge_items_come_from_the_same_run(tmp_path):
    answers = iter(["run 1", "run 2", "run 3", "run 4"])
    fail = {**JUDGE_OK, "items": [{**JUDGE_OK["items"][0], "verdict": "fail"}]}
    llm = FakeLLM({"judge": [fail, fail, fail, JUDGE_OK]})
    body = lambda msg: chat_body(answer=next(answers), sources=False)  # noqa: E731 - code check fails, so 3 reruns
    go(tmp_path, [case(must_contain=[])], ok_handler(body), llm=llm)
    res = json.loads((tmp_path / "results.jsonl").read_text().splitlines()[0])
    assert res["n_runs"] == 4
    assert res["answer"] == "run 4" and "run 4" in llm.calls[-1]["contents"]
    assert res["judge_items"][0]["verdict"] == "pass"
    assert res["evidence"] == [f"- {URL}: ate 48x"]
