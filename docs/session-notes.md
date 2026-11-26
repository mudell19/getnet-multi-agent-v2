# Session notes — 2026-11-26

60-minute session, clock started at the first commit (03:45:59 -03:00). Spec-Driven Development:
every phase and task has its own commit on `main`, pushed immediately (`git log --reverse`).

## Phase times (commit time, minutes from start)

| Phase | Time | Min |
|---|---|---|
| Constitution v1.0.0 | 03:47 | 1 |
| Spec (FR-001..FR-072) | 03:49 | 3 |
| Plan, research, data model, contracts, quickstart | 03:52 | 6 |
| Tasks (40, wave-ordered, exclusive file ownership) | 03:55 | 9 |
| Wave 0: deps, settings, contracts, merchant data, container answering `/health/live` | 03:56–04:00 | 10–14 |
| Wave 1: G1 RAG, G2 security/core, G3 state, G4 ops (parallel subagents) + agents, supervisor | 04:00–04:10 | 14–24 |
| Live debugging of the ten scenarios in the container, API, integration tests, CI | 04:10–04:21 | 24–35 |
| Wave 2: G5 evals, G6 docs (started at minute 17, against the contracts) | 04:03–04:19 | 17–33 |
| Feature freeze, README limits | 04:27 | 41 |
| Clean-clone proof, live eval and retrieval reports | 04:27–04:37 | 41–51 |

## What was built

- Router (typed plan, language, standalone rewrite), bounded supervisor loop with critic
  (deterministic rules, then lite completeness check; add/retry/drop revisions in the trace),
  Knowledge agent (hybrid RAG over the committed snapshot; Google Search grounding for web),
  Customer Support agent (two function-calling tools over simulated data), synthesis,
  Personality with a code-checked fact lock, Human Escalation with checkpoint, ticket queue,
  atomic claim, approve/edit/reject resumption and audit.
- Identity by code (HS256 JWT issued only by the CLI, `user_id == sub`, roles), deterministic
  guardrails before any LLM (length, Luhn card, CPF, other merchant ids, EN/PT injection), masking
  before logs and DB, DLP on the final answer, HMAC pseudonyms in logs.
- One metered Gemini wrapper (cost incl. search queries, timeout, one retry, budget, whole content
  across tool turns); stub mode for CI.
- SQLite (WAL) memory with rolling summary; Prometheus metrics, 4 alerts with promtool tests,
  provisioned Grafana dashboard; CI (ruff, pytest, compose smoke in stub mode, promtool).
- Evals: 32-case dataset, live runner with typed judge and adjudication list, calibration script,
  retrieval metrics hybrid vs vector, held-out hash check.

## Cut (declared in README "Known limits")

Optional [CUT-FIRST] tasks T036–T040: rate limiting, operator webhook, MCP server, image scanning,
approval-gated advance action. No human labels collected, so no calibration figure.
`live-eval.yml` not yet run on GitHub (needs the secret and a `sessao-*` tag).

## Evidence

Verified (command → result):

- Clean clone of `5807c7c`, only `.env` copied: `docker compose -p gma-ci up --build --wait` →
  healthy in 79 s, `/health/ready` `{"chunks": 1068}`, `/health/live` `rev 5807c7c`, user `app`.
- In the clone: `uv run ruff check` → clean; `uv run pytest` → 144 passed (unit + HTTP
  integration with the LLM faked at the wrapper, restart survival, FR coverage gate);
  promtool `test rules` → SUCCESS.
- `scripts/scenarios.py` against the clean-clone container → 10/11. All ten official scenarios
  route and answer correctly; s01 fails only the strict check that "R$ 129,90" appears in the
  trace evidence excerpt (the answer states R$ 79.90 vs R$ 129.90).
- `evals/run.py` (policy `1+3`: every case once, failures 3 more times, majority) →
  32 cases / 41 runs: routing accuracy 0.931, citation rate 1.000, source match 0.929, correct
  refusal rate 1.000, pass rate 0.906, judge correctness 3.92, groundedness 3.52, relevance 4.96,
  helpfulness 4.20; p50 5.7 s, p95 18.4 s; API cost USD 0.2056 (0.0050 per request), judge USD
  0.1788. **Verdict FAIL** on correctness and groundedness (threshold 4.0). The runner's exit code
  was not captured (the shell's `PIPESTATUS` is empty in zsh); the FAIL verdict is in the report.
- `evals/retrieval.py` (18 queries, EN+PT) → hybrid Hit@6 1.000, MRR 0.769, nDCG 0.829, context
  recall 0.889 vs vector-only Hit@6 0.944, MRR 0.653, nDCG 0.727, context recall 0.778.
- GitHub Actions `ci` on `5f6b395`: test, promtool and container smoke all green.

Not verified: `live-eval.yml` on GitHub; Grafana panels against live traffic (provisioning and the
datasource health were checked); held-out set (never opened; only its hash check is implemented
and unit-tested).

## Defects found by running it for real, and fixed

1. `gemini-embedding-2` embeds a plain list of strings as ONE content (100 texts → 1 vector);
   now one `Content` per text plus a count check (regression test).
2. The first stub run wrote hash vectors into the live collection; stub and live now use separate
   collections.
3. Ingestion was charged against the per-request token budget; each batch now has its own context.
4. Router committed to steps before decomposing parts (schema order); fields reordered and
   paraphrased examples added (no eval messages copied into prompts).
5. `/health/ready` reported ready mid-ingestion (200 of 1068 chunks); now waits for ingestion.
6. `astral-sh/setup-uv@v10` does not exist (the plan input said verified); CI installs uv 0.13.6.
7. Critic-added troubleshooting for issuer declines has no grounding on the site; it is now
   dropped (`drop` revision) instead of escalating an answered question.

## Open items for adjudication

`s01` (number formatting in English), `a03` (refused by the code guardrail because the message asks
to follow embedded instructions), `m02` (adds a valid troubleshooting step). Groundedness: the
judge sees two 300-character windows per chunk; passing full cited chunks to the judge is the
next step.
