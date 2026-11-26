---
description: "Wave-ordered tasks with exclusive file ownership"
---

# Tasks: Getnet Multi-Agent Support

**Input**: `specs/001-multi-agent-support/` (plan, spec, research, data-model, contracts, quickstart)

**Tests**: required by the constitution: every FR has a pytest test named `test_fr_NNN_*`; each task
writes the tests for the FRs it lists, in the test files it owns. Unit tests use the fake
`LLMClient` from `tests/conftest.py`; nothing calls the network.

**Organization**: waves replace story phases (user input). Within a wave, `[P]` tasks run in
parallel and **never own the same file**. `[Gn]` = parallel group, `[MAIN]` = main session.
`[USn]` maps to spec user stories. `S/` = `src/getnet_multi_agent/`.

**Rules for every task**: touch only owned files; run the verify command; one commit per task on
`main`, pushed immediately (`git push origin main`), message `feat|test|chore|docs(<area>): … (T0NN,
FR-…)`. Interfaces are those in `contracts/` and `data-model.md`; do not change `S/contracts.py` or
`S/core/llm.py` after Wave 0 (ask the main session instead).

---

## Wave 0 — Foundation (sequential, main session)

- [ ] T001 Dependencies and lockfile. Owns `pyproject.toml`, `uv.lock`. Add runtime deps
  fastapi==0.162.0, uvicorn, pydantic, pydantic-settings, google-genai==2.34.0, chromadb==1.5.9,
  beautifulsoup4, lxml, httpx, pyjwt==2.15.1, prometheus-client==0.26.0; dev group pytest, ruff;
  ruff config (line 100); pytest `testpaths=["tests"]`; keep the `uv_build` backend and package name.
  Verify: `uv lock && uv sync --frozen && uv run python -c "import fastapi, google.genai, chromadb, jwt, prometheus_client, bs4, lxml"`.
- [ ] T002 Settings and `.env.example` (FR-054). Owns `S/core/__init__.py`, `S/core/settings.py`,
  `.env.example`, `tests/unit/test_settings.py`. `Settings(BaseSettings)` with exactly the `.env`
  names in research.md plus `LLM_MODE` (`live`|`stub`, default live), `DATA_DIR="data"`,
  `APP_REV="dev"`, `MEMORY_LAST_TURNS=6`; `env_file=".env"`, process env wins; secrets as
  `SecretStr`; cached `get_settings()`. `.env.example`: same names and values, empty
  GEMINI_API_KEY/JWT_SECRET/PSEUDONYM_KEY. Never open `.env`. Test: `.env.example` keys == Settings
  `.env` fields. Verify: `uv run pytest tests/unit/test_settings.py -q`.
- [ ] T003 Shared contracts and LLM interface (FR-002, FR-003, FR-047). Owns `S/contracts.py`,
  `S/core/llm.py`, every package `__init__.py` (`S/security`, `S/state`, `S/rag`, `S/agents`,
  `S/agents/prompts`, `S/api`), `tests/__init__.py`, `tests/conftest.py`,
  `tests/unit/test_contracts.py`. Models and enums exactly as data-model.md (message
  `1..MAX_MESSAGE_CHARS` validated in the chat route, not the model). `core/llm.py`: `LLMClient`
  Protocol (`generate`, `embed` per contracts/cli-and-llm.md), `LLMResult`, `GroundingInfo`,
  exceptions `LLMUnavailable`, `BudgetExceeded`, `get_llm(settings)` that lazily imports
  `core.gemini_client.GeminiClient` or `core.stub_client.StubClient` by `LLM_MODE`. `conftest.py`:
  `FakeLLM` with scripted responses per task and 768-d hash embeddings, `settings` fixture with temp
  `DATA_DIR` and test secrets. Verify: `uv run pytest tests/unit/test_contracts.py -q`.
- [ ] T004 Simulated merchant data (FR-024). Owns `data/merchants.json`, `S/merchants.py`,
  `tests/unit/test_merchants.py`. Day offsets relative to today in fixed UTC-03:00, per
  data-model.md (`cliente1988`: T-1001 offline with connectivity error, T-1002 online with decline
  `51` and reason, sales at −1 (≥2) and −2..−5 with settlement dates/amounts; `cliente2000`: own
  terminal and sales). `load_merchant(merchant_id, today=None) -> dict | None` resolves offsets to ISO
  dates. Verify: `uv run pytest tests/unit/test_merchants.py -q`.
- [ ] T005 Container from the start (FR-069). Owns `Dockerfile`, `.dockerignore`, `compose.yaml`,
  `S/api/app.py` (minimal), `S/api/health.py` (minimal). Dockerfile: pinned
  `python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b`, uv copied from its image,
  `uv sync --frozen --no-dev`, `ARG REV=dev` → `ENV APP_REV`, label
  `org.opencontainers.image.revision`, uid 10001, `/app/data/state` owned by it, `data/crawl_cache`
  and `data/merchants.json` copied, `HEALTHCHECK` via Python urllib on `/health/ready`, CMD uvicorn
  `getnet_multi_agent.api.app:app` on 8000. `.dockerignore`: `.env`, `.venv`, `.git`, `data/state`,
  caches. compose: `name: getnet-multi-agent`, service `api` (`image: getnet-multi-agent:${REV:-dev}`,
  build arg REV, `env_file: .env`, `environment: LLM_MODE: ${LLM_MODE:-live}`, port
  `127.0.0.1:8000:8000`, named volume `state:/app/data/state`, healthcheck start_period 300s,
  `logging` json-file 10m×3, `restart: unless-stopped`). Minimal app: `/health/live` and
  `/health/ready` (200 for now). Verify: `LLM_MODE=stub docker compose -p getnet-multi-agent-dev up --build --wait && curl -fs 127.0.0.1:8000/health/live && docker compose -p getnet-multi-agent-dev down`.

**Checkpoint**: container builds and answers; contracts frozen.

---

## Wave 1 — Parallel groups + main session

### G1 RAG [P]

- [ ] T006 [P] [G1] [US1] Extraction and chunking (FR-015, FR-016). Owns `S/rag/extract.py`,
  `S/rag/chunk.py`, `tests/unit/test_rag_extract_chunk.py`. Drop script/style/nav/header/footer;
  drop text nodes repeated in ≥ 30% of pages of the same host; keep tables (rows as `a | b`),
  product cards, FAQ question+answer. Chunk by heading and by FAQ question; metadata per
  data-model.md (`kind`, `is_rule` from requirement patterns). Test on 3 real cached pages
  (`/crediario/` yields a chunk with "48x"). Verify: `uv run pytest tests/unit/test_rag_extract_chunk.py -q`.
- [ ] T007 [P] [G1] [US1] Cache, store and offline ingestion (FR-011, FR-012, FR-013, FR-023).
  Owns `S/rag/cache.py`, `S/rag/store.py`, `S/rag/ingest.py`, `tests/unit/test_rag_ingest.py`.
  `normalize_url`, `cache_key`, `read_cache()` keeping status 200 + `text/html`, dedupe by final URL
  and visible-text hash; Chroma `PersistentClient` at `DATA_DIR/state/chroma`, collection
  `getnet_kb` with `configuration={"hnsw": {"space": "cosine"}}`, telemetry off;
  `ingest(settings, llm, rebuild=False) -> int` embeds with `RETRIEVAL_DOCUMENT`, 768-d, batches of
  100. Tests: socket blocked during ingest; the six required URLs present; key = sha256(normalized).
  Verify: `uv run pytest tests/unit/test_rag_ingest.py -q`.
- [ ] T008 [P] [G1] [US1] Glossary and hybrid retriever (FR-017, FR-018, FR-051 data). Owns
  `S/rag/glossary.py`, `S/rag/retriever.py`, `tests/unit/test_rag_retriever.py`. Alias groups from
  spec FR-017; `retrieve(query, mode="hybrid"|"vector", k=RAG_TOP_K) -> list[RankedChunk]` with the
  score in research.md (similarity = 1 − distance; +0.10 per glossary group, max 0.20; +0.10
  `is_rule`; keep ≥ `RAG_MIN_SIMILARITY`). Tests: "Payment Link" matches "Link de Pagamento"; rule
  chunk outranks mention chunk at equal similarity. Verify: `uv run pytest tests/unit/test_rag_retriever.py -q`.
- [ ] T009 [P] [G1] Refresh crawler (FR-014). Owns `S/rag/crawler.py`, `tests/unit/test_rag_crawler.py`.
  `refresh(settings, max_pages=None) -> int`: start pages from contracts/cli-and-llm.md, depth 1,
  same host, `/en` only on www.getnet.net, sequential, 2 s sleep (injectable), stop host at first
  403/429, cap `RAG_MAX_PAGES`, writes the cache format. Tests with `httpx.MockTransport`. Verify:
  `uv run pytest tests/unit/test_rag_crawler.py -q`.

### G2 Security and core [P]

- [ ] T010 [P] [G2] Request context, JSON logging, metrics registry (FR-057, FR-058). Owns
  `S/core/request_context.py` (contextvars: request_id, token counter, usage list),
  `S/core/logging.py`, `S/core/metrics.py`, `tests/unit/test_core_obs.py`. Metrics:
  `getnet_requests_total{route,status}`, `getnet_request_latency_seconds`,
  `getnet_llm_tokens_total{model,kind}`, `getnet_llm_cost_usd_total{model}`,
  `getnet_replans_total`, `getnet_refusals_total{reason}`, `getnet_escalations_total{reason}`,
  `getnet_tickets_open`, `getnet_ticket_oldest_age_seconds` (callback setter). Verify:
  `uv run pytest tests/unit/test_core_obs.py -q`.
- [ ] T011 [P] [G2] Gemini and stub clients (FR-022, FR-053, FR-054, FR-055). Owns
  `S/core/gemini_client.py`, `S/core/stub_client.py`, `tests/unit/test_llm_clients.py`. Task →
  model/thinking/prices per research.md; structured output via `response_schema`; usage None → 0;
  cost formula; search queries from `grounding_metadata.web_search_queries`; grounding chunks →
  `{title, uri}`; `search` + `tools` → `ValueError`; timeout; one retry on 429/5xx then
  `LLMUnavailable`; budget check before each call → `BudgetExceeded`; raw `Content` kept in
  `LLMResult.content`; one JSON log line per call; metrics updated. Stub: deterministic per task,
  hash embeddings. Tests mock `genai.Client`. Verify: `uv run pytest tests/unit/test_llm_clients.py -q`.
- [ ] T012 [P] [G2] [US5] JWT auth, pseudonym, CLI (FR-033, FR-034, FR-035, FR-036). Owns
  `S/security/auth.py`, `S/security/pseudonym.py`, `S/cli.py`, `tests/unit/test_auth_cli.py`.
  `issue_token(sub, role, ttl)`, `verify_token` (HS256, aud, iss, exp, sub, role required) →
  `Principal`; FastAPI deps `require_merchant`, `require_operator` (401/403 JSON);
  `pseudonym(sub)` = HMAC-SHA256 with `PSEUDONYM_KEY`, 16 hex chars. CLI subcommands `token`,
  `refresh` (calls `rag.crawler.refresh`), `ingest` (calls `rag.ingest.ingest`), imported lazily.
  Verify: `uv run pytest tests/unit/test_auth_cli.py -q`.
- [ ] T013 [P] [G2] [US4] Guardrails, masking, DLP (FR-029, FR-031, FR-032). Owns
  `S/security/guardrails.py`, `S/security/dlp.py`, `tests/unit/test_guardrails.py`.
  `check(message, principal) -> Refusal | None` in order: length (`too_long`), Luhn card 13–19
  digits with separators or valid CPF (`sensitive_data`, warning text), `cliente\d+` ≠ principal
  (`other_merchant`), injection patterns EN/PT (`prompt_injection`); `mask(text)`; refusal text
  in en/pt by Portuguese markers; `dlp_check(answer, principal)` masks and blocks other merchant ids.
  Tests: invalid Luhn/CPF not refused. Verify: `uv run pytest tests/unit/test_guardrails.py -q`.

### G3 State [P]

- [ ] T014 [P] [G3] [US5] SQLite, conversations, memory (FR-037, FR-038, FR-040). Owns
  `S/state/db.py`, `S/state/conversations.py`, `tests/unit/test_state_conversations.py`. Schema of
  all six tables (data-model.md), WAL, `connect(settings)`; create/get with owner check (None →
  404 upstream), `append_turn` (masked text), `last_turns(n)`, `get_summary`/`save_summary`. Test:
  data survives reopening the DB file. Verify: `uv run pytest tests/unit/test_state_conversations.py -q`.
- [ ] T015 [P] [G3] [US6] Tickets, checkpoints, audit (FR-041, FR-043, FR-045). Owns
  `S/state/tickets.py`, `S/state/checkpoints.py`, `S/state/audit.py`, `tests/unit/test_state_tickets.py`.
  Statuses `open, claimed, resolved, rejected`; `claim` = `UPDATE … WHERE id=? AND status='open'`
  (rowcount 0 → `AlreadyClaimed`); `resolve` only by claimant; `open_stats()` (count, oldest age).
  Test: two threads claim, exactly one wins. Verify: `uv run pytest tests/unit/test_state_tickets.py -q`.

### G4 Ops [P]

- [ ] T016 [P] [G4] [US7] Prometheus config, alerts, promtool tests (FR-059). Owns
  `ops/prometheus/prometheus.yml`, `ops/prometheus/alerts.yml`, `ops/prometheus/alerts_test.yml`.
  Scrape `api:8000/metrics`; alerts HighErrorRate (status="error" ratio > 5% for 5m),
  HighLatencyP95 (> 15 s for 10m), HighCostPerHour (> 1 USD/h), StaleTicket (oldest age > 900 s);
  one firing and one silent test per alert. Verify: `docker run --rm --entrypoint promtool -v "$PWD/ops/prometheus:/etc/prometheus:ro" prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06 test rules /etc/prometheus/alerts_test.yml`.
- [ ] T017 [P] [G4] [US7] Grafana and observability profile (FR-060). Owns
  `ops/grafana/provisioning/datasources/prometheus.yml`,
  `ops/grafana/provisioning/dashboards/dashboards.yml`, `ops/grafana/dashboards/getnet.json`,
  `compose.yaml` (adds `prometheus` and `grafana` services, profile `observability`, pinned digests,
  ports on 127.0.0.1, log limits). Panels: requests by route/status, p50/p95 latency, tokens and
  cost by model, replans, refusals, escalations, open tickets, oldest ticket age. Verify:
  `LLM_MODE=stub docker compose -p getnet-multi-agent-dev --profile observability up -d --build --wait && curl -fs -u admin:admin '127.0.0.1:3000/api/search?query=Getnet' | grep -q Getnet`.
- [ ] T018 [P] [G4] CI workflows (FR-070). Owns `.github/workflows/ci.yml`,
  `.github/workflows/live-eval.yml` per research.md (checkout@v7, setup-uv@v10). **Keep uncommitted**
  until T026 passes; committed in T027. Verify: after the T027 push,
  `gh run list --workflow ci.yml -L 1 --json conclusion -q '.[0].conclusion'` prints `success`.

### MAIN Agents, supervisor, API

- [ ] T019 [MAIN] [US2] Support tools and agent (FR-025, FR-026, FR-027, FR-028, FR-056). Owns
  `S/agents/tools.py`, `S/agents/support.py`, `S/agents/prompts/support.py`,
  `tests/unit/test_support.py`. Tools `get_receivables(from_date, to_date)` (validated ISO, from ≤ to,
  ≤ 90 days) and `get_terminal_status()`; merchant id bound from Principal, absent from declarations;
  typed results; not-found result; loop ≤ `MAX_TOOL_ITERATIONS` returning model Content whole; tool
  output delimited as untrusted. Verify: `uv run pytest tests/unit/test_support.py -q`.
- [ ] T020 [MAIN] [US1] [US3] Knowledge agent (FR-019, FR-020, FR-021, FR-022, FR-056). Owns
  `S/agents/knowledge.py`, `S/agents/prompts/knowledge.py`, `tests/unit/test_knowledge.py`.
  `knowledge_rag`: retrieve, delimited context, structured `AgentResult`, `no_grounding` when nothing
  passes threshold or model says ungrounded; evidence with URL/score/excerpt; global-site flag.
  `knowledge_web`: search-only call, sources title+uri. Verify: `uv run pytest tests/unit/test_knowledge.py -q`.
- [ ] T021 [MAIN] Planner and critic (FR-002, FR-004, FR-005, FR-006, FR-030, FR-039). Owns
  `S/agents/planner.py`, `S/agents/critic.py`, `S/agents/prompts/router.py`,
  `S/agents/prompts/critic.py`, `tests/unit/test_planner_critic.py`. Router gets summary + last turns
  + date, returns Plan; parse failure → escalate. Critic rules: offline terminal/terminal error →
  add `knowledge:rag`; `no_grounding` → retry once with rewrite, then escalate that part; failure →
  escalate; then lite completeness check. Verify: `uv run pytest tests/unit/test_planner_critic.py -q`.
- [ ] T022 [MAIN] Synthesis, Personality, escalation (FR-008, FR-009, FR-041). Owns
  `S/agents/synthesis.py`, `S/agents/personality.py`, `S/agents/escalation.py`,
  `S/agents/prompts/synthesis.py`, `S/agents/prompts/personality.py`, `S/agents/prompts/summary.py`,
  `tests/unit/test_synthesis_personality.py`. Fact lock: number and URL sets equal both ways, else
  draft; escalation saves checkpoint + ticket + audit `escalated`. Verify:
  `uv run pytest tests/unit/test_synthesis_personality.py -q`.
- [ ] T023 [MAIN] Supervisor (FR-001, FR-003, FR-007, FR-010, FR-048, FR-049, FR-055). Owns
  `S/supervisor.py`, `tests/unit/test_supervisor.py`. Loop per plan.md request flow; stop on
  complete, `MAX_SUPERVISOR_ITERATIONS`, budget; partial escalation keeps answered parts; route
  string; trace; sources and global disclaimer by code. Tests: connectivity scenario shows an `add`
  revision; compound runs `support>knowledge:rag`. Verify: `uv run pytest tests/unit/test_supervisor.py -q`.
- [ ] T024 [MAIN] [US1] [US5] Chat, conversations, health API (FR-023, FR-037, FR-046, FR-047,
  FR-050, FR-052). Owns `S/api/app.py`, `S/api/chat.py`, `S/api/conversations.py`,
  `S/api/health.py`, `tests/integration/test_api_chat.py`. Middleware request_id/latency/metrics;
  JSON error handlers; guardrails before planning; startup ingestion thread when empty; ready when
  chunks > 0; `/metrics`; background summary refresh. Verify: `uv run pytest tests/integration/test_api_chat.py -q`.
- [ ] T025 [MAIN] [US6] Operator API (FR-042, FR-043, FR-044, FR-045, FR-051). Owns
  `S/api/operator.py`, `tests/integration/test_api_operator.py`. List by status, claim (409),
  resolve approve/edit/reject resuming from checkpoint through Personality, retrieval endpoint.
  Verify: `uv run pytest tests/integration/test_api_operator.py -q`.

**Checkpoint**: `uv run ruff check && uv run pytest -q` green.

---

## Wave 2 — Integration + G5 + G6

- [ ] T026 [MAIN] Integration flows and FR coverage (FR-038, FR-033, FR-034, FR-029). Owns
  `tests/integration/test_flows.py`, `tests/integration/test_restart.py`,
  `tests/test_fr_coverage.py`. Flows with FakeLLM for US2, US4, US5, US6; restart = new app
  instance on the same DB; coverage test parses `FR-\d{3}` from spec.md and asserts a
  `test_fr_NNN_` test exists for each. Verify: `uv run ruff check && uv run pytest -q`.
- [ ] T027 [MAIN] Ten scenarios in the container (SC-001). Owns `scripts/scenarios.py`; commits T018
  files. Runs the ten challenge payloads plus the compound one against the live container, printing
  route/status/sources/fact checks; fix defects found in the owning task's files. Verify:
  `docker compose -p getnet-multi-agent-dev up --build --wait && uv run python scripts/scenarios.py --base-url http://127.0.0.1:8000`
  (exit 0), then the first GitHub Actions `ci.yml` run green.
- [ ] T028 [P] [G5] [US7] Datasets (FR-061, FR-062). Owns `evals/dataset.jsonl`,
  `evals/retrieval.jsonl`. Format per contracts/eval-jsonl.md; ten scenarios (expected facts from
  spec US1), compound, adversarial (injection in message, in retrieved content, in tool result; card
  number; other merchant; out of scope), authorization (401/403/404), memory (two follow-ups),
  hitl (approve, edit). Retrieval: ≥ 16 queries, half en half pt. Verify:
  `uv run python -c "import json;[json.loads(l) for f in ('evals/dataset.jsonl','evals/retrieval.jsonl') for l in open(f)]"`.
- [ ] T029 [P] [G5] [US7] Runner and judge (FR-063, FR-064, FR-065, FR-068). Owns `evals/run.py`,
  `evals/judge.py`, `tests/unit/test_eval_runner.py`. Concurrency (default 4), token per user_id via
  `security.auth.issue_token`, code checks, judge via `LLMClient` task `judge` with typed rubric,
  adjudication list, `evals/report.md` metrics and repetition policy, thresholds from SC-002..SC-004,
  `--dataset`, `--heldout` sha256 check against `evals/heldout.sha256` (never search for the file).
  Verify: `uv run pytest tests/unit/test_eval_runner.py -q`.
- [ ] T030 [P] [G5] [US7] Calibration (FR-066). Owns `evals/calibrate.py`,
  `tests/unit/test_eval_calibrate.py`. Export CSV sheet from `evals/results.jsonl`; read labels;
  report agreement and Cohen's kappa. Verify: `uv run pytest tests/unit/test_eval_calibrate.py -q`.
- [ ] T031 [P] [G5] [US7] Retrieval metrics (FR-067). Owns `evals/retrieval.py`,
  `tests/unit/test_eval_retrieval.py`. Calls `/operator/retrieval` in both modes; Hit@k, Recall@k,
  MRR, nDCG@k, context precision/recall (fact substring), by language; writes
  `evals/retrieval_report.md`. Verify: `uv run pytest tests/unit/test_eval_retrieval.py -q`.
- [ ] T032 [P] [G6] Documentation (FR-071, FR-072). Owns `README.md`, `docs/threat-model.md`. All
  README sections listed in FR-071 with curl examples from quickstart.md; threat model: assets,
  actors, threats (injection, data leak, cross-merchant access, token forgery, cost abuse),
  mitigations mapped to FRs. Verify: `grep -c '^## ' README.md` ≥ 12 and every link target exists.

---

## Final wave (sequential, main session)

- [ ] T033 Clean-clone proof and live reports (SC-001..SC-010). Owns `evals/report.md`,
  `evals/retrieval_report.md`, `evals/results.jsonl`. `git clone` to a temp dir, copy `.env`,
  `docker compose -p getnet-multi-agent-dev up --build --wait`, run `scripts/scenarios.py`,
  `evals/run.py`, `evals/retrieval.py`. Verify: exit codes recorded; reports committed.
- [ ] T034 Final docs update. Owns `README.md`, `docs/threat-model.md`. Reflect what exists and the
  measured results; remove anything not built. Verify: README commands rerun from the clean clone.
- [ ] T035 Session notes and push. Owns `docs/session-notes.md`. Timeline from git log, verified vs
  not verified, cuts. Last commit of the session, message exactly `docs: final session notes`, then
  `git push origin main`. Verify: `git log -1 --format=%s` prints `docs: final session notes` and
  `git status` is clean and in sync with origin.

---

## Optional [CUT-FIRST] (only if time remains; run before T033 so T035 stays the last commit)

- [ ] T036 [CUT-FIRST] Rate limiting per principal on `/chat`. Owns `S/security/ratelimit.py`,
  `tests/unit/test_ratelimit.py` (wired by one line in `S/api/chat.py`).
- [ ] T037 [CUT-FIRST] Operator webhook on ticket creation. Owns `S/state/notify.py`,
  `tests/unit/test_notify.py`.
- [ ] T038 [CUT-FIRST] MCP server exposing the two support tools for operators. Owns `S/mcp_server.py`.
- [ ] T039 [CUT-FIRST] Image scanning job in CI. Owns `.github/workflows/scan.yml`.
- [ ] T040 [CUT-FIRST] Approval-gated receivables advance action (operator approval required). Owns
  `S/agents/advance.py`, `tests/unit/test_advance.py`.

---

## Dependencies and parallelism

- Wave 0 is strictly sequential (T001 → T005). Wave 1 starts only after T005.
- Wave 1: G1, G2, G3, G4 and MAIN run together; MAIN codes against `contracts.py` and `FakeLLM`, so
  it does not wait for G1–G3. T024/T025 tests need G2 (auth, guardrails) and G3 (state) merged;
  they finish last in the wave.
- Wave 2: T026 → T027 sequential in MAIN; G5 (T028 → T029, T030, T031) and G6 (T032) in parallel.
- Final wave: T033 → T034 → T035.
- Story coverage: US1 T006–T008, T020, T024; US2 T004, T019, T023; US3 T011, T020; US4 T013,
  T021; US5 T012, T014, T024; US6 T015, T022, T025; US7 T016, T017, T028–T031.

## Implementation strategy

MVP = Wave 0 + US1/US2 path (T006–T008, T010–T014, T019–T024) proving the container answers grounded
and support questions. Waves add escalation, observability, evals and docs. Cut [CUT-FIRST] tasks
first, then T030 and T017, if time runs short; never cut T033–T035.
