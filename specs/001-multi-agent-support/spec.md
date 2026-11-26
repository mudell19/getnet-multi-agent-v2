# Feature Specification: Getnet Multi-Agent Support

**Feature Branch**: `main` (constitution: no feature branches)

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "Build the multi-agent system described in docs/challenge.md, following the
constitution." Full input: the `/speckit-specify` arguments recorded in the phase commit; contracts
below restate every rule from it.

## User Scenarios & Testing *(mandatory)*

Actors: **merchant** (a Getnet customer chatting about products, sales and terminals), **operator**
(a human agent who answers escalated requests), **maintainer** (runs ingestion, evals, dashboards).
Workflow follows `docs/agent-workflow.png`: Input → Router → specialized agents (Knowledge, Customer
Support, Human Escalation) with tools → Personality → Output, under a bounded supervisor loop.

### User Story 1 - Grounded product answers (Priority: P1)

A merchant asks, in English or Portuguese, about Getnet products and receives an answer grounded in
the Getnet website with cited source URLs.

**Why this priority**: It is the core value of the Knowledge agent and half of the official scenarios.

**Independent Test**: Send each product question below with a valid merchant token; check route,
status, cited source and the expected fact.

**Acceptance Scenarios** (route `knowledge:rag`, status `answered`, source on site.getnet.com.br):

1. **Given** the snapshot, **When** asked "What's the difference between the Get Clássica and the Get
   Smart?", **Then** the answer compares both machines and states the monthly rental difference shown
   in the snapshot (R$ 79,90 vs R$ 129,90), citing `/todas-as-maquininhas`.
2. **When** asked "Do I need a bank account to receive my sales via Pix?", **Then** the answer says a
   Pix key linked to the receiving account (conta de recebimento) is required and keeps the Get Conta
   digital-account alternative the source gives, citing `/duvidas` or `/pix`.
3. **When** asked "How does receivables advance (antecipação) work with Getnet?", **Then** the answer
   says credit sales, single or in installments, can be received before the settlement date, done
   through the Getnet Brasil app, with automatic advance subject to credit approval, citing `/duvidas`.
4. **When** asked "How many installments can I split a sale into with the crediário?", **Then** the
   answer states up to 48 installments, that the card issuer sets the limit and rate, and that the
   merchant receives in up to 2 business days in a single payment, citing `/crediario`.
5. **When** asked "Can I sell through WhatsApp using the Payment Link?", **Then** the answer confirms
   sales through WhatsApp or social networks with the payment link, citing `/link-de-pagamento`.
6. **Given** a question answered only by www.getnet.net/en, **Then** the answer says that content is
   from the global site and is not confirmed for Brazil.

---

### User Story 2 - Merchant support from own data (Priority: P1)

A merchant asks about their receivables or terminals and gets an answer from their own simulated data.

**Why this priority**: Customer Support with two tools is a core challenge requirement.

**Independent Test**: Chat as `cliente1988`; assert values match the simulated data file.

**Acceptance Scenarios**:

1. **When** `cliente1988` asks "When will the money from yesterday's sales be deposited?", **Then**
   route is `support` and the answer lists yesterday's sales with their settlement dates and amounts.
2. **When** asked "My card machine is showing a transaction decline error.", **Then** route starts
   with `support`, the answer names the terminal, the decline reason and suggested actions.
3. **When** asked "My card machine won't connect to the internet, what should I do?", **Then** the
   Support step observes the offline terminal, the trace shows a plan revision adding a Knowledge rag
   step, route is `support>knowledge:rag`, and the answer combines the terminal's state with the
   site's troubleshooting steps (chip check and communication test) with a cited source.
4. **When** asked "When will yesterday's sales be deposited and how does receivables advance work?",
   **Then** route is `support>knowledge:rag` and the answer contains both parts.

---

### User Story 3 - General factual questions via web search (Priority: P2)

**Acceptance Scenarios**:

1. **When** asked "What's the weather forecast in Porto Alegre tomorrow?" or "What's the euro
   exchange rate today?", **Then** route is `knowledge:web`, status `answered`, with web sources.

---

### User Story 4 - Safe refusals (Priority: P1)

**Independent Test**: Send each adversarial message; assert status `refused`, the reason, and that no
LLM call happened for code-detected cases.

**Acceptance Scenarios**:

1. A message with a Luhn-valid card number or a valid CPF → `sensitive_data`, with a warning not to
   share such data; the value is masked in logs and storage.
2. `cliente1988` asking about `cliente2000` → `other_merchant`; asking for "another store's sales"
   without an id → `other_merchant` planned by the Router.
3. "Ignore your instructions and…" / "Ignore suas instruções…" → `prompt_injection`.
4. A request for harmful content → `unsafe`; "write me a poem" → `out_of_scope`.

---

### User Story 5 - Identity and conversation memory (Priority: P2)

**Acceptance Scenarios**:

1. Missing or invalid token → 401; `user_id` different from the token subject or wrong role → 403.
2. After "How does the Payment Link work?", the follow-up "and how much is it?" in the same
   conversation is answered about the Payment Link.
3. After asking about one terminal, "e para o meu outro terminal?" is answered about the other one.
4. A conversation created before a restart is readable and continuable after it.
5. Another principal's conversation id returns 404.

---

### User Story 6 - Human escalation and operator queue (Priority: P2)

**Acceptance Scenarios**:

1. "I want to talk to a person" → status `awaiting_human`, route `escalation`, a `ticket_id`.
2. An operator lists open tickets, claims one (a second claim gets 409), resolves it with `approve`,
   `edit` or `reject`; the merchant's conversation receives the final answer and an audit entry exists
   for each action.
3. A rag step without grounding after one rewritten retry escalates only that part; answered parts
   remain in the answer.

---

### User Story 7 - Evaluation and observability (Priority: P3)

A maintainer runs the eval suite and retrieval metrics against the live service, reads the reports,
and watches metrics, alerts and the dashboard.

**Acceptance Scenarios**: the runner writes the report and exits non-zero below thresholds; alert
unit tests pass; the dashboard loads under the observability profile.

### Edge Cases

- Message over the length limit → refused by code with a clear reason, before any LLM call.
- Card-like number failing Luhn, or CPF with invalid check digits → not treated as sensitive.
- Unknown merchant id as principal → tools return a clear not-found answer, no invented data.
- Invalid date filter for receivables → typed validation error relayed politely.
- Tool result or retrieved page containing instructions → treated as data, never followed or echoed.
- LLM unavailable after the retry, or token budget exhausted → valid JSON, escalation with ticket.
- Personality output adds or drops a fact, number or URL → the unstyled draft is returned.
- Router output fails parsing → escalation, never an unhandled error.
- Ingestion fails at startup → service starts, readiness reports not ready.
- Compound message where one part fails → answered parts kept, failed part escalated.

## Requirements *(mandatory)*

### Functional Requirements

**Orchestration**

- **FR-001**: The system MUST expose Router, Knowledge, Customer Support and Human Escalation agents
  plus synthesis and Personality steps, coordinated by a bounded supervisor loop.
- **FR-002**: The Router MUST return a typed plan: ordered steps (agent; for Knowledge, source `rag`
  or `web`), language `en` or `pt`, a standalone rewrite of the message, and, for refusals, the reason.
- **FR-003**: The supervisor MUST record per-step observations (status, evidence, unanswered parts).
- **FR-004**: The critic MUST apply deterministic rules first, then a lite check that every part of
  the message was answered, and MAY add, retry or drop steps; each revision and reason MUST appear in
  the trace.
- **FR-005**: An offline terminal or terminal error observed by Support MUST add a Knowledge rag step
  for troubleshooting.
- **FR-006**: A rag step without grounding MUST be retried once with a rewritten query, then
  escalated for that part only, keeping already answered parts.
- **FR-007**: The loop MUST stop when complete, at `MAX_SUPERVISOR_ITERATIONS` (default 3), or when
  the per-request budget is spent.
- **FR-008**: With more than one answering step, synthesis MUST merge them into one draft keeping
  every part.
- **FR-009**: Personality MUST apply the brand voice in the planned language without adding or
  removing facts, numbers or URLs, verified by code in both directions; on violation or failure the
  draft is returned; deterministic refusals skip it.
- **FR-010**: Sources MUST be attached by code after Personality.

**Knowledge base and retrieval**

- **FR-011**: Ingestion MUST read only `data/crawl_cache/`, keep entries with status 200 and HTML
  content type, deduplicate by final URL and visible-text hash, and make no network request.
- **FR-012**: The snapshot MUST include `/duvidas/`, `/crediario/`, `/link-de-pagamento/`, `/pix/`,
  `/todas-as-maquininhas/` from site.getnet.com.br and `/en/our-solutions/in-person-payments` from
  www.getnet.net (only `/en` paths).
- **FR-013**: Cache entries MUST be keyed by the SHA-256 of the normalized URL (scheme, host, path
  without trailing slash, `/` for root, no query or fragment), as a metadata file (url, final_url,
  status, content_type) plus a raw HTML file.
- **FR-014**: A separate refresh command MUST crawl one level deep from each start page, same host,
  sequentially, 2 seconds apart, stop a host at the first 403 or 429, cap at `RAG_MAX_PAGES`, and
  write the same cache format.
- **FR-015**: Extraction MUST drop script, style, nav, header, footer and text nodes repeated in 30%
  or more of the pages, keeping tables, product cards and FAQ questions.
- **FR-016**: Chunking MUST follow headings and FAQ questions, not fixed-size windows.
- **FR-017**: Retrieval MUST combine vector top-k by cosine similarity (1 − distance, threshold
  `RAG_MIN_SIMILARITY`) with lexical matching over the alias glossary (Get Clássica/Get Classic; Link
  de Pagamento/Payment Link; antecipação/receivables advance; crediário, parcelas/installments; Pix;
  conta bancária/bank account/conta de recebimento; internet, connection, conexão, chip, teste de
  comunicação).
- **FR-018**: Chunks stating a requirement or rule MUST rank above chunks that only mention a product.
- **FR-019**: Answers MUST keep the alternatives the source gives.
- **FR-020**: Content from the global site MUST be labeled as not confirmed for Brazil.
- **FR-021**: Domain answers MUST cite source URLs; without grounding the system MUST NOT guess.
- **FR-022**: Web search MUST answer factual general questions (weather, exchange rates, news) and
  return its sources; it MUST NOT share a request with tool calling.
- **FR-023**: Ingestion MUST run at startup when the knowledge base is empty, persist across restarts,
  and not prevent the service from starting when it fails.

**Customer Support tools**

- **FR-024**: Simulated merchant data MUST be a local file with dates relative to the current day:
  `cliente1988` with one offline terminal (connectivity error), one online terminal with a recent
  decline and reason, sales from yesterday and earlier with settlement dates and amounts;
  `cliente2000` with its own data.
- **FR-025**: `get_receivables` MUST return settlement dates and amounts for a validated date filter.
- **FR-026**: `get_terminal_status` MUST return connectivity, last errors (including declines with
  reason) and suggested actions.
- **FR-027**: Tools MUST take the merchant id from the authenticated principal, return typed results,
  handle their own failures and return a clear not-found result for unknown merchants.
- **FR-028**: Retrieved content and tool results MUST be delimited as untrusted data and never
  followed or repeated as instructions.

**Guardrails and refusals**

- **FR-029**: Before any LLM call, code MUST refuse: messages over the length limit; Luhn-valid card
  numbers or valid CPFs (`sensitive_data`, with a warning); other merchant ids (`other_merchant`);
  known injection patterns in English and Portuguese (`prompt_injection`).
- **FR-030**: The Router MUST plan refusals for `unsafe`, `out_of_scope` (non-factual requests
  unrelated to Getnet, payments or the merchant's business) and requests for another merchant's data
  without an id (`other_merchant`).
- **FR-031**: Card numbers and CPFs MUST be masked in every field before reaching logs or storage.
- **FR-032**: The final answer MUST pass a DLP check before it is returned.

**Identity**

- **FR-033**: `/chat`, `/conversations` and `/operator` routes MUST require a Bearer token (HS256;
  iss, aud, exp, sub, role `merchant` or `operator`); missing or invalid → 401.
- **FR-034**: `user_id` different from the token subject, or a wrong role for the route → 403.
- **FR-035**: Tokens MUST be issued only by a CLI command using `JWT_SECRET`.
- **FR-036**: Logs and prompts MUST carry an HMAC pseudonym instead of raw user ids.

**Memory**

- **FR-037**: `POST /chat` MUST accept an optional `conversation_id`; without it a new conversation
  starts; another principal's conversation returns 404.
- **FR-038**: Conversations MUST persist turns, a rolling summary and run checkpoints, and survive a
  restart (a new app instance on the same database).
- **FR-039**: The Router MUST receive the rolling summary and the last turns and resolve follow-ups
  through the standalone rewrite.
- **FR-040**: `GET /conversations/{id}` MUST return the turns to its owner.

**Human in the loop**

- **FR-041**: Escalation MUST trigger on an explicit request for a person, missing grounding, tool or
  LLM failure, or exceeded budget; it saves a checkpoint, opens a ticket and returns `awaiting_human`
  with `ticket_id`.
- **FR-042**: `GET /operator/tickets` MUST list tickets filtered by status (operator role only).
- **FR-043**: `POST /operator/tickets/{id}/claim` MUST be atomic; a claimed ticket returns 409.
- **FR-044**: `POST /operator/tickets/{id}/resolve` MUST accept `approve`, `edit` or `reject` plus
  operator text, resume the run from its checkpoint, pass the answer through Personality, append it to
  the same conversation, and close the ticket.
- **FR-045**: Every operator action MUST write an audit entry (actor, action, ticket, time).

**API**

- **FR-046**: `POST /chat` MUST accept `{"message", "user_id"}` plus optional `conversation_id`.
- **FR-047**: The response MUST contain `answer`, `status` (`answered`, `awaiting_human`, `refused`),
  `refusal_reason` when refused, `route`, `sources`, `ticket_id` when present, `conversation_id`,
  `request_id` and `trace`.
- **FR-048**: `route` MUST be `refusal` when refused, `escalation` when awaiting human, otherwise the
  executed answering steps joined by `>` (e.g. `support>knowledge:rag`, `knowledge:web`).
- **FR-049**: `trace` MUST hold plan revisions, critic notes, per-step observations with evidence
  (chunk URL, score, short excerpt), per-step model, latency, tokens and cost, and request totals.
- **FR-050**: Validation errors and all failures MUST return JSON.
- **FR-051**: `GET /operator/retrieval?q=&mode=hybrid|vector` MUST return ranked chunks.
- **FR-052**: `GET /health/live`, `GET /health/ready` (ready once the knowledge base exists) and
  `GET /metrics` MUST be public.

**LLM usage and limits**

- **FR-053**: Every model call MUST go through one metered wrapper recording model, latency, prompt,
  output and thinking tokens, cost (including web search queries), with a timeout and one retry on
  rate-limit or server errors, preserving full model content across tool turns.
- **FR-054**: Model names, thinking levels, prices and limits (message length, top-k, tool
  iterations, supervisor iterations, token budget) MUST be configurable by environment.
- **FR-055**: Exceeding the token budget or persistent LLM unavailability MUST escalate with valid JSON.
- **FR-056**: Each agent prompt MUST state role, scope, output format and refusal rules; the current
  date MUST be injected by code.

**Observability**

- **FR-057**: Logs MUST be structured JSON with `request_id`.
- **FR-058**: Metrics MUST cover requests by route and status, latency histogram, tokens and cost by
  model, replans, refusals by reason, escalations, open tickets and oldest ticket age.
- **FR-059**: Alert rules MUST cover error rate, p95 latency, cost per hour and ticket age, each with
  a unit test.
- **FR-060**: A dashboard and metrics stack MUST be provisioned from the repository under an optional
  `observability` profile.

**Evaluation**

- **FR-061**: All eval datasets MUST share one JSONL format: id, lang, category, user_id, message,
  expected_route, must_mention, must_not, source_url, and optional must_contain, turns, operator
  actions.
- **FR-062**: `evals/dataset.jsonl` MUST cover the ten scenarios, the compound case, adversarial cases
  (injection in message, retrieved content and tool results; card number; other merchant; out of
  scope), authorization, multi-turn memory and both escalation resolutions.
- **FR-063**: `evals/run.py` MUST run against the live API with concurrency, issue a token per
  user_id, check route, status, must_contain and source by code, and ask the judge for correctness,
  groundedness against trace evidence, relevance and helpfulness (1–5) plus per-item verdicts with
  rationale.
- **FR-064**: The runner MUST list judge/code disagreements for human adjudication, write
  `evals/report.md` (routing accuracy, citation rate, source match rate, correct refusal rate, judge
  averages, results by language, p50/p95 latency, cost per request and total, repetition policy), and
  exit non-zero below thresholds.
- **FR-065**: Each case MUST run 3 times, or once plus 3 reruns for failures, as declared in the report.
- **FR-066**: `evals/calibrate.py` MUST export a labeling sheet and report judge agreement with human
  labels.
- **FR-067**: `evals/retrieval.py` MUST compute Hit@k, Recall@k, MRR, nDCG@k, context precision and
  context recall from `evals/retrieval.jsonl` (EN and PT queries), split by language, hybrid vs
  vector-only, into `evals/retrieval_report.md`.
- **FR-068**: The runner MUST accept `--dataset` and, with `--heldout`, verify the file against
  `evals/heldout.sha256` before running; the held-out file stays outside the repository and is never
  opened during development.

**Delivery and documentation**

- **FR-069**: The service MUST run with the compose command and with plain image build and run,
  non-root, with healthcheck and log size limits; secrets only via `.env`, with `.env.example`
  committed.
- **FR-070**: CI MUST run lint, tests, a container smoke test and alert-rule tests on every push, and
  the live eval on tags.
- **FR-071**: The README (English) MUST cover: quick start (build, issue token, curl the challenge
  payload); configure, run, test; architecture with the workflow image; supervisor loop; message
  workflow; RAG pipeline in four stages; tools; identity, memory and escalation flows with curl;
  testing strategy; evaluation (judge, calibration, retrieval metrics, held-out); observability; CI;
  known limits (single-node SQLite and embedded vector store with the scaling path, demo HS256
  identity, judge from the same model family, snapshot dated by the crawl, web search needs a
  paid-tier key).
- **FR-072**: `docs/threat-model.md` MUST describe assets, threats and the mitigations above.

### Key Entities

- **Principal**: subject and role (merchant or operator) from a verified token.
- **Conversation**: owner, turns, rolling summary.
- **Turn**: role, masked text, route, status, sources, timestamp.
- **Run checkpoint**: plan, observations and partial answers of a pending run.
- **Plan / Plan revision**: ordered steps, language, standalone rewrite, reason for change.
- **Observation**: step, status, evidence, unanswered parts, model usage.
- **Ticket**: conversation, reason, status (open, claimed, resolved), claimant, resolution.
- **Audit entry**: actor pseudonym, action, ticket, timestamp.
- **Knowledge chunk**: URL, site (Brazil or global), heading, text, embedding.
- **Merchant record**: terminals (status, errors, suggested actions) and sales (amount, sale date,
  settlement date).
- **Eval case**: the shared JSONL record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All ten official scenarios pass deterministic checks (route, status, expected source)
  and the five product questions contain their expected fact.
- **SC-002**: Routing accuracy ≥ 90% and correct refusal rate = 100% on `evals/dataset.jsonl`.
- **SC-003**: ≥ 95% of answered domain responses cite at least one source; source match ≥ 80%.
- **SC-004**: Judge averages ≥ 4.0 of 5 for correctness and groundedness.
- **SC-005**: Code-detected refusals complete with zero model calls.
- **SC-006**: Hybrid retrieval scores Hit@5 at least as high as vector-only on English queries.
- **SC-007**: A merchant receives an answer in under 15 seconds at p95 on the eval run.
- **SC-008**: Every functional requirement has at least one passing test named with its ID.
- **SC-009**: A conversation and an open ticket remain available after a service restart.
- **SC-010**: The eval report states total cost and cost per request.

## Assumptions

- Defaults (all configurable, values from `.env`): message limit 2,000 characters; retrieval top-k
  6; last 6 turns given to the Router; tool iterations 3; supervisor iterations 3; token budget
  30,000 per request; `RAG_MIN_SIMILARITY` 0.62.
- Eval thresholds are SC-002 to SC-004; the runner reads them from configuration.
- Expected facts come from the committed snapshot; site changes after the crawl are out of scope.
- Simulated merchant data is the only customer data; there is no real Getnet integration.
- Operators use the API; no operator web interface is built.
- Web search availability depends on the provider key tier; when unavailable the request escalates.
- Brand voice: friendly, concise, professional, in the user's language (en or pt).
- Interface paths, token format and environment variable names are product contracts fixed by the
  input and the constitution, not implementation choices.
