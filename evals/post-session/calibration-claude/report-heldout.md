# Judge agreement with a second annotator (heldout)

Annotator: Claude Opus 5.5 (Anthropic), not a person and not the Gemini family of the judge, labeling blind to the judge verdicts. Written by `evals/calibrate.py report`, whose column and wording say "human". Judge: tag judge (before the fix). Answers: evals/heldout/results.jsonl, single-run cases only.

- Labeled items: 10
- Agreement rate: 0.600
- Cohen's kappa: 0.200

## Disagreements

- `H07` / consulta a web e informa a taxa Selic vigente: judge fail, annotator pass
- `H07` / informar taxa de memória sem consulta: judge fail, annotator pass
- `H11` / lists last Saturday's transactions from the lookup filtered to amounts above R$300: judge fail, annotator pass
- `H11` / invent transactions or amounts: judge fail, annotator pass
