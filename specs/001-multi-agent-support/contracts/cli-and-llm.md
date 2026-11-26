# CLI and internal interfaces

## CLI (`python -m getnet_multi_agent.cli`)

| Command | Effect |
|---|---|
| `token --sub cliente1988 --role merchant [--ttl-minutes 60]` | prints a signed JWT (only issuance path) |
| `token --sub op1 --role operator` | operator token |
| `refresh [--max-pages N]` | crawls start pages into `data/crawl_cache/` (only networked command) |
| `ingest [--rebuild]` | offline ingestion from the cache into the collection |

Start pages for refresh: `https://site.getnet.com.br/`, `/duvidas/`, `/crediario/`,
`/link-de-pagamento/`, `/pix/`, `/todas-as-maquininhas/`, `https://www.getnet.net/en`,
`https://www.getnet.net/en/our-solutions/in-person-payments`. Rules: depth 1, same host, `/en` only
on www.getnet.net, sequential, 2 s delay, host stops at first 403/429, ≤ `RAG_MAX_PAGES`.

## LLMClient (`core/llm.py`)

```text
generate(task, contents, *, schema=None, tools=None, search=False, system=None) -> LLMResult
embed(texts, task_type) -> list[list[float]]   # 768-d
```

- `task` ∈ {router, critic, summary, personality, knowledge, support, synthesis, judge} selects
  model and thinking level from Settings.
- `LLMResult`: parsed (schema instance or None), text, content (raw model Content for tool loops),
  function_calls, grounding (queries, chunks[{title, uri}]), usage (Usage).
- `search=True` and `tools` together → `ValueError` before any call.
- Timeout per call; one retry on 429/5xx; errors raise `LLMUnavailable`; budget overrun raises
  `BudgetExceeded` before the call (per-request counter in a contextvar).
- Every call logs one JSON line: request_id, task, model, latency, tokens, cost, status.
- Implementations: `GeminiClient` (live), `StubClient` (LLM_MODE=stub), test fakes.

## Agent functions (direct calls)

```text
plan(message, summary, last_turns, principal) -> Plan
critic(message, plan, observations) -> CriticVerdict
knowledge_rag(step, lang) -> Observation      knowledge_web(step, lang) -> Observation
support(step, principal, lang) -> Observation synthesize(message, observations, lang) -> str
personality(draft, lang) -> str                escalate(state, reason) -> (ticket_id, checkpoint_id)
```
