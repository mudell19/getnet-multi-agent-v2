# Judge agreement with a second annotator (dataset)

Annotator: Claude Opus 5.5 (Anthropic), not a person and not the Gemini family of the judge, labeling blind to the judge verdicts. Written by `evals/calibrate.py report`, whose column and wording say "human". Judge: post-fix judge. Answers: evals/post-session/results.jsonl.

- Labeled items: 49
- Agreement rate: 0.980
- Cohen's kappa: 0.657

## Disagreements

- `s01` / invents prices: judge pass, annotator fail
