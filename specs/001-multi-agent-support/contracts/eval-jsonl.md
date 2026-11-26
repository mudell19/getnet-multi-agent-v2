# Eval dataset format (dataset.jsonl, held-out, retrieval.jsonl)

One JSON object per line.

| Field | Type | Notes |
|---|---|---|
| id | str | unique |
| lang | `en`\|`pt` | |
| category | str | scenario, compound, adversarial, authorization, memory, hitl |
| user_id | str | token issued for this subject (authorization cases may set `token_sub`/`token_role`) |
| message | str | single-turn message, or the last turn when `turns` is present |
| expected_route | str | response route vocabulary |
| expected_status | str | optional; defaults derived from route (`refusal`→refused, `escalation`→awaiting_human) |
| expected_http | int | optional, for authorization cases (401/403/404) |
| must_mention | [str] | judge verdict per item |
| must_not | [str] | judge verdict per item |
| source_url | str | expected among sources, or "" |
| must_contain | [str] | optional literal substrings checked by code |
| turns | [str] | optional earlier user turns in the same conversation |
| operator | {action, text} | optional; runner claims and resolves the ticket, then checks the conversation |

`retrieval.jsonl`: `{id, lang, query, relevant_urls[str], expected_fact}`.

Judge output (typed): `{correctness, groundedness, relevance, helpfulness: 1..5,
items[{criterion, kind: must_mention|must_not, verdict: pass|fail, rationale}]}`.
