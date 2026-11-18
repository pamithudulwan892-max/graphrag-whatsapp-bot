# Evaluation results (2026-11-18 07:42 UTC)

Questions: 30 | LLM: offline (extractive answers) | Graph extractor: heuristic | top_k: 6

| Metric | vector | hybrid | graphrag |
|---|---|---|---|
| context_recall | 0.962 | 0.962 | 0.981 |
| full_context_hit | 0.923 | 0.923 | 0.962 |
| context_precision | 0.237 | 0.244 | 0.25 |
| answer_accuracy | 0.462 | 0.462 | 0.5 |
| refusal_accuracy | 0.5 | 0.5 | 0.5 |
| false_refusals | 3 | 3 | 3 |
| latency_s_median | 0.04 | 0.61 | 0.62 |

## By question type (context recall / keyword accuracy)

| Type | vector | hybrid | graphrag |
|---|---|---|---|
| multi-hop (n=13) | 0.923 / 0.308 | 0.923 / 0.308 | 0.962 / 0.308 |
| single-hop (n=13) | 1.0 / 0.615 | 1.0 / 0.615 | 1.0 / 0.692 |
| unanswerable (n=4) | None / 0.5 | None / 0.5 | None / 0.5 |
