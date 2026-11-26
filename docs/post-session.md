# Post-session work

The 60-minute session ended at the tag `sessao-60min` (`64a1e8b`, 52:27 after the first push). Everything in this file happened after the tag, and every later commit says "post-session" in its message. The tag is the deliverable of the session; nothing here rewrites it.

## 1. Live eval on GitHub, tag run

[Actions run 45776859838](https://github.com/mudell19/getnet-multi-agent-v2/actions/runs/45776859838) (`live-eval.yml`, triggered by the tag): the stack was built from the tag with the real Gemini key and `evals/run.py` ran the 32-case dataset (41 runs, policy `1+3`).

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| Routing accuracy | 0.931 | 0.90 | PASS |
| Correct refusal rate | 1.000 | 1.00 | PASS |
| Citation rate | 1.000 | 0.95 | PASS |
| Source match | 0.929 | 0.80 | PASS |
| Judge correctness | 4.000 | 4.0 | PASS |
| Judge groundedness | 3.440 | 4.0 | FAIL |

API cost USD 0.179 (0.0044 per request), judge USD 0.162, p50 4.2 s, p95 19.6 s. The retrieval step did not run, because the workflow stops at the first failed step.

## 2. Held-out set, run once

The sealed set was generated outside this repository, and its SHA-256 has been in `evals/heldout.sha256` since the first commit. It was opened for the first time after the tag and run exactly once, on 2026-11-26 (finished at 05:36, UTC-03:00). The run used the clean-clone container from the session's final proof (`/health/live` reports `rev 5807c7c`), whose code is identical to the tag: `git diff --stat 5807c7c sessao-60min` lists only README, session notes, eval reports and `tasks.md`.

```bash
uv run python evals/run.py --heldout <path outside the repository>/heldout-v2.jsonl --out <report> --results <results>
```

The file is now published as [`evals/heldout/heldout-v2.jsonl`](../evals/heldout/heldout-v2.jsonl) (`shasum -a 256` matches `evals/heldout.sha256`), with the [report](../evals/heldout/report.md) and [per-case results](../evals/heldout/results.jsonl) copied unchanged from the runner's output.

| Metric | Value |
|---|---|
| Cases passing (majority of runs) | 10 of 20 |
| Refusals and escalations | 6 of 6 |
| Web questions | 2 of 2 |
| Support questions | 2 of 4 |
| Knowledge base questions | 0 of 6 |
| Compound (support and knowledge) | 0 of 2 |
| Routing accuracy | 0.700 |
| Source match | 0.000 |
| Judge correctness / groundedness | 2.70 / 3.18 |
| API cost | USD 0.48 for 50 runs (0.0095 per request) |

### What the held-out found

Reading every failed case against the trace, the code and the data:

1. **The judge never sees tool results or web text.** Support tool results are in the response trace (`trace.observations[].data`), but `evals/judge.py` builds the evidence only from `observations[].evidence`, which the Support agent leaves empty; web evidence carries titles and URIs with empty excerpts, because Google Search grounding returns no source text. Correct answers were scored as invented. Example: in H09 the answer says the only amount settling in the next 7 days is R$ 1,250.00 on 2026-11-26, which is exactly what `get_receivables` returns for `cliente1988` that day; the judge gave correctness 1 and wrote that the amount had no support. The tag live eval shows the same pattern: every RAG answer scored groundedness 4 or 5, while the web cases (`s02`, `s07`) and the support cases (`s03`, `s08`) scored 1. The session README attributed the low groundedness to the 300-character evidence excerpts; the per-case scores do not support that explanation.
2. **The knowledge snapshot is one level deep.** Seven of the eight expected source URLs are `/duvidas/<topic>/` subpages, and the committed snapshot, crawled one level from each start page, has none of them. Hence source match 0 (H06's page is in the snapshot but was not among the cited sources). H03 and H05 escalate on missing grounding, which is the designed behavior; the other knowledge answers come from the general FAQ page and miss details only the subpage has.
3. **Judge calls ran out of token budget.** The eval process never opens a request context, so the per-request budget (`REQUEST_TOKEN_BUDGET`, 30,000 tokens) accumulated per worker thread across judge calls. In the last run of 10 of the 20 cases the judge failed (9 `BudgetExceeded`, 1 `LLMUnavailable`), so the held-out judge averages rest on 33 of the 46 runs that were not refusals.
4. **Expectation differences, not defects.** In H10 the terminal is offline, and the spec (FR-005) adds a Knowledge troubleshooting step; the held-out expects Support only. H19 asks which benefit card brands are enabled on the terminal, which the simulated tools do not expose. H09 also adds a short receivables-advance explanation (route `support>knowledge:rag` instead of `support`).

Items 1 and 3 are measurement defects in the eval harness. Item 2 is a real coverage limit of the knowledge base. None of them was known at the tag.

## 3. Measurement fixes

Changes only in the eval harness and the workflow: no agent, prompt, tool, dataset or threshold changed.

- **Judge evidence** (`evals/judge.py`): tool results from `trace.observations[].data` enter the evidence block marked `[tool]`; web sources are marked `[web]`, and the rubric says their text is not available, so for time-sensitive facts the judge checks that a value is specific, dated and attributed instead of marking it down for being unverifiable. RAG excerpts are unchanged.
- **Judge budget:** each judgment opens its own request context, so the per-request token budget no longer accumulates across judge calls.
- **Same-run results** (`evals/run.py`): `answer`, `judge_items` and the new `evidence` field now come from the same run. Before, the answer came from the last run and the item verdicts from the first judged run, which differ whenever a case was re-run; a calibration sheet built from those rows would pair an answer with verdicts about another answer.
- **Workflow:** the retrieval eval runs whenever the stack started, even if the answer eval fails its thresholds; the job still fails.
- Three regression tests, each failing before the fix; `uv run pytest`: 147 passed.

Same 32-case dataset, same container built from the tag (`rev 5807c7c`), run locally on 2026-11-26 (finished at 05:52); report and results in [`evals/post-session/`](../evals/post-session/report.md):

| Metric | Tag live eval (GitHub) | After the fix (local) | After the fix (GitHub) |
|---|---|---|---|
| Routing accuracy | 0.931 | 0.931 | 0.931 |
| Correct refusal rate | 1.000 | 1.000 | 1.000 |
| Citation rate | 1.000 | 1.000 | 1.000 |
| Source match | 0.929 | 0.929 | 0.929 |
| Judge correctness | 4.00 | 4.76 | 4.76 |
| Judge groundedness | 3.44 | 4.64 | 4.60 |
| Judge relevance | 4.88 | 4.84 | 4.88 |
| Judge helpfulness | 4.04 | 4.72 | 4.80 |
| API cost per request (USD) | 0.0044 | 0.0050 | 0.0043 |
| Verdict | FAIL | PASS | PASS |

The GitHub column is [Actions run 45787180220](https://github.com/mudell19/getnet-multi-agent-v2/actions/runs/45787180220) (`live-eval.yml` dispatched on `main`, whose application code is still the tag's). Its retrieval step now ran and produced a report identical to the committed `evals/retrieval_report.md`.

The answers are new runs of the same code, so they are not identical, but the change is where the defect was: web cases (`s02`, `s07`) and support cases (`s03`, `s08`) went from groundedness 1 to 5, while RAG cases stayed at 4 or 5. Trade-off: the judge cannot read web pages, so web scores now measure specificity and attribution, not whether today's exchange rate is right; the calibration below measures how far the judge agrees with a person.

The held-out set was not run again: it was used once, and its judge averages in section 2 come from the defective judge. Its code checks (routing, refusals, source match) do not depend on the judge.
