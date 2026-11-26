# Research: Getnet Multi-Agent Support

All items below are **verified facts** (real calls on 2026-11-25, supplied with the plan input) or
**decisions** derived from them. No open questions remain. Delivery class: local delivery (no
production side effects; merchant data is simulated).

## Stack (pinned)

| Item | Value |
|---|---|
| Runtime | Python 3.12, `uv` with committed `uv.lock`, installed with `uv sync --frozen` |
| Pins | fastapi==0.162.0, google-genai==2.34.0 (stay on 2.x), chromadb==1.5.9, pyjwt==2.15.1, prometheus-client==0.26.0 |
| Unpinned (locked) | uvicorn, pydantic, pydantic-settings, beautifulsoup4, lxml, httpx, pytest, ruff |
| Wheels | the set resolves for linux amd64 and arm64 |
| State | stdlib `sqlite3` in WAL mode; Chroma `PersistentClient`, both under `data/state` |
| App image | `python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b` |
| Prometheus | `prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06` (also `--entrypoint promtool`) |
| Grafana | `grafana/grafana:13.3.1@sha256:0615ec4fbd4072004b7d86b46ded63013a74b7d6eb1119273dd89e8fa25c13cf` |
| Platforms | all three images are multi-arch indexes (amd64, arm64); no `platform:` pin |

## Gemini contracts (verified)

- Structured output: `types.GenerateContentConfig(response_mime_type="application/json",
  response_schema=<Pydantic model>, thinking_config=types.ThinkingConfig(thinking_level=...))`
  returns `response.parsed`.
- `gemini-3.8-flash` rejects `thinking_level="minimal"`; it uses `low` (agents) and `high` (judge).
  `gemini-3.5-flash-lite` accepts `minimal`.
- Judge is `gemini-3.8-flash` with thinking high: `gemini-2.5-pro` returns 404 for new users and
  preview models are not allowed. Same family as the agents: stated as a known limit.
- Usage: `usage_metadata.prompt_token_count`, `candidates_token_count`, `thoughts_token_count`;
  any may be `None` → 0. Cost = prompt × input price + (candidates + thoughts) × output price.
- Embeddings: `gemini-embedding-2`, `output_dimensionality=768`, `task_type` `RETRIEVAL_DOCUMENT`
  (ingestion) or `RETRIEVAL_QUERY` (queries).
- Search grounding: `types.Tool(google_search=types.GoogleSearch())`; queries counted from
  `candidates[0].grounding_metadata.web_search_queries`, priced at `PRICE_SEARCH_PER_1K`.
  Grounding chunk URIs are `vertexaisearch` redirect links → sources carry chunk title + URI.
- Grounding + function calling in one request → 400. Decision: web search is its own call, never
  combined with tools.
- Function-calling loop: the model `Content` must be appended back whole (thought signatures);
  otherwise the next turn returns 400.

## Pricing map (decision)

Price table from Settings: `GEMINI_ROUTER_MODEL` → `PRICE_LITE_*`; `GEMINI_MODEL` and
`GEMINI_JUDGE_MODEL` → `PRICE_FLASH_*`; embeddings → `PRICE_EMBEDDING_PER_M` on input tokens;
search → `PRICE_SEARCH_PER_1K` per query.

## Other verified contracts

- Chroma defaults to l2 → collection created with `configuration={"hnsw": {"space": "cosine"}}`;
  similarity = 1 − distance. Telemetry disabled in client settings.
- PyJWT: `jwt.encode(..., algorithm="HS256")`, `jwt.decode(token, key, algorithms=["HS256"],
  audience=JWT_AUDIENCE, issuer=JWT_ISSUER)`; `exp`, `sub`, `role` required.
- Metrics endpoint: `prometheus_client.generate_latest()` with `CONTENT_TYPE_LATEST`.

## Configuration (decision)

- `.env` exists and is never opened by tooling; `Settings` (pydantic-settings) reads exactly:
  GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODEL_THINKING, GEMINI_ROUTER_MODEL,
  GEMINI_ROUTER_THINKING, GEMINI_EMBEDDING_MODEL, GEMINI_JUDGE_MODEL, GEMINI_JUDGE_THINKING,
  PRICE_FLASH_INPUT_PER_M, PRICE_FLASH_OUTPUT_PER_M, PRICE_LITE_INPUT_PER_M,
  PRICE_LITE_OUTPUT_PER_M, PRICE_EMBEDDING_PER_M, PRICE_SEARCH_PER_1K, JWT_SECRET, JWT_ISSUER,
  JWT_AUDIENCE, PSEUDONYM_KEY, MAX_MESSAGE_CHARS, RAG_TOP_K, RAG_MAX_PAGES, RAG_MIN_SIMILARITY,
  MAX_TOOL_ITERATIONS, MAX_SUPERVISOR_ITERATIONS, REQUEST_TOKEN_BUDGET.
- `.env.example` lists the same names and values with empty secrets.
- Extra process-env settings with defaults (not in `.env`): `LLM_MODE=live|stub` (default live),
  `DATA_DIR=data`, `APP_REV=dev` (baked at build time), `MEMORY_LAST_TURNS=6`.
- Process environment overrides `.env` (pydantic-settings precedence); the container receives values
  through `env_file`, never a copied `.env`.
- These values supersede the spec's illustrative defaults (top-k 6, budget 30,000 tokens, similarity
  threshold 0.62); the spec Assumptions were updated accordingly.

## LLM_MODE=stub (decision)

Deterministic outputs per task and 768-d hash embeddings (SHA-256 expanded, L2-normalized). Used by
the CI container smoke test. Unit and integration tests inject a scripted fake at the wrapper
interface (`LLMClient`) instead.

## Design decisions

- **Contracts first**: `contracts.py` holds Plan, Step, Observation, CriticVerdict, AgentResult,
  ChatRequest, ChatResponse, Trace, Ticket, Principal; `core/llm.py` defines `LLMClient`. Module
  groups build in parallel against them without touching each other's files.
- **Timezone**: business dates use fixed `UTC-03:00` (Brazil has no DST), avoiding a `tzdata`
  dependency on the slim image.
- **Ingestion at startup** runs in a background thread when the collection is empty; `/health/live`
  answers immediately, `/health/ready` turns true when the collection has chunks and SQLite opens.
  Failure is logged and leaves the service live but not ready.
- **Boilerplate removal**: text nodes repeated in ≥ 30% of the pages of the same host are dropped
  (the two sites have different templates).
- **Hybrid score**: candidates = vector top 3×k ∪ lexical glossary matches; score = similarity
  + 0.10 per matched glossary group (max 0.20) + 0.10 for rule chunks (requirement patterns such as
  "é necessário", "precisa", "até N", "required", "must"); keep score ≥ `RAG_MIN_SIMILARITY`, top k.
- **Global-site disclaimer** is appended by code when any cited source is `www.getnet.net`.
- **Personality check**: numbers (normalized) and URLs extracted from draft and styled text must be
  equal sets; otherwise the draft is returned.
- **Deterministic refusal language**: Portuguese markers (accents, common stopwords) → pt, else en.
- **Escalation resolution**: `approve` sends the stored proposed answer; `edit` sends the operator
  text in place of the escalated part, merged with answered parts; `reject` sends a polite
  rejection carrying the operator text. All pass through Personality.
- **Rolling summary** is refreshed by the lite model as a background task after the response; its
  cost is logged with the same `request_id`.
- **Chat role**: `/chat` and `/conversations` require role merchant; `/operator/*` requires operator.
- **Container**: non-root uid 10001; `/app/data/state` created and owned by it in the image so the
  named volume inherits ownership; `APP_REV` from build arg; compose `name: getnet-multi-agent`;
  healthcheck by Python `urllib` on `/health/ready` (no curl in slim) with a long start period for
  first ingestion; logs `json-file` max-size 10m × 3; ports bound to 127.0.0.1.
- **Container early**: the Docker task runs right after the first endpoint responds in stub mode,
  not at the end.

## CI (decision)

- `actions/checkout@v7`, `astral-sh/setup-uv@v10` (both current, node24).
- `ci.yml` on push: `uv sync --frozen`, `ruff check`, `pytest`, `.env` from `.env.example` with
  generated `JWT_SECRET` and `PSEUDONYM_KEY`, compose smoke with `LLM_MODE=stub` (token via CLI in
  the container, `POST /chat` returns valid JSON), `promtool test rules` via the Prometheus image.
- `live-eval.yml` on tags `sessao-*`: `.env` from `.env.example`, `GEMINI_API_KEY` from repository
  secret, generated JWT and pseudonym secrets, compose up, `evals/run.py` and `evals/retrieval.py`,
  reports uploaded as artifacts.
