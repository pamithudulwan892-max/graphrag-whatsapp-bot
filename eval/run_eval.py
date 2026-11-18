"""Evaluate retrieval and answers: vector-only RAG vs hybrid vs GraphRAG.

It builds a fresh index from sample_data/, asks every question in qa.jsonl
with each retrieval mode, and reports:

Retrieval (no LLM needed)
- context_recall:   share of the gold facts that appear in the retrieved chunks
- full_context_hit: share of questions where ALL gold facts were retrieved
- context_precision: share of retrieved chunks that contain at least one gold fact

Answers
- answer_accuracy:  answer contains every required fact (keyword check, strict)
- refusal_accuracy: unanswerable questions correctly declined
- false_refusals:   answerable questions the bot wrongly declined
- LLM judge (only with an API key, RAGAS-style, 0-1):
  faithfulness (claims supported by the sources), answer_relevance, correctness vs reference

Usage:
  python eval/run_eval.py                 # uses the LLM if ANTHROPIC_API_KEY is set
  python eval/run_eval.py --offline       # retrieval + extractive answers only
"""

import argparse
import json
import os
import shutil
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

JUDGE_SYSTEM = """You grade a customer-support chatbot's answer. Be strict and literal.
Return scores between 0 and 1:
- faithfulness: share of the answer's factual claims that are directly supported by the SOURCES
  (1.0 if every claim is supported; a refusal with no claims scores 1.0).
- answer_relevance: how directly the answer addresses the QUESTION.
- correctness: agreement with the REFERENCE answer (1.0 same facts, 0.5 partly, 0 wrong or missing)."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "faithfulness": {"type": "number"},
        "answer_relevance": {"type": "number"},
        "correctness": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["faithfulness", "answer_relevance", "correctness", "reason"],
    "additionalProperties": False,
}


def norm(s: str) -> str:
    return " ".join(s.lower().replace("–", "-").split())


def load_qa(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_services(offline: bool, data_dir: Path, reuse: bool = False):
    if data_dir.exists() and not reuse:
        shutil.rmtree(data_dir)
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["SEED_SAMPLE_DOCS"] = "false"
    if offline:
        os.environ["LLM_OFFLINE"] = "true"
    from app.config import get_settings
    from app.main import _ingest_file
    from app.services import Services

    get_settings.cache_clear()
    svc = Services(get_settings())
    t0 = time.perf_counter()
    if reuse and svc.db.list_documents():
        print(f"  reusing index in {data_dir}")
        return svc
    for p in sorted((ROOT / "sample_data").iterdir()):
        if p.is_dir():
            continue
        r = _ingest_file(svc, p.name, p.read_bytes())
        print(f"  ingested {p.name}: {r}")
    print(f"  index built in {time.perf_counter() - t0:.1f}s, graph: {svc.graph.stats()['nodes']} nodes / {svc.graph.stats()['edges']} edges")
    return svc


def judge(svc, q: dict, answer_text: str, context: str) -> dict | None:
    if not svc.llm.enabled:
        return None
    user = f"QUESTION: {q['question']}\n\nREFERENCE: {q['reference']}\n\nSOURCES:\n{context}\n\nANSWER: {answer_text}"
    try:
        return svc.llm.json(JUDGE_SYSTEM, user, JUDGE_SCHEMA, effort="low", max_tokens=2000)
    except Exception as e:
        print("    judge failed:", e)
        return None


def evaluate(svc, qa: list[dict], mode: str, use_judge: bool = True) -> dict:
    from app.answer import Answerer

    rows = []
    for q in qa:
        t0 = time.perf_counter()
        out = svc.ask(q["question"], [], mode)
        latency = time.perf_counter() - t0
        ans, res = out["answer"], out["retrieval"]
        ctx = norm(" ".join(c.text for c in res.chunks))
        facts = [norm(f) for f in q.get("context_facts", [])]
        found = [f for f in facts if f in ctx]
        precision = (
            sum(1 for c in res.chunks if any(f in norm(c.text) for f in facts)) / len(res.chunks)
            if facts and res.chunks else None
        )
        a = norm(ans.text)
        unans = q.get("unanswerable", False)
        if unans:
            correct = not ans.answerable
        else:
            correct = ans.answerable and all(any(norm(alt) in a for alt in group) for group in q["answer_facts"])
        sources, fact_lines = Answerer.build_sources(res)
        j = judge(svc, q, ans.text, Answerer.render_context(sources, fact_lines)) if use_judge else None
        rows.append({
            "id": q["id"], "type": q["type"], "question": q["question"], "answer": ans.text,
            "answerable": ans.answerable, "unanswerable": unans,
            "context_recall": (len(found) / len(facts)) if facts else None,
            "full_context_hit": (len(found) == len(facts)) if facts else None,
            "context_precision": precision,
            "answer_correct": correct,
            "latency_s": round(latency, 2),
            "judge": j,
            "retrieved": [c.id for c in res.chunks],
        })
        mark = "ok " if correct else "BAD"
        print(f"  [{mode:8}] {mark} {q['id']} recall={rows[-1]['context_recall']} {ans.text[:70]!r}")
    return summarize(rows) | {"rows": rows}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 3) if xs else None


def summarize(rows: list[dict]) -> dict:
    answerable = [r for r in rows if not r["unanswerable"]]
    unans = [r for r in rows if r["unanswerable"]]
    out = {
        "context_recall": mean([r["context_recall"] for r in answerable]),
        "full_context_hit": mean([float(r["full_context_hit"]) for r in answerable]),
        "context_precision": mean([r["context_precision"] for r in answerable]),
        "answer_accuracy": mean([float(r["answer_correct"]) for r in answerable]),
        "refusal_accuracy": mean([float(r["answer_correct"]) for r in unans]),
        "false_refusals": sum(1 for r in answerable if not r["answerable"]),
        "latency_s_median": round(statistics.median(r["latency_s"] for r in rows), 2),
        "by_type": {},
    }
    judged = [r["judge"] for r in rows if r["judge"]]
    if judged:
        for k in ("faithfulness", "answer_relevance", "correctness"):
            out[k] = mean([j[k] for j in judged])
    for t in sorted({r["type"] for r in rows}):
        sub = [r for r in rows if r["type"] == t]
        out["by_type"][t] = {
            "n": len(sub),
            "context_recall": mean([r["context_recall"] for r in sub]),
            "accuracy": mean([float(r["answer_correct"]) for r in sub]),
        }
        if judged:
            out["by_type"][t]["correctness"] = mean([r["judge"]["correctness"] for r in sub if r["judge"]])
    return out


def to_markdown(report: dict) -> str:
    modes = report["modes"]
    metrics = ["context_recall", "full_context_hit", "context_precision", "answer_accuracy", "refusal_accuracy",
               "false_refusals", "faithfulness", "answer_relevance", "correctness", "latency_s_median"]
    lines = [f"# Evaluation results ({report['timestamp']})", "",
             f"Questions: {report['n_questions']} | LLM: {report['llm_model'] or 'offline (extractive answers)'} | "
             f"Graph extractor: {report['extractor']} | top_k: {report.get('top_k')}", "",
             "| Metric | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for m in metrics:
        vals = [modes[k].get(m) for k in modes]
        if all(v is None for v in vals):
            continue
        lines.append(f"| {m} | " + " | ".join("-" if v is None else str(v) for v in vals) + " |")
    lines += ["", "## By question type (context recall / keyword accuracy)", "",
              "| Type | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    types = next(iter(modes.values()))["by_type"].keys()
    for t in types:
        cells = []
        for k in modes:
            bt = modes[k]["by_type"][t]
            cells.append(f"{bt['context_recall']} / {bt['accuracy']}")
        lines.append(f"| {t} (n={modes[next(iter(modes))]['by_type'][t]['n']}) | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="do not call the LLM")
    ap.add_argument("--modes", default="vector,hybrid,graphrag")
    ap.add_argument("--tag", default="", help="suffix for the results file name")
    ap.add_argument("--judge-modes", default="vector,graphrag", help="modes scored by the LLM judge (saves free-tier quota)")
    ap.add_argument("--reuse-index", action="store_true", help="reuse eval/.data instead of rebuilding (no extraction calls)")
    ap.add_argument("--retrieval-only", action="store_true", help="only measure retrieval (no answer or judge calls)")
    ap.add_argument("--k", type=int, default=None, help="chunks retrieved per question (default: TOP_K setting)")
    args = ap.parse_args()

    qa = load_qa(ROOT / "eval" / "qa.jsonl")
    if args.k:
        os.environ["TOP_K"] = str(args.k)
    print(f"Building index ({'offline' if args.offline else 'LLM if key set'})...")
    if args.retrieval_only:
        os.environ["LLM_OFFLINE"] = "true"
    svc = build_services(args.offline or args.retrieval_only, ROOT / "eval" / ".data", args.reuse_index)
    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_questions": len(qa),
        "llm_model": svc.settings.llm_model if svc.llm.enabled else None,
        "extractor": svc.extractor.name,
        "top_k": svc.settings.top_k,
        "modes": {},
    }
    for mode in args.modes.split(","):
        print(f"\nMode: {mode}")
        report["modes"][mode] = evaluate(svc, qa, mode, mode in args.judge_modes.split(","))
    report["llm_usage"] = svc.llm.usage

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    name = "offline" if not svc.llm.enabled else "llm"
    name += f"-{args.tag}" if args.tag else ""
    (out_dir / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / f"{name}.md").write_text(to_markdown(report), encoding="utf-8")
    shutil.copy(out_dir / f"{name}.json", out_dir / "latest.json")
    print("\n" + to_markdown(report))
    print(f"Saved eval/results/{name}.json and .md")


if __name__ == "__main__":
    main()
