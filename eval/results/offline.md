# Evaluation results (2026-11-18 06:32 UTC)

Questions: 30 | LLM: offline (extractive answers) | Graph extractor: heuristic

| Metric | vector | hybrid | graphrag |
|---|---|---|---|
| context_recall | 0.98 | 0.98 | 0.98 |
| full_context_hit | 0.96 | 0.96 | 0.96 |
| context_precision | 0.253 | 0.253 | 0.253 |
| answer_accuracy | 0.44 | 0.48 | 0.56 |
| refusal_accuracy | 0.6 | 0.6 | 0.6 |
| false_refusals | 3 | 2 | 2 |
| latency_s_median | 0.05 | 0.99 | 3.66 |

## By question type (context recall / keyword accuracy)

| Type | vector | hybrid | graphrag |
|---|---|---|---|
| multi-hop (n=13) | 0.962 / 0.231 | 0.962 / 0.308 | 0.962 / 0.385 |
| single-hop (n=12) | 1.0 / 0.667 | 1.0 / 0.667 | 1.0 / 0.75 |
| unanswerable (n=5) | None / 0.6 | None / 0.6 | None / 0.6 |
