# Quickstart validation

Prerequisites: Docker with compose, `uv`, a `.env` (copy `.env.example`, fill `GEMINI_API_KEY`,
`JWT_SECRET`, `PSEUDONYM_KEY`).

## 1. Tests (no network, LLM faked)

```bash
uv sync --frozen && uv run ruff check && uv run pytest
```
Expect: all pass; every FR-NNN has a test named `test_fr_NNN_*`.

## 2. Container

```bash
docker compose up --build --wait            # live mode; first start ingests the snapshot
TOKEN=$(docker compose exec -T api python -m getnet_multi_agent.cli token --sub cliente1988 --role merchant)
curl -s localhost:8000/chat -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"When will the money from yesterday'\''s sales be deposited?","user_id":"cliente1988"}'
```
Expect: `status=answered`, `route=support`, yesterday's sales with settlement dates.

Plain Docker: `docker build -t getnet-multi-agent:dev . && docker run --env-file .env -p 127.0.0.1:8000:8000 -v getnet-state:/app/data/state getnet-multi-agent:dev`.

## 3. Acceptance scenarios

Send each of the ten challenge messages (spec US1–US3) as above. Check route, status, source and
expected fact; the connectivity message shows a plan revision `add knowledge:rag` in `trace`.

## 4. Identity, memory, escalation

- No token → 401; `user_id` ≠ token sub → 403; other merchant's `conversation_id` → 404.
- Follow-up "and how much is it?" with the returned `conversation_id` → answered in context.
- `docker compose restart api`, then `GET /conversations/{id}` → same turns.
- "I want to talk to a person" → `awaiting_human` + `ticket_id`; operator token: list, claim (second
  claim 409), resolve `edit`; `GET /conversations/{id}` shows the operator answer.

## 5. Evals and observability

```bash
uv run python evals/run.py --base-url http://localhost:8000      # writes evals/report.md, exit≠0 below thresholds
uv run python evals/retrieval.py --base-url http://localhost:8000 # writes evals/retrieval_report.md
docker compose --profile observability up -d                     # Grafana 127.0.0.1:3000, Prometheus 127.0.0.1:9090
docker run --rm --entrypoint promtool -v "$PWD/ops/prometheus:/etc/prometheus" \
  prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06 test rules /etc/prometheus/alerts_test.yml
```
