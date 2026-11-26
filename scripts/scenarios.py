"""Run the ten official challenge scenarios (plus the compound one) against a running API.

Checks route, status, expected source and, for RAG scenarios, the expected fact both in the trace
evidence and in the answer. Exit 0 only if every scenario passes.
Usage: uv run python scripts/scenarios.py --base-url http://127.0.0.1:8000 [--only s05]
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from getnet_multi_agent.core.settings import get_settings
from getnet_multi_agent.security.auth import issue_token

DUV = "https://site.getnet.com.br/duvidas/"
S = [
    ("s01", "What's the difference between the Get Clássica and the Get Smart?", "knowledge:rag",
     "https://site.getnet.com.br/todas-as-maquininhas/", ["79,90", "129,90"]),
    ("s02", "What's the weather forecast in Porto Alegre tomorrow?", "knowledge:web", None, []),
    ("s03", "When will the money from yesterday's sales be deposited?", "support", None, []),
    ("s04", "Do I need a bank account to receive my sales via Pix?", "knowledge:rag", None, ["chave"]),
    ("s05", "My card machine won't connect to the internet, what should I do?", "support>knowledge:rag",
     DUV, ["teste de comunica"]),
    ("s06", "How does receivables advance (antecipação) work with Getnet?", "knowledge:rag", None,
     ["antecip"]),
    ("s07", "What's the euro exchange rate today?", "knowledge:web", None, []),
    ("s08", "My card machine is showing a transaction decline error.", "support*", None, []),
    ("s09", "How many installments can I split a sale into with the crediário?", "knowledge:rag",
     "https://site.getnet.com.br/crediario/", ["48"]),
    ("s10", "Can I sell through WhatsApp using the Payment Link?", "knowledge:rag",
     "https://site.getnet.com.br/link-de-pagamento/", ["whatsapp"]),
    ("k01", "When will yesterday's sales be deposited and how does receivables advance work?",
     "support>knowledge:rag", None, []),
]
ANSWER_FACT = {"s01": ["79,90", "129,90"], "s05": ["T-1001"], "s08": ["T-1002", "51"], "s09": ["48"],
               "s10": ["WhatsApp"], "s03": ["2026"]}


def norm(u: str) -> str:
    return u.rstrip("/")


def run_one(client, token, case):
    cid, msg, route, source, ev_facts = case
    t0 = time.monotonic()
    r = client.post("/chat", json={"message": msg, "user_id": "cliente1988"},
                    headers={"Authorization": f"Bearer {token}"})
    dt = time.monotonic() - t0
    d = r.json()
    problems = []
    if r.status_code != 200:
        return cid, False, [f"http {r.status_code}"], d, dt
    if (d["route"] != route) if not route.endswith("*") else not d["route"].startswith(route[:-1]):
        problems.append(f"route {d['route']} != {route}")
    if d["status"] != "answered":
        problems.append(f"status {d['status']}")
    urls = [norm(s["url"]) for s in d["sources"]]
    if source and norm(source) not in urls:
        problems.append(f"source {source} not in {urls}")
    if route.endswith("knowledge:web") and not d["sources"]:
        problems.append("no web sources")
    evidence = " ".join(e["excerpt"] for o in d["trace"]["observations"] for e in o["evidence"]).lower()
    for f in ev_facts:
        if f.lower() not in evidence:
            problems.append(f"fact {f!r} missing in trace evidence")
    answer_num = d["answer"].lower().replace(".", ",")  # "R$ 79.90" in English == "R$ 79,90"
    for f in ANSWER_FACT.get(cid, []):
        if f.lower().replace(".", ",") not in answer_num:
            problems.append(f"fact {f!r} missing in answer")
    return cid, not problems, problems, d, dt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    token = issue_token(get_settings(), "cliente1988", "merchant")
    cases = [c for c in S if not a.only or c[0] in a.only]
    with httpx.Client(base_url=a.base_url, timeout=120) as client, ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: run_one(client, token, c), cases))
    ok = 0
    for cid, passed, problems, d, dt in results:
        ok += passed
        print(f"{cid} {'PASS' if passed else 'FAIL'} {dt:5.1f}s route={d.get('route')} "
              f"status={d.get('status')} cost=${d.get('trace', {}).get('total', {}).get('cost_usd', 0):.4f} "
              f"{'; '.join(problems)}")
        if a.verbose or not passed:
            print("   answer:", (d.get("answer") or json.dumps(d))[:400].replace("\n", " "))
            revs = [r["reason"][:90] for r in d.get("trace", {}).get("plan_revisions", [])]
            print("   revisions:", revs)
    print(f"{ok}/{len(results)} passed")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
