# Evaluation results (2026-11-18 06:42 UTC)

Questions: 30 | LLM: offline (extractive answers) | Graph extractor: heuristic | top_k: 4

| Metric | vector | hybrid | graphrag |
|---|---|---|---|
| context_recall | 0.94 | 0.94 | 0.94 |
| full_context_hit | 0.88 | 0.88 | 0.88 |
| context_precision | 0.35 | 0.35 | 0.34 |
| answer_accuracy | 0.48 | 0.48 | 0.52 |
| refusal_accuracy | 0.6 | 0.6 | 0.6 |
| false_refusals | 2 | 2 | 2 |
| latency_s_median | 0.04 | 0.65 | 0.62 |

## By question type (context recall / keyword accuracy)

| Type | vector | hybrid | graphrag |
|---|---|---|---|
| multi-hop (n=13) | 0.885 / 0.308 | 0.885 / 0.308 | 0.885 / 0.308 |
| single-hop (n=12) | 1.0 / 0.667 | 1.0 / 0.667 | 1.0 / 0.75 |
| unanswerable (n=5) | None / 0.6 | None / 0.6 | None / 0.6 |
