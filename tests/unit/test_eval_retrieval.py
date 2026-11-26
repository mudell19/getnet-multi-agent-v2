"""T031: retrieval metrics (FR-067)."""

import importlib.util
import json
import math
from pathlib import Path

import httpx
import pytest

EVALS = Path(__file__).resolve().parents[2] / "evals"
spec = importlib.util.spec_from_file_location("eval_retrieval", EVALS / "retrieval.py")
ret = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ret)

A, B, C = "https://site.getnet.com.br/a/", "https://site.getnet.com.br/b/", "https://site.getnet.com.br/c/"


def chunk(url, excerpt=""):
    return {"rank": 1, "url": url, "title": "", "heading": "", "score": 1, "similarity": 1, "excerpt": excerpt}


def test_fr_067_metrics_math_toy():
    chunks = [chunk(C), chunk(A, "tem antecipação"), chunk(A), chunk(B)]
    m = ret.query_metrics(chunks, [A, B], "Antecipacao", k=4)
    assert m["hit"] == 1.0 and m["recall"] == 1.0 and m["mrr"] == 0.5
    assert m["ctx_precision"] == 0.75 and m["ctx_recall"] == 1.0  # accent/case-insensitive
    dcg = 1 / math.log2(3) + 1 / math.log2(5)  # A at rank 2, B at rank 4, dup A ignored
    idcg = 1 + 1 / math.log2(3)
    assert m["ndcg"] == pytest.approx(dcg / idcg)


def test_metrics_cutoff_and_miss():
    m = ret.query_metrics([chunk(C), chunk(C), chunk(A)], [A], "nada", k=2)
    assert m == {"hit": 0.0, "recall": 0.0, "mrr": 0.0, "ndcg": 0.0, "ctx_precision": 0.0, "ctx_recall": 0.0}


def test_fr_067_cli_both_modes_split_by_language(tmp_path):
    ds = tmp_path / "r.jsonl"
    ds.write_text("\n".join(json.dumps(r) for r in [
        {"id": "1", "lang": "en", "query": "pix", "relevant_urls": [A], "expected_fact": "chave Pix"},
        {"id": "2", "lang": "pt", "query": "pix pt", "relevant_urls": [A], "expected_fact": "chave Pix"}]))
    seen = []

    def h(req: httpx.Request):
        assert req.url.path == "/operator/retrieval" and req.headers["authorization"] == "Bearer op"
        q, mode = req.url.params["q"], req.url.params["mode"]
        seen.append((q, mode))
        if mode == "hybrid":
            return httpx.Response(200, json={"chunks": [chunk(A, "a chave Pix vinculada")]})
        return httpx.Response(200, json={"chunks": [chunk(C, "x"), chunk(A, "y")]})

    out = tmp_path / "rep.md"
    code = ret.main(["--dataset", str(ds), "--out", str(out), "--k", "6"],
                    transport=httpx.MockTransport(h), token_fn=lambda: "op")
    assert code == 0 and len(seen) == 4 and {m for _, m in seen} == {"hybrid", "vector"}
    text = out.read_text()
    assert "## Overall" in text and "## EN" in text and "## PT" in text
    assert "| hybrid | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |" in text
    assert "| vector | 1.000 | 1.000 | 0.500 |" in text


def test_shipped_retrieval_dataset():
    rows = [json.loads(ln) for ln in (EVALS / "retrieval.jsonl").read_text().splitlines() if ln.strip()]
    assert len(rows) >= 16
    en = sum(r["lang"] == "en" for r in rows)
    assert en == len(rows) - en
