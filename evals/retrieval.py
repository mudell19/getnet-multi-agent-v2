"""Retrieval metrics (FR-067): Hit@k, Recall@k, MRR, nDCG@k, context precision/recall; hybrid vs vector.

Usage: uv run python evals/retrieval.py [--base-url URL] [--k 6] [--dataset FILE] [--out FILE]
"""

import argparse
import json
import math
import sys
import unicodedata
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
MODES = ("hybrid", "vector")
METRICS = ("hit", "recall", "mrr", "ndcg", "ctx_precision", "ctx_recall")
LABELS = {"hit": "Hit@k", "recall": "Recall@k", "mrr": "MRR", "ndcg": "nDCG@k",
          "ctx_precision": "Context precision", "ctx_recall": "Context recall"}


def norm_url(u: str) -> str:
    return u.rstrip("/").lower()


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def query_metrics(chunks: list[dict], relevant: list[str], fact: str, k: int) -> dict:
    chunks = chunks[:k]
    rel = {norm_url(u) for u in relevant}
    urls = [norm_url(c.get("url", "")) for c in chunks]
    is_rel = [u in rel for u in urls]
    seen, dcg = set(), 0.0
    for i, u in enumerate(urls, 1):
        if u in rel and u not in seen:  # gain once per distinct relevant url
            seen.add(u)
            dcg += 1 / math.log2(i + 1)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(rel)) + 1))
    first = next((i for i, r in enumerate(is_rel, 1) if r), None)
    text = fold(" ".join(f"{c.get('excerpt', '')} {c.get('text', '')}" for c in chunks))
    return {
        "hit": float(any(is_rel)),
        "recall": len(seen) / len(rel) if rel else 0.0,
        "mrr": 1 / first if first else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
        "ctx_precision": sum(is_rel) / len(chunks) if chunks else 0.0,
        "ctx_recall": float(fold(fact) in text),
    }


def mean(rows: list[dict]) -> dict:
    return {m: sum(r[m] for r in rows) / len(rows) for m in METRICS} if rows else dict.fromkeys(METRICS, 0.0)


def fetch(client: httpx.Client, headers: dict, q: str, mode: str) -> list[dict]:
    r = client.get("/operator/retrieval", params={"q": q, "mode": mode}, headers=headers)
    r.raise_for_status()
    return r.json().get("chunks", [])


def run(queries: list[dict], client: httpx.Client, headers: dict, k: int) -> dict:
    """-> {mode: [{lang, id, **metrics}]}"""
    out = {m: [] for m in MODES}
    for q in queries:
        for mode in MODES:
            chunks = fetch(client, headers, q["query"], mode)
            out[mode].append({"id": q["id"], "lang": q["lang"],
                              **query_metrics(chunks, q["relevant_urls"], q["expected_fact"], k)})
    return out


def build_report(results: dict, k: int) -> str:
    langs = sorted({r["lang"] for rows in results.values() for r in rows})
    L = ["# Retrieval report", "", f"k = {k}; queries: {len(results[MODES[0]])}; "
         "relevance by URL (binary).", ""]
    for scope in ["all", *langs]:
        L += [f"## {'Overall' if scope == 'all' else scope.upper()}", "",
              "| mode | " + " | ".join(LABELS[m] for m in METRICS) + " |",
              "|---|" + "---|" * len(METRICS)]
        for mode in MODES:
            rows = [r for r in results[mode] if scope in ("all", r["lang"])]
            mm = mean(rows)
            L.append(f"| {mode} | " + " | ".join(f"{mm[m]:.3f}" for m in METRICS) + " |")
        L.append("")
    return "\n".join(L)


def main(argv=None, *, transport=None, token_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--dataset", default=str(HERE / "retrieval.jsonl"))
    ap.add_argument("--out", default=str(HERE / "retrieval_report.md"))
    a = ap.parse_args(argv)
    if token_fn is None:
        from getnet_multi_agent.core.settings import get_settings
        from getnet_multi_agent.security.auth import issue_token

        def token_fn():
            return issue_token(get_settings(), "eval-operator", "operator")
    queries = [json.loads(ln) for ln in Path(a.dataset).read_text(encoding="utf-8").splitlines() if ln.strip()]
    with httpx.Client(base_url=a.base_url, transport=transport, timeout=60) as client:
        res = run(queries, client, {"Authorization": f"Bearer {token_fn()}"}, a.k)
    Path(a.out).write_text(build_report(res, a.k), encoding="utf-8")
    print(f"{len(queries)} queries -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
