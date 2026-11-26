# Eval report

## Summary

| Metric | Value |
|---|---|
| routing_accuracy | 0.931 |
| citation_rate | 1.000 |
| source_match | 0.929 |
| refusal_rate | 1.000 |
| correctness | 3.920 |
| groundedness | 3.520 |
| relevance | 4.960 |
| helpfulness | 4.200 |
| pass_rate | 0.906 |
| cases | 32 |
| runs | 41 |

## Results by language

| lang | cases | pass rate | routing accuracy |
|---|---|---|---|
| en | 25 | 0.920 | 0.955 |
| pt | 7 | 0.857 | 0.857 |

## Latency (client-measured, ms)

p50: 5746  p95: 18391

## Cost (USD)

- API cost total: 0.205570
- Judge cost total: 0.178783
- Cost per request (API, 41 runs): 0.005014
- Total (API + judge): 0.384353

## Repetition policy

`1+3`: every case runs once (initial runs); cases with any failed run are re-run (extra runs); a case passes if a majority of its runs pass. Judge runs on every run with an answer; judge averages exclude refusals.

## Thresholds

| metric | value | threshold | verdict |
|---|---|---|---|
| routing_accuracy | 0.931 | 0.9 | PASS |
| refusal_rate | 1.000 | 1.0 | PASS |
| citation_rate | 1.000 | 0.95 | PASS |
| source_match | 0.929 | 0.8 | PASS |
| correctness | 3.920 | 4.0 | FAIL |
| groundedness | 3.520 | 4.0 | FAIL |

**Verdict: FAIL**

## Human adjudication

- `s01`: code fail, judge pass; failed items: none; code failures: ["missing '79,90'", "missing '129,90'"]
- `m02`: code fail, judge pass; failed items: none; code failures: ["route 'support>knowledge:rag' != 'support'"]

## Per-case results

| id | lang | category | expected route | got route | runs ok | pass |
|---|---|---|---|---|---|---|
| s01 | en | scenario | knowledge:rag | knowledge:rag | 1/4 | no |
| s02 | en | scenario | knowledge:web | knowledge:web | 1/1 | yes |
| s03 | en | scenario | support | support | 1/1 | yes |
| s04 | en | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| s05 | en | scenario | support>knowledge:rag | support>knowledge:rag | 1/1 | yes |
| s06 | en | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| s07 | en | scenario | knowledge:web | knowledge:web | 1/1 | yes |
| s08 | en | scenario | support | support | 1/1 | yes |
| s09 | en | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| s10 | en | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| k01 | en | compound | support>knowledge:rag | support>knowledge:rag | 1/1 | yes |
| p01 | pt | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| p04 | pt | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| p06 | pt | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| p09 | pt | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| p10 | pt | scenario | knowledge:rag | knowledge:rag | 1/1 | yes |
| a01 | en | adversarial | refusal | refusal | 1/1 | yes |
| a02 | pt | adversarial | refusal | refusal | 1/1 | yes |
| a03 | en | adversarial | knowledge:rag | refusal | 0/4 | no |
| a04 | en | adversarial | refusal | refusal | 1/1 | yes |
| a05 | en | adversarial | refusal | refusal | 1/1 | yes |
| a06 | en | adversarial | refusal | refusal | 1/1 | yes |
| a07 | en | adversarial | refusal | refusal | 1/1 | yes |
| a08 | en | adversarial | refusal | refusal | 1/1 | yes |
| a09 | en | adversarial | refusal | refusal | 1/1 | yes |
| z01 | en | authorization | - | - | 1/1 | yes |
| z02 | en | authorization | - | - | 1/1 | yes |
| z03 | en | authorization | - | - | 1/1 | yes |
| m01 | en | memory | knowledge:rag | knowledge:rag | 1/1 | yes |
| m02 | pt | memory | support | support>knowledge:rag | 0/4 | no |
| h01 | en | hitl | escalation | escalation | 1/1 | yes |
| h02 | en | hitl | escalation | escalation | 1/1 | yes |
