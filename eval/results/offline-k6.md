# Evaluation results (2026-11-18 06:43 UTC)

Questions: 30 | LLM: offline (extractive answers) | Graph extractor: heuristic | top_k: 6

| Metric | vector | hybrid | graphrag |
|---|---|---|---|
| context_recall | 0.96 | 0.94 | 0.96 |
| full_context_hit | 0.92 | 0.88 | 0.92 |
| context_precision | 0.24 | 0.24 | 0.247 |
| answer_accuracy | 0.48 | 0.48 | 0.52 |
| refusal_accuracy | 0.6 | 0.6 | 0.6 |
| false_refusals | 2 | 2 | 2 |
| latency_s_median | 0.06 | 0.64 | 0.65 |

## By question type (context recall / keyword accuracy)

| Type | vector | hybrid | graphrag |
|---|---|---|---|
| multi-hop (n=13) | 0.923 / 0.308 | 0.885 / 0.308 | 0.923 / 0.308 |
| single-hop (n=12) | 1.0 / 0.667 | 1.0 / 0.667 | 1.0 / 0.75 |
| unanswerable (n=5) | None / 0.6 | None / 0.6 | None / 0.6 |
