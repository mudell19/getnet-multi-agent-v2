# HTTP API

Auth: `Authorization: Bearer <JWT>` (HS256; iss, aud, exp, sub, role). Missing/invalid → 401.
Every error body is JSON: `{"error": {"code", "message"}, "request_id"}`. Header `X-Request-ID`
on every response.

| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | /chat | merchant | 200 ChatResponse | 401, 403 (user_id ≠ sub or role), 404 (conversation not owned), 422 |
| GET | /conversations/{id} | merchant | 200 `{id, turns[{role, text, route, status, sources, created_at}]}` | 401, 403, 404 |
| GET | /operator/tickets?status=open\|claimed\|resolved\|rejected | operator | 200 `{tickets[Ticket]}` | 401, 403, 422 |
| POST | /operator/tickets/{id}/claim | operator | 200 Ticket | 404, 409 (not open) |
| POST | /operator/tickets/{id}/resolve | operator | 200 `{ticket, turn}` | 404, 409 (not claimed by caller), 422 |
| GET | /operator/retrieval?q=&mode=hybrid\|vector | operator | 200 `{chunks[{rank, url, title, heading, score, similarity, excerpt}]}` | 422 |
| GET | /health/live | — | 200 `{"status":"live","rev"}` | — |
| GET | /health/ready | — | 200 `{"status":"ready","chunks"}` | 503 `{"status":"not_ready","reason"}` |
| GET | /metrics | — | 200 Prometheus text | — |

## POST /chat

Request: `{"message": "…", "user_id": "cliente1988", "conversation_id": "optional uuid"}`

Response (200 for answered, refused and awaiting_human alike):

```json
{
  "answer": "…",
  "status": "answered",
  "refusal_reason": null,
  "route": "support>knowledge:rag",
  "sources": [{"title": "Dúvidas | Getnet", "url": "https://site.getnet.com.br/duvidas/"}],
  "ticket_id": null,
  "conversation_id": "uuid",
  "request_id": "uuid",
  "trace": {
    "plan_revisions": [{"iteration": 1, "action": "add", "step_id": "s2", "reason": "terminal T-1001 offline"}],
    "critic_notes": ["…"],
    "observations": [{"step_id": "s1", "agent": "support", "source": null, "status": "answered",
                      "evidence": [{"url": "…", "title": "…", "score": 0.81, "excerpt": "…"}],
                      "unanswered": [], "usage": [{"model": "…", "latency_ms": 900, "prompt_tokens": 1200,
                      "output_tokens": 150, "thinking_tokens": 40, "search_queries": 0, "cost_usd": 0.0012}]}],
    "total": {"tokens": 4100, "cost_usd": 0.004, "latency_ms": 5200}
  }
}
```

Route vocabulary: `refusal` | `escalation` | answering steps joined by `>` from `support`,
`knowledge:rag`, `knowledge:web` (executed order, duplicates from retries collapsed).

## POST /operator/tickets/{id}/resolve

Request: `{"action": "approve" | "edit" | "reject", "text": "operator text (required for edit and reject)"}`.
Effect: resume from checkpoint, Personality, append assistant turn to the conversation, ticket →
`resolved` (approve/edit) or `rejected`, audit entry.
