# Getnet Multi-Agent Constitution

## Core Principles

### I. Bounded Supervisor Orchestration

- Orchestration MUST be plain Python with direct function calls. Agent frameworks are forbidden.
- Orchestration MUST be a bounded supervisor loop, not a fixed pipeline.
- A Router MUST return a typed plan containing: ordered steps (agent and, for Knowledge, source
  `rag` or `web`), the user language (`en` or `pt`), and a standalone rewrite of the message that
  resolves references to earlier turns.
- The supervisor MUST execute each step and record a structured observation with status, evidence
  and unanswered parts.
- A critic MUST review observations by applying deterministic rules first, then a lite-model check
  that every part of the user message was answered. The critic MAY replan by adding, retrying or
  dropping steps; every plan revision and its reason MUST be kept in the trace.
- The loop MUST stop when the answer is complete, at `MAX_SUPERVISOR_ITERATIONS`, or when the
  per-request budget is spent.
- When more than one step answered, a synthesis step MUST merge their answers into one draft that
  keeps every part.
- A final Personality step MUST apply the brand voice in the planned language and MUST NOT add or
  remove facts, numbers or URLs. Code MUST check this in both directions; on violation or failure
  the draft is returned unchanged. Deterministic refusals skip Personality.
- Sources MUST be attached by code after Personality.
- Each agent prompt MUST live in its own module and state role, scope, output format and refusal
  rules. The current date MUST be injected by code.

Rationale: a bounded, traced loop handles compound questions without unbounded cost, and keeping
voice separate from facts makes the brand layer verifiable.

### II. Identity and Authorization by Code

- Every endpoint except health and metrics MUST require a Bearer JWT (HS256 with `iss`, `aud`,
  `exp`, `sub` and `role` in {`merchant`, `operator`}) verified by code.
- The chat `user_id` MUST equal the token subject; otherwise the request returns 403.
- Tools MUST receive the merchant id from the authenticated principal, never from the LLM.
- Conversations and tickets MUST belong to their principal and be inaccessible to others.
- Tokens MUST be issued only by a CLI command, never by an HTTP endpoint.
- Raw user ids MUST NOT reach logs or prompts; logs carry an HMAC pseudonym.

Rationale: authorization decided by a model is not authorization.

### III. Deterministic Guardrails and Grounded Answers

- Guardrails MUST be deterministic first and run before any LLM call:
  - a message length limit;
  - refusal of any message carrying a full Luhn-valid card number or a valid CPF, with such values
    masked in every field before they reach a log or the database;
  - refusal of any message that names another merchant;
  - prompt-injection heuristics in English and Portuguese.
- The final answer MUST pass a DLP check.
- Retrieved content and tool results are untrusted data: they MUST be delimited in prompts and
  never followed or repeated as instructions.
- Unsafe or out-of-scope requests MUST receive a polite refusal.
- Domain answers MUST be grounded in retrieved context with cited source URLs. When grounding
  fails the system MUST NOT guess and MUST escalate.

Rationale: payment-domain data leaks and invented answers are the costliest failures; cheap
deterministic checks stop them before any model sees the input.

### IV. Right Model per Task, Metered LLM Access

- Google Gemini through the `google-genai` SDK is the only LLM provider, at runtime and in evals.
- All model names and thinking levels MUST come from environment variables:
  - planning, critic, memory summary and Personality: `GEMINI_ROUTER_MODEL`, thinking minimal;
  - answering agents and synthesis: `GEMINI_MODEL`, thinking low;
  - embeddings: `GEMINI_EMBEDDING_MODEL`;
  - eval judge: `GEMINI_JUDGE_MODEL`, thinking high, never on the request path.
- Every LLM call MUST go through one client wrapper that:
  - records model, latency, prompt, output and thinking tokens;
  - computes cost in USD from a price table in environment variables, including Google Search
    queries counted from grounding metadata;
  - logs structured JSON with the `request_id`;
  - applies a timeout and exactly one retry on 429 or 5xx;
  - preserves complete model content, including thought signatures, across tool turns;
  - enforces a per-request token budget.
- Google Search grounding and function calling MUST NOT share a request.
- Limits MUST be explicit and configurable: message length, top-k, tool iterations, supervisor
  iterations, token budget.

Rationale: one choke point makes cost, latency and failure behavior measurable and enforceable.

### V. Typed Control Flow and Graceful Degradation

- Every LLM output that drives control flow MUST be parsed into a Pydantic model.
- Every tool MUST return a typed result and handle its own failures.
- When the budget is exceeded or the LLM stays unavailable, the API MUST still return valid JSON
  and escalate.

Rationale: untyped model output in control flow turns model drift into crashes.

### VI. Durable Memory and Human in the Loop

- Conversations MUST persist in SQLite on a Docker volume, storing turns, a rolling summary
  written by the lite model, and run checkpoints. A conversation MUST survive a restart.
- Follow-ups MUST be resolved by the Router's standalone rewrite.
- Escalation MUST store a checkpoint of the pending run, open a ticket and return status
  `awaiting_human`.
- Operators MUST be able to list tickets, claim them atomically, and resolve them by approve,
  edit or reject.
- Resolving a ticket MUST resume the run from its checkpoint, pass the operator answer through
  Personality, append it to the same conversation, and write an audit entry. Every operator
  action MUST produce an audit entry.

Rationale: escalation is the safe default for ungrounded or failed answers, so it must be durable
and auditable rather than a dead end.

### VII. Observability Implemented

Observability MUST exist as running artifacts, not documentation: JSON logs with `request_id`,
Prometheus metrics at `/metrics`, alert rules with `promtool` unit tests, a provisioned Grafana
dashboard under a compose profile, and health split into live and ready endpoints.

### VIII. Evals Are Part of the Product

- The eval dataset MUST cover the official scenarios plus compound, adversarial, authorization,
  multi-turn memory and human-in-the-loop flows.
- A runner MUST call the live API and apply deterministic assertions plus an LLM judge with a
  typed rubric. The judge MUST be calibrated against human labels.
- Retrieval metrics MUST be reported.
- A sealed held-out set MUST have its hash committed before any code (`evals/heldout.sha256`), and
  nobody opens it during the session.
- The runner MUST exit non-zero below thresholds and report cost.

### IX. Requirement-Traced Tests

- Every functional requirement MUST have an ID (FR-001, FR-002, ...) and at least one pytest test
  whose name contains that ID.
- Unit tests MUST mock the LLM.
- Integration tests MUST call the HTTP API with the LLM stubbed at the client wrapper.

### X. Simplicity over Abstraction

Build only what the spec and this constitution ask for. Abstractions, layers or options without a
current requirement are defects.

## Technology and Delivery Constraints

- Python 3.12 managed with `uv`; FastAPI for the HTTP API.
- The system MUST run with `docker compose up` and with plain `docker build` plus `docker run`.
- The image MUST be non-root, use a base image pinned by digest, install the `uv` lockfile frozen,
  define a healthcheck, and set log size limits.
- GitHub Actions MUST run lint, tests, a container smoke test and `promtool` on every push, and a
  live eval on tags.
- Secrets MUST come only from `.env`; a `.env.example` MUST be committed and `.env` MUST NOT be.

## Development Workflow

- Spec-Driven Development phases run in order: constitution, spec, plan, tasks, implementation.
- Each phase and each completed task MUST get its own commit on the repository default branch,
  pushed immediately. Feature or docs branches MUST NOT be used. The remote history is the
  evidence of each stage and its time.
- The constitution phase is written from the stated principles only, without web research or API
  calls. External contracts (SDK surface, model names, pricing, grounding metadata) MUST be
  verified in the plan phase before any code depends on them.

## Governance

- This constitution supersedes any other practice in the repository. Spec, plan and tasks MUST
  pass a constitution check; any deviation MUST be recorded with its justification in the plan's
  complexity tracking, or the artifact is rejected.
- Amendments MUST be made through `/speckit-constitution`, committed on the default branch with
  the version bump in the message.
- Versioning follows semantic versioning: MAJOR for removing or redefining a principle, MINOR for
  adding a principle or materially expanding guidance, PATCH for clarifications.
- Compliance is verified at each phase commit and by CI; a task is complete only when its tests
  pass and it violates no principle.

**Version**: 1.0.0 | **Ratified**: 2026-11-26 | **Last Amended**: 2026-11-26
