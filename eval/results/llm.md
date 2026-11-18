# Evaluation results (2026-11-18 07:23 UTC)

Questions: 30 | LLM: gemini-3.5-flash-lite | Graph extractor: llm | top_k: 6

| Metric | vector | hybrid | graphrag |
|---|---|---|---|
| context_recall | 0.962 | 0.962 | 0.981 |
| full_context_hit | 0.923 | 0.923 | 0.962 |
| context_precision | 0.237 | 0.244 | 0.25 |
| answer_accuracy | 0.923 | 0.923 | 0.962 |
| refusal_accuracy | 1.0 | 1.0 | 1.0 |
| false_refusals | 1 | 2 | 1 |
| faithfulness | 1.0 | - | 1.0 |
| answer_relevance | 0.993 | - | 0.977 |
| correctness | 0.943 | - | 0.95 |
| latency_s_median | 1.46 | 3.9 | 2.56 |

## By question type (context recall / keyword accuracy)

| Type | vector | hybrid | graphrag |
|---|---|---|---|
| multi-hop (n=13) | 0.923 / 0.846 | 0.923 / 0.846 | 0.962 / 0.923 |
| single-hop (n=13) | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |
| unanswerable (n=4) | None / 1.0 | None / 1.0 | None / 1.0 |
