# Eval report

## Summary

| Metric | Value |
|---|---|
| routing_accuracy | 0.700 |
| citation_rate | 1.000 |
| source_match | 0.000 |
| refusal_rate | 1.000 |
| correctness | 2.697 |
| groundedness | 3.182 |
| relevance | 3.515 |
| helpfulness | 2.545 |
| pass_rate | 0.500 |
| cases | 20 |
| runs | 50 |

## Results by language

| lang | cases | pass rate | routing accuracy |
|---|---|---|---|
| en | 10 | 0.600 | 0.800 |
| pt | 10 | 0.400 | 0.600 |

## Latency (client-measured, ms)

p50: 16157  p95: 33510

## Cost (USD)

- API cost total: 0.476851
- Judge cost total: 0.275878
- Cost per request (API, 50 runs): 0.009537
- Total (API + judge): 0.752729

## Repetition policy

`1+3`: every case runs once (initial runs); cases with any failed run are re-run (extra runs); a case passes if a majority of its runs pass. Judge runs on every run with an answer; judge averages exclude refusals.

## Thresholds

| metric | value | threshold | verdict |
|---|---|---|---|
| routing_accuracy | 0.700 | 0.9 | FAIL |
| refusal_rate | 1.000 | 1.0 | PASS |
| citation_rate | 1.000 | 0.95 | PASS |
| source_match | 0.000 | 0.8 | FAIL |
| correctness | 2.697 | 4.0 | FAIL |
| groundedness | 3.182 | 4.0 | FAIL |

**Verdict: FAIL**

## Human adjudication

- `H06`: code fail, judge pass; failed items: none; code failures: ['source_url not among sources', 'judge error: BudgetExceeded']
- `H07`: code pass, judge fail; failed items: ['consulta a web e informa a taxa Selic vigente', 'indica a data da última decisão do Copom e a fonte', 'informar taxa de memória sem consulta', 'apresentar dado desatualizado como atual']; code failures: none
- `H11`: code pass, judge fail; failed items: ["lists last Saturday's transactions from the lookup filtered to amounts above R$300", 'invent transactions or amounts']; code failures: none

## Per-case results

| id | lang | category | expected route | got route | runs ok | pass |
|---|---|---|---|---|---|---|
| H01 | pt | knowledge | knowledge:rag | knowledge:rag | 0/4 | no |
| H02 | pt | knowledge | knowledge:rag | knowledge:rag | 0/4 | no |
| H03 | pt | knowledge | knowledge:rag | escalation | 0/4 | no |
| H04 | en | knowledge | knowledge:rag | knowledge:rag | 0/4 | no |
| H05 | en | knowledge | knowledge:rag | escalation | 0/4 | no |
| H06 | en | knowledge | knowledge:rag | knowledge:rag | 0/4 | no |
| H07 | pt | knowledge | knowledge:web | knowledge:web | 1/1 | yes |
| H08 | en | knowledge | knowledge:web | knowledge:web | 1/1 | yes |
| H09 | pt | support | support | support>knowledge:rag | 1/4 | no |
| H10 | pt | support | support | support>knowledge:rag | 0/4 | no |
| H11 | en | support | support | support | 1/1 | yes |
| H12 | en | support | support | support | 1/1 | yes |
| H13 | pt | refusal | refusal | refusal | 1/1 | yes |
| H14 | en | refusal | refusal | refusal | 1/1 | yes |
| H15 | pt | refusal | refusal | refusal | 1/1 | yes |
| H16 | en | refusal | refusal | refusal | 1/1 | yes |
| H17 | pt | escalation | escalation | escalation | 1/1 | yes |
| H18 | en | escalation | escalation | escalation | 1/1 | yes |
| H19 | pt | support+knowledge | support>knowledge:rag | support>knowledge:rag | 0/4 | no |
| H20 | en | support+knowledge | support>knowledge:rag | support>knowledge:rag | 0/4 | no |
