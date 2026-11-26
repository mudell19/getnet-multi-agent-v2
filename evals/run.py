"""Eval runner against the live API: code checks, LLM judge, repetition policy, report, thresholds.

Usage: uv run python evals/run.py [--base-url URL] [--dataset FILE | --heldout FILE] [--no-judge]
Exit: 0 thresholds met, 1 below thresholds, 2 held-out hash mismatch/unreadable.
"""

import argparse
import hashlib
import hmac
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge as judge_mod  # noqa: E402

THRESHOLDS = {
    "routing_accuracy": 0.90, "refusal_rate": 1.0, "citation_rate": 0.95,
    "source_match": 0.80, "correctness": 4.0, "groundedness": 4.0,
}
JUDGE_METRICS = {"correctness", "groundedness"}
DEFAULT_STATUS = {"refusal": "refused", "escalation": "awaiting_human"}


# ---------------------------------------------------------------- inputs

def load_jsonl(path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def heldout_ok(path, hash_file) -> bool:
    """FR-068: sha256 of the file bytes must equal the first token of the hash file."""
    try:
        want = Path(hash_file).read_text().split()[0].strip().lower()
        got = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (OSError, IndexError):
        return False
    return hmac.compare_digest(got, want)


def default_token_fn(sub: str, role: str) -> str:
    from getnet_multi_agent.core.settings import get_settings
    from getnet_multi_agent.security.auth import issue_token

    return issue_token(get_settings(), sub, role)


# ---------------------------------------------------------------- execution

def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def execute(case: dict, client: httpx.Client, token_fn) -> dict:
    """One run of a case: turns, final message, optional operator resolution."""
    role = case.get("token_role", "merchant")
    headers = {} if role == "none" else {
        "Authorization": f"Bearer {token_fn(case.get('token_sub', case['user_id']), role)}"
    }
    rec = {"http": 0, "body": {}, "final_text": "", "latency_ms": 0, "cost_usd": 0.0, "errors": []}
    cid = None
    try:
        for msg in [*case.get("turns", []), case["message"]]:
            payload = {"message": msg, "user_id": case["user_id"]}
            if cid:
                payload["conversation_id"] = cid
            t0 = time.perf_counter()
            r = client.post("/chat", json=payload, headers=headers)
            rec["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            rec["http"], rec["body"] = r.status_code, _json(r)
            if r.status_code != 200:
                return rec
            total = (rec["body"].get("trace") or {}).get("total") or {}
            rec["cost_usd"] += float(total.get("cost_usd") or 0.0)
            cid = rec["body"].get("conversation_id") or cid
        rec["final_text"] = rec["body"].get("answer", "")
        op = case.get("operator")
        tid = rec["body"].get("ticket_id")
        if op:
            if not tid:
                rec["errors"].append("no ticket_id in escalation response")
                return rec
            oh = {"Authorization": f"Bearer {token_fn('eval-operator', 'operator')}"}
            for step, kw in (("claim", {}), ("resolve", {"json": op})):
                rr = client.post(f"/operator/tickets/{tid}/{step}", headers=oh, **kw)
                if rr.status_code >= 300:
                    rec["errors"].append(f"{step} -> HTTP {rr.status_code}")
                    return rec
            conv = client.get(f"/conversations/{cid}", headers=headers)
            turns = [t for t in _json(conv).get("turns", []) if t.get("role") != "user"]
            rec["final_text"] = turns[-1].get("text", "") if turns else ""
            if not turns:
                rec["errors"].append("conversation has no assistant turn")
    except httpx.HTTPError as e:
        rec["errors"].append(f"transport: {type(e).__name__}")
    return rec


def norm_url(u: str) -> str:
    return u.rstrip("/").lower()


def code_checks(case: dict, rec: dict) -> dict:
    """Flags are True/False, or None when not applicable to the case."""
    fails = list(rec["errors"])
    flags = {"route_ok": None, "refusal_ok": None, "cited": None, "source_ok": None}
    exp_http = case.get("expected_http", 200)
    if rec["http"] != exp_http:
        fails.append(f"http {rec['http']} != {exp_http}")
        return {**flags, "ok": False, "fails": fails}
    if exp_http != 200:
        return {**flags, "ok": not fails, "fails": fails}
    body, route = rec["body"], case["expected_route"]
    flags["route_ok"] = body.get("route") == route
    if not flags["route_ok"]:
        fails.append(f"route {body.get('route')!r} != {route!r}")
    want_status = case.get("expected_status") or DEFAULT_STATUS.get(route, "answered")
    if body.get("status") != want_status:
        fails.append(f"status {body.get('status')!r} != {want_status!r}")
    if route == "refusal":
        flags["refusal_ok"] = body.get("status") == "refused"
    urls = {norm_url(s.get("url", "")) for s in body.get("sources") or []}
    if "knowledge:rag" in route and body.get("status") == "answered":
        flags["cited"] = bool(urls)
    if case.get("source_url"):
        flags["source_ok"] = norm_url(case["source_url"]) in urls
        if not flags["source_ok"]:
            fails.append("source_url not among sources")
    text = rec["final_text"].lower()
    for s in case.get("must_contain", []):
        if s.lower() not in text:
            fails.append(f"missing {s!r}")
    return {**flags, "ok": not fails, "fails": fails}


def judge_run(case, rec, llm):
    body = rec["body"]
    if llm is None or rec["http"] != 200 or not rec["final_text"]:
        return None, 0.0, None
    try:
        jr = judge_mod.judge(case, {**body, "answer": rec["final_text"]}, llm)
        return jr, jr.cost_usd, None
    except Exception as e:  # judge failure must not abort the run
        return None, 0.0, f"judge error: {type(e).__name__}"


def majority(vals):
    vals = [v for v in vals if v is not None]
    return None if not vals else sum(bool(v) for v in vals) * 2 > len(vals)


def evaluate_case(case, client, token_fn, llm, first=1, reruns=3) -> dict:
    runs = []

    def one():
        rec = execute(case, client, token_fn)
        chk = code_checks(case, rec)
        jr, jcost, jerr = judge_run(case, rec, llm)
        if jerr:
            chk["fails"].append(jerr)
        runs.append({"rec": rec, "chk": chk, "judge": jr, "judge_cost": jcost})

    for _ in range(first):
        one()
    if any(not r["chk"]["ok"] for r in runs):
        for _ in range(reruns):
            one()
    last = runs[-1]
    judged = [r for r in runs if r["judge"]]
    jitems = [i.model_dump() for i in judged[0]["judge"].items] if judged else []
    return {
        "id": case["id"], "lang": case["lang"], "category": case["category"],
        "message": case["message"], "expected_route": case["expected_route"],
        "route": last["rec"]["body"].get("route"), "status": last["rec"]["body"].get("status"),
        "http": last["rec"]["http"], "n_runs": len(runs),
        "run_passes": sum(r["chk"]["ok"] for r in runs),
        "code_pass": majority([r["chk"]["ok"] for r in runs]),
        **{k: majority([r["chk"][k] for r in runs]) for k in
           ("route_ok", "refusal_ok", "cited", "source_ok")},
        "judge_pass": majority([r["judge"].all_pass for r in judged if r["judge"].items]),
        "judge_items": jitems, "fails": last["chk"]["fails"],
        "answer": last["rec"]["final_text"],
        "scores": [
            {k: getattr(r["judge"], k) for k in ("correctness", "groundedness", "relevance", "helpfulness")}
            for r in judged if r["rec"]["body"].get("status") != "refused"
        ],
        "latencies_ms": [r["rec"]["latency_ms"] for r in runs],
        "api_cost_usd": sum(r["rec"]["cost_usd"] for r in runs),
        "judge_cost_usd": sum(r["judge_cost"] for r in runs),
    }


# ---------------------------------------------------------------- report

def rate(cases, key):
    v = [c[key] for c in cases if c[key] is not None]
    return sum(v) / len(v) if v else None


def mean_score(cases, key):
    v = [s[key] for c in cases for s in c["scores"]]
    return sum(v) / len(v) if v else None


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def compute_metrics(cases) -> dict:
    return {
        "routing_accuracy": rate(cases, "route_ok"), "citation_rate": rate(cases, "cited"),
        "source_match": rate(cases, "source_ok"), "refusal_rate": rate(cases, "refusal_ok"),
        "correctness": mean_score(cases, "correctness"),
        "groundedness": mean_score(cases, "groundedness"),
        "relevance": mean_score(cases, "relevance"), "helpfulness": mean_score(cases, "helpfulness"),
        "pass_rate": rate(cases, "code_pass"),
    }


def check_thresholds(metrics, thresholds, judged: bool):
    out = []
    for k, t in thresholds.items():
        v = metrics.get(k)
        if v is None or (k in JUDGE_METRICS and not judged):
            out.append((k, v, t, "n/a"))
        else:
            out.append((k, v, t, "PASS" if v >= t else "FAIL"))
    return out


def fmt(v, nd=3):
    return "n/a" if v is None else f"{v:.{nd}f}"


def adjudication(cases):
    return [c for c in cases if c["judge_pass"] is not None and c["judge_pass"] != c["code_pass"]]


def build_report(cases, thresholds, policy, judged) -> tuple[str, list]:
    m = compute_metrics(cases)
    th = check_thresholds(m, thresholds, judged)
    lat = [x for c in cases for x in c["latencies_ms"]]
    n_runs = sum(c["n_runs"] for c in cases)
    api = sum(c["api_cost_usd"] for c in cases)
    jc = sum(c["judge_cost_usd"] for c in cases)
    L = ["# Eval report", "", "## Summary", "", "| Metric | Value |", "|---|---|"]
    for k in ("routing_accuracy", "citation_rate", "source_match", "refusal_rate", "correctness",
              "groundedness", "relevance", "helpfulness", "pass_rate"):
        L.append(f"| {k} | {fmt(m[k])} |")
    L += [f"| cases | {len(cases)} |", f"| runs | {n_runs} |", "", "## Results by language", "",
          "| lang | cases | pass rate | routing accuracy |", "|---|---|---|---|"]
    for lang in sorted({c["lang"] for c in cases}):
        sub = [c for c in cases if c["lang"] == lang]
        L.append(f"| {lang} | {len(sub)} | {fmt(rate(sub, 'code_pass'))} | {fmt(rate(sub, 'route_ok'))} |")
    L += ["", "## Latency (client-measured, ms)", "",
          f"p50: {pct(lat, 50)}  p95: {pct(lat, 95)}", "", "## Cost (USD)", "",
          f"- API cost total: {api:.6f}", f"- Judge cost total: {jc:.6f}",
          f"- Cost per request (API, {n_runs} runs): {api / n_runs if n_runs else 0:.6f}",
          f"- Total (API + judge): {api + jc:.6f}", "",
          "## Repetition policy", "", f"`{policy}`: every case runs once (initial runs); cases with "
          "any failed run are re-run (extra runs); a case passes if a majority of its runs pass. "
          "Judge runs on every run with an answer; judge averages exclude refusals.", "",
          "## Thresholds", "", "| metric | value | threshold | verdict |", "|---|---|---|---|"]
    L += [f"| {k} | {fmt(v)} | {t} | {s} |" for k, v, t, s in th]
    ok = all(s != "FAIL" for *_, s in th)
    L += ["", f"**Verdict: {'PASS' if ok else 'FAIL'}**", "", "## Human adjudication", ""]
    adj = adjudication(cases)
    if not adj:
        L.append("No code/judge disagreements." if judged else "Judge disabled.")
    for c in adj:
        bad = [i["criterion"] for i in c["judge_items"] if i["verdict"] == "fail"]
        L.append(f"- `{c['id']}`: code {'pass' if c['code_pass'] else 'fail'}, judge "
                 f"{'pass' if c['judge_pass'] else 'fail'}; failed items: {bad or 'none'}; "
                 f"code failures: {c['fails'] or 'none'}")
    L += ["", "## Per-case results", "", "| id | lang | category | expected route | got route | runs ok | pass |",
          "|---|---|---|---|---|---|---|"]
    for c in cases:
        L.append(f"| {c['id']} | {c['lang']} | {c['category']} | {c['expected_route'] or '-'} | "
                 f"{c['route'] or '-'} | {c['run_passes']}/{c['n_runs']} | {'yes' if c['code_pass'] else 'no'} |")
    return "\n".join(L) + "\n", th


# ---------------------------------------------------------------- CLI

def main(argv=None, *, transport=None, llm=None, token_fn=None,
         heldout_hash_file=HERE / "heldout.sha256", thresholds=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--dataset", default=str(HERE / "dataset.jsonl"))
    ap.add_argument("--heldout", default=None)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--repeats-policy", default="1+3")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--out", default=str(HERE / "report.md"))
    ap.add_argument("--results", default=str(HERE / "results.jsonl"))
    a = ap.parse_args(argv)
    dataset = a.dataset
    if a.heldout:
        if not heldout_ok(a.heldout, heldout_hash_file):
            print("held-out hash mismatch or unreadable: aborting", file=sys.stderr)
            return 2
        dataset = a.heldout
    first, _, extra = a.repeats_policy.partition("+")
    first, reruns = int(first), int(extra or 0)
    cases_in = load_jsonl(dataset)
    token_fn = token_fn or default_token_fn
    if llm is None and not a.no_judge:
        from getnet_multi_agent.core.llm import get_llm
        from getnet_multi_agent.core.settings import get_settings
        llm = get_llm(get_settings())
    if a.no_judge:
        llm = None
    with httpx.Client(base_url=a.base_url, transport=transport, timeout=180) as client:
        with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
            cases = list(ex.map(
                lambda c: evaluate_case(c, client, token_fn, llm, first, reruns), cases_in))
    Path(a.results).write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
    report, th = build_report(cases, thresholds or THRESHOLDS, a.repeats_policy, llm is not None)
    Path(a.out).write_text(report, encoding="utf-8")
    failed = [k for k, _, _, s in th if s == "FAIL"]
    print(f"{len(cases)} cases; report: {a.out}; " + (f"FAIL: {', '.join(failed)}" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
