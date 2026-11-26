# Implementation Plan: Getnet Multi-Agent Support

**Branch**: `main` (constitution: no feature branches) | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-multi-agent-support/spec.md`

## Summary

A FastAPI service where a Router plans typed steps, a bounded supervisor executes Knowledge (RAG
over the committed Getnet snapshot, or Gemini Search grounding) and Support (two function-calling
tools over simulated merchant data), a critic replans, synthesis merges, Personality styles under a
code-checked fact lock, and escalations become operator tickets resumed from SQLite checkpoints.
Every model call goes through one metered Gemini wrapper. Verified stack and decisions:
[research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12, `uv` + `uv.lock` (frozen install)

**Primary Dependencies**: fastapi==0.162.0, uvicorn, pydantic, pydantic-settings,
google-genai==2.34.0, chromadb==1.5.9, beautifulsoup4 + lxml, httpx, pyjwt==2.15.1,
prometheus-client==0.26.0; dev: pytest, ruff

**Storage**: SQLite (stdlib, WAL) and embedded Chroma (cosine) under `data/state`; read-only crawl
cache in `data/crawl_cache`; simulated merchants in `data/merchants.json`

**Testing**: pytest; unit tests with a fake `LLMClient`; integration tests via FastAPI `TestClient`
with the LLM faked at the wrapper; container smoke with `LLM_MODE=stub`; promtool rule tests; live
evals against the container

**Target Platform**: Linux container (amd64 and arm64), Docker Compose

**Project Type**: web service + CLI + eval scripts

**Performance Goals**: p95 < 15 s per chat on the live eval (SC-007)

**Constraints**: limits from `.env` (2,000 chars, top-k 6, 3 tool iterations, 3 supervisor
iterations, 30,000 tokens per request); no network at ingestion; search grounding never combined
with function calling

**Scale/Scope**: single node, demo load; ~70 snapshot pages; 2 simulated merchants

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design: PASS.*

| Principle | How the design satisfies it |
|---|---|
| I. Bounded supervisor | `supervisor.py` loop ≤ MAX_SUPERVISOR_ITERATIONS; typed Plan/Observation/CriticVerdict; revisions in Trace; synthesis; Personality fact lock; sources by code; one prompt module per agent with date injected |
| II. Identity by code | `security/auth.py` HS256 verification; sub = user_id; tools get merchant id from Principal; owner checks; tokens only via CLI; HMAC pseudonyms in logs/prompts |
| III. Guardrails first | `security/guardrails.py` (length, Luhn card, CPF, merchant ids, injection EN/PT) before any LLM; masking before log/DB; DLP on final answer; untrusted data delimited; no-grounding → retry → escalate |
| IV. Metered LLM | `core/llm.py` single wrapper: models/thinking from env, usage and cost incl. search queries, JSON logs, timeout + one retry, whole Content preserved, budget; search and tools separated |
| V. Typed control flow | all control outputs parsed to Pydantic; typed tool results; budget/LLM failure → valid JSON + escalation |
| VI. Memory and HITL | SQLite turns, summaries, checkpoints, tickets, audit on a volume; atomic claim; resume via Personality |
| VII. Observability | JSON logs, `/metrics`, alert rules + promtool tests, provisioned Grafana under profile, live/ready |
| VIII. Evals | dataset, live runner with judge, calibration, retrieval metrics, held-out hash check, thresholds, cost |
| IX. Traced tests | `test_fr_NNN_*` per FR; LLM faked in unit and integration tests |
| X. Simplicity | plain functions, no frameworks, no repository/service layers |
| Delivery | pinned digests, frozen lock, non-root, healthcheck, log limits, compose + plain docker, CI, `.env.example` |
| Workflow | one commit per phase and per task on `main`, pushed |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-multi-agent-support/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/  http-api.md  cli-and-llm.md  eval-jsonl.md
└── tasks.md   (next phase)
```

### Source Code (repository root)

```text
src/getnet_multi_agent/
├── contracts.py              # shared Pydantic models (built first)
├── core/       settings.py  llm.py  logging.py  metrics.py
├── security/   auth.py  guardrails.py  dlp.py  pseudonym.py
├── state/      db.py  conversations.py  tickets.py  checkpoints.py  audit.py
├── rag/        crawler.py  extract.py  chunk.py  glossary.py  store.py  retriever.py  ingest.py
├── agents/     planner.py  critic.py  knowledge.py  support.py  tools.py  synthesis.py
│               escalation.py  personality.py
│   └── prompts/  router.py  critic.py  knowledge.py  support.py  synthesis.py  personality.py  summary.py
├── supervisor.py
├── api/        app.py  chat.py  conversations.py  operator.py  health.py
└── cli.py
data/  crawl_cache/ (committed)  merchants.json  state/ (git-ignored)
evals/ dataset.jsonl  retrieval.jsonl  heldout.sha256  run.py  judge.py  calibrate.py  retrieval.py
tests/ unit/  integration/  conftest.py (fake LLMClient)
ops/   prometheus/ (prometheus.yml, alerts.yml, alerts_test.yml)  grafana/ (provisioning, dashboards)
Dockerfile  compose.yaml  .dockerignore  .env.example  .github/workflows/ (ci.yml, live-eval.yml)
README.md  docs/threat-model.md
```

**Structure Decision**: single package with module groups that never share files, so groups can be
built in parallel once `contracts.py`, `core/settings.py` and the `LLMClient` interface exist.

## Request flow

1. Middleware: request_id, timer. Auth → Principal; role and `user_id == sub` checks.
2. Guardrails (code) → refusal JSON with reason, no LLM call; masked message stored.
3. Load conversation (owner check), summary and last 6 turns → `plan()`.
4. Plan refusal → refusal response; `human_requested` → escalate.
5. Supervisor loop: execute steps → observations → critic (rules: offline terminal/terminal error
   → add `knowledge:rag`; `no_grounding` → retry once with rewritten query, then escalate that part;
   failed tool/LLM → escalate) → lite completeness check → stop on complete, iteration cap or budget.
6. Synthesis if > 1 answered step; Personality with fact lock; global-site disclaimer; sources;
   DLP check; persist turns; metrics; background summary refresh.

## Build order (container early)

1. contracts + settings + LLMClient interface + stub → 2. API skeleton (`/health`, `/chat` stub) →
3. **Dockerfile + compose smoke** → 4. parallel groups: security, state, rag, agents → 5. supervisor
→ 6. HITL routes → 7. observability ops → 8. evals → 9. CI → 10. README and threat model → 11. final
proof from a clean clone in the container with live acceptance scenarios.

## Complexity Tracking

None.
