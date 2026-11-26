# Data Model

## Shared contracts (`src/getnet_multi_agent/contracts.py`, Pydantic)

| Model | Fields |
|---|---|
| Principal | sub, role (`merchant`\|`operator`) |
| Step | id, agent (`knowledge`\|`support`\|`escalation`), source (`rag`\|`web`\|null), query |
| Plan | steps[Step], lang (`en`\|`pt`), standalone (str), refusal_reason (null\|`unsafe`\|`out_of_scope`\|`other_merchant`\|`prompt_injection`), escalate_reason (null\|`human_requested`) |
| PlanRevision | iteration, action (`add`\|`retry`\|`drop`), step_id, reason |
| Evidence | url, title, score, excerpt (≤ 200 chars) |
| Usage | model, latency_ms, prompt_tokens, output_tokens, thinking_tokens, search_queries, cost_usd |
| Observation | step_id, agent, source, status (`answered`\|`partial`\|`no_grounding`\|`failed`), answer, evidence[Evidence], unanswered[str], data (typed tool result or null), usage[Usage] |
| CriticVerdict | complete (bool), missing_parts[str], revisions[PlanRevision], notes[str] |
| AgentResult | answer, grounded (bool), cited_ids[str], unanswered[str] |
| Trace | plan_revisions, critic_notes, observations, steps_usage, total {tokens, cost_usd, latency_ms} |
| ChatRequest | message (1..MAX_MESSAGE_CHARS), user_id, conversation_id (optional) |
| ChatResponse | answer, status (`answered`\|`awaiting_human`\|`refused`), refusal_reason, route, sources[{title,url}], ticket_id, conversation_id, request_id, trace |
| Ticket | id, conversation_id, owner_sub, reason, status, claimed_by, created_at, updated_at |

Refusal reasons (response): `sensitive_data`, `other_merchant`, `prompt_injection`, `unsafe`,
`out_of_scope`, `too_long`. Escalation reasons: `human_requested`, `no_grounding`, `tool_failure`,
`llm_failure`, `budget_exceeded`.

## SQLite (`data/state/app.db`, WAL)

| Table | Columns | Notes |
|---|---|---|
| conversations | id (uuid pk), owner_sub, created_at | owner check on every read → 404 |
| turns | id (pk), conversation_id fk, role (`user`\|`assistant`\|`operator`), text (masked), route, status, sources_json, request_id, created_at | append-only |
| summaries | conversation_id pk, text, last_turn_id, updated_at | rolling, lite model |
| checkpoints | id (uuid pk), conversation_id, request_id, state_json (plan, observations, answered parts, proposed answer, lang), created_at | written on escalation |
| tickets | id (uuid pk), conversation_id, checkpoint_id, owner_sub, reason, status, claimed_by, resolution_json, created_at, updated_at | index on status |
| audit | id (pk), ticket_id, actor (HMAC pseudonym), action (`escalated`\|`claimed`\|`approve`\|`edit`\|`reject`), detail_json, created_at | append-only |

Ticket state machine: `open → claimed` (`UPDATE … SET status='claimed', claimed_by=? WHERE id=?
AND status='open'`; rowcount 0 → 409) → `resolved` (approve, edit) or `rejected` (reject); only the
claimant may resolve.

## Knowledge base (Chroma, `data/state/chroma`, collection `getnet_kb`, cosine)

Chunk metadata: url (final URL), site (`br`\|`global`), title, heading, kind (`section`\|`faq`\|
`table`\|`card`), is_rule (bool), text_hash. Id = sha256(url + heading + ordinal).

Crawl cache (`data/crawl_cache/`, read-only in the image): `<sha256(normalized url)>.json` with
url, final_url, status, content_type, plus `<same>.html`.

## Simulated merchant data (`data/merchants.json`)

Offsets in days relative to today (UTC-03:00), resolved at read time:

- `cliente1988`: terminals `T-1001` (offline, error `CONNECTIVITY: no data network`, suggested
  actions) and `T-1002` (online, decline `51 insufficient funds` within the last hour, suggested
  actions); sales at offsets −1 (several) and −2..−5, each with amount, sale date, settlement date,
  payment type.
- `cliente2000`: one terminal and its own sales.

Tool results: `ReceivablesResult` {merchant_found, from_date, to_date, items[{sale_date,
settlement_date, amount, payment_type}], total} and `TerminalStatusResult` {merchant_found,
terminals[{id, model, connectivity, last_errors[{at, code, message, kind}], suggested_actions}]}.
Date filter validation: ISO dates, from ≤ to, range ≤ 90 days.
