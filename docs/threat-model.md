# Threat model

Scope: the Getnet multi-agent support service (FastAPI API, supervisor, SQLite and Chroma state, Gemini calls) as built from `specs/001-multi-agent-support/`. Requirement IDs (FR-NNN) refer to [`spec.md`](../specs/001-multi-agent-support/spec.md). The deployment target is a single node with simulated merchant data; there is no real Getnet integration.

## Assets

| Asset | Why it matters |
|---|---|
| Merchant data | Sales, settlement dates, amounts and terminal state of each merchant (`data/merchants.json`, simulated here, real in production). Disclosure to another merchant is the costliest failure. |
| Tokens and secrets | `JWT_SECRET` (forges any identity), `PSEUDONYM_KEY` (reverses pseudonyms by brute force), `GEMINI_API_KEY` (spend). |
| Conversations | Turns, rolling summaries and run checkpoints in SQLite; may contain personal context even after masking. |
| Operator actions | Claim, approve, edit and reject decide what a merchant is told; they must be attributable (audit). |
| LLM budget | Every request spends paid tokens and, for web questions, paid search queries. |

## Actors

| Actor | Capability and intent |
|---|---|
| Merchant | Authenticated, legitimate. May also be curious about other merchants or try to manipulate the model. |
| Other merchant | Holds a valid merchant token for a different subject; wants the first merchant's data or conversations. |
| Operator | Authenticated with role `operator`; trusted to resolve tickets but not to act unaudited or to use merchant routes. |
| External attacker | No valid token; probes endpoints, replays or forges tokens, tries to exhaust budget. |
| Malicious web content | Text on a crawled or searched page, or inside a tool result, crafted to instruct the model. |

## Entry points

| Entry point | Exposure |
|---|---|
| `POST /chat`, `GET /conversations/{id}` | Bearer token, role `merchant`; free-text message from the user. |
| `/operator/*` (tickets, claim, resolve, retrieval) | Bearer token, role `operator`; operator free text. |
| `GET /health/live`, `/health/ready`, `/metrics` | Public; return status, revision, chunk count and aggregate metrics only. |
| Crawl cache and Google Search results | Third-party text that reaches prompts. |
| Tool results | Merchant data fields that reach prompts. |
| CLI (`token`, `refresh`, `ingest`) | Local or container shell access; the only token issuance path and the only networked command besides model calls. |
| Container image and dependencies | Supply chain. |

## Threats and mitigations

| # | Threat | Mitigation | FR |
|---|---|---|---|
| T1 | Prompt injection in the user message ("ignore your instructions", "ignore suas instruções", role-play, prompt extraction). | Deterministic English and Portuguese patterns refuse before any LLM call (`prompt_injection`, zero model calls). Patterns that slip through meet agent prompts with fixed role, scope and refusal rules, and the Router plans `unsafe` and `out_of_scope` refusals. Authorization never depends on the model, so a successful injection cannot widen data access. | FR-029, FR-030, FR-056 |
| T2 | Indirect injection through retrieved pages, search results or tool results. | Retrieved chunks are delimited in `<context>` and tool output is passed inside an `untrusted_data` envelope; prompts state that such content is data and must never be followed or repeated. Tool arguments never include the merchant id. Final DLP and the Personality fact lock limit what injected text can add to the answer. | FR-028, FR-032, FR-009 |
| T3 | Leakage of card numbers or CPFs, from user input or from model output. | Luhn-valid card numbers and valid CPFs are refused by code with a warning; the values are masked in every field before logs or storage; the final answer passes DLP before it is returned. | FR-029, FR-031, FR-032 |
| T4 | Cross-merchant access: asking about another merchant, tampering with `user_id`, reading another merchant's conversation, abusing tools. | Other merchant ids in the message are refused by code; the Router plans `other_merchant` for requests without an id; `user_id` must equal the token subject (403); tools take the merchant id from the authenticated principal, not from the model; conversations belong to their owner (404 otherwise); DLP replaces other merchants' ids in answers. | FR-027, FR-029, FR-030, FR-034, FR-037 |
| T5 | Token forgery, tampering, replay or theft. | HS256 verification with required `iss`, `aud`, `exp`, `sub` and role claims and a pinned algorithm list; invalid tokens return 401. Tokens expire (default TTL 60 minutes, `--ttl-minutes` to shorten), which bounds replay. Tokens are issued only by the CLI, never by an HTTP endpoint. Token issuance and verification fail closed (error 500) when `JWT_SECRET` is empty. | FR-033, FR-035 |
| T6 | Privilege escalation: a merchant calling operator routes, or an operator using merchant routes. | Role is checked per route by dependency (`merchant` for `/chat` and `/conversations`, `operator` for `/operator/*`); mismatch returns 403. Only the claimant may resolve a ticket; claim is atomic (409 on a second claim). Every operator action writes an audit entry. | FR-034, FR-043, FR-044, FR-045 |
| T7 | Cost abuse and denial of service: oversized messages, loops, repeated expensive requests. | Message length limit (`MAX_MESSAGE_CHARS`) enforced by code; bounded supervisor (`MAX_SUPERVISOR_ITERATIONS`), bounded tool turns (`MAX_TOOL_ITERATIONS`), per-request token budget that escalates when spent; timeout and exactly one retry per model call; every call metered with cost, and the `HighCostPerHour` alert. Search grounding is a separate, counted call. Per-principal rate limiting is not part of the base build (see residual risks). | FR-053, FR-054, FR-055, FR-007, FR-029, FR-059 |
| T8 | Hallucinated or ungrounded answers about products, prices or terms. | Domain answers must cite source URLs; without grounding the system retries once with a rewritten query and then escalates that part instead of guessing. Sources are attached by code after Personality. Global-site content is labeled as not confirmed for Brazil. | FR-021, FR-006, FR-010, FR-020 |
| T9 | Personality (brand voice) altering facts, numbers or URLs. | Code compares the sets of numbers and URLs in the draft and the styled text in both directions; any difference returns the unstyled draft. Personality failure also returns the draft. | FR-009 |
| T10 | Exposure of personal data or identifiers through logs, metrics, prompts or the audit trail. | Logs and prompts carry an HMAC pseudonym instead of the raw user id; card numbers and CPFs are masked before reaching logs or storage; metrics are aggregate with no user label; JSON logs are rotated by size. | FR-036, FR-031, FR-057 |
| T11 | Supply chain: malicious or drifting images and packages. | Base images pinned by digest (Python, Prometheus, Grafana); `uv sync --frozen` from a committed lockfile with exact pins for the main libraries; non-root container (uid 10001); ports bound to 127.0.0.1. | FR-069 |
| T12 | Secrets baked into the image or the repository. | `.env` is git-ignored and excluded from the build context by `.dockerignore` (only `.env.example` is committed); the container receives secrets at runtime through `env_file`; CI generates throwaway secrets and reads the Gemini key from a repository secret. | FR-069, FR-070 |
| T13 | Failure leaving the user without an answer, or an unhandled error leaking internals. | Router parse failure, tool failure, LLM unavailability and budget exhaustion all end in valid JSON with an escalation; validation errors and all failures return a JSON error body with `request_id`. | FR-041, FR-050, FR-055 |

## Residual risks

- **Injection heuristics are pattern-based.** Novel phrasings can pass the code check. Mitigations downstream (prompt rules, untrusted-data delimiting, authorization by code, DLP) limit impact, but a model can still be steered into a wrong or off-topic answer. The adversarial eval cases measure this; they do not prove its absence.
- **DLP and masking cover card numbers, CPFs and merchant ids.** Other personal data (names, addresses, free-form identifiers) is not detected.
- **No rate limiting per principal.** An authenticated client can send many valid requests; the per-request caps bound cost per request, the cost alert signals the problem after the fact. Rate limiting is only present if the optional task was built; otherwise this is open. Production would add limits at a gateway or in Redis.
- **Shared-secret HS256.** Anyone with `JWT_SECRET` can mint any identity, including operators, and there is no revocation list; the short TTL is the only containment. Production would use OIDC with JWKS and per-role audiences.
- **Operator trust.** An operator can send arbitrary text to a merchant; the answer passes Personality and DLP, and the action is audited, but content is not otherwise reviewed.
- **Grafana and Prometheus under the observability profile** run with anonymous viewer access and a default admin password unless `GRAFANA_ADMIN_PASSWORD` is set; they bind to localhost only and are meant for local use.
- **Third-party content.** The knowledge base is a snapshot of public pages and web search is live; either can contain false or manipulated statements. Grounding proves where a statement came from, not that it is true.
- **Same-family judge.** Eval scores come from a judge in the same model family as the agents, which can share blind spots.
- **Single node.** SQLite and Chroma on one volume have no replication or encryption at rest; protect the host and volume accordingly.
