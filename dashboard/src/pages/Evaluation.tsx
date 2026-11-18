import { useEffect, useState } from "react";
import { api } from "../api";

type ModeResult = Record<string, any> & { rows: any[]; by_type: Record<string, { n: number; context_recall: number | null; accuracy: number | null }> };
interface Report { available: boolean; timestamp?: string; n_questions?: number; llm_model?: string | null; extractor?: string; top_k?: number; modes?: Record<string, ModeResult> }

const METRICS: [string, string, boolean][] = [
  ["context_recall", "Context recall: share of needed facts that were retrieved", true],
  ["full_context_hit", "All needed facts retrieved", true],
  ["answer_accuracy", "Answer accuracy (required facts present)", true],
  ["refusal_accuracy", "Says \"I don't know\" when the answer is not in the documents", true],
  ["faithfulness", "Faithfulness (LLM judge): claims supported by sources", true],
  ["answer_relevance", "Answer relevance (LLM judge)", true],
  ["correctness", "Correctness vs reference (LLM judge)", true],
  ["false_refusals", "Answerable questions wrongly declined (count)", false],
  ["latency_s_median", "Median latency (seconds)", false],
];

export default function Evaluation() {
  const [r, setR] = useState<Report | null>(null);
  const [mode, setMode] = useState("graphrag");
  useEffect(() => { api<Report>("/api/eval/results").then(setR); }, []);
  if (!r) return <div className="empty">Loading...</div>;
  if (!r.available || !r.modes) return (
    <div className="stack">
      <h1>Evaluation</h1>
      <div className="card">No results yet. Run <code>python eval/run_eval.py</code> on the server.</div>
    </div>
  );
  const modes = Object.keys(r.modes);
  const rows = r.modes[mode]?.rows ?? [];
  return (
    <div className="stack">
      <div>
        <h1>Evaluation</h1>
        <p className="sub">
          {r.n_questions} test questions on the sample documents, run {r.timestamp}. Answer model: {r.llm_model ?? "offline"}; graph: {r.extractor}; top_k: {r.top_k}.
        </p>
      </div>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Metric</th>{modes.map((m) => <th key={m} className="num">{m}</th>)}</tr></thead>
          <tbody>
            {METRICS.filter(([k]) => modes.some((m) => r.modes![m][k] != null)).map(([k, label, pct]) => {
              const vals = modes.map((m) => r.modes![m][k] as number | null);
              const best = pct ? Math.max(...vals.map((v) => v ?? -1)) : null;
              return (
                <tr key={k}>
                  <td>{label}</td>
                  {vals.map((v, i) => (
                    <td key={i} className="num" style={v === best && pct ? { fontWeight: 700, color: "var(--accent)" } : undefined}>
                      {v == null ? "-" : pct ? `${Math.round(v * 100)}%` : v}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="card table-wrap">
        <h2>By question type (accuracy)</h2>
        <table>
          <thead><tr><th>Type</th>{modes.map((m) => <th key={m} className="num">{m}</th>)}</tr></thead>
          <tbody>
            {Object.keys(r.modes[modes[0]].by_type).map((t) => (
              <tr key={t}>
                <td>{t} (n={r.modes![modes[0]].by_type[t].n})</td>
                {modes.map((m) => {
                  const v = r.modes![m].by_type[t].accuracy;
                  return <td key={m} className="num">{v == null ? "-" : `${Math.round(v * 100)}%`}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card table-wrap">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Every question</h2>
          <div className="tabs" style={{ margin: 0 }}>
            {modes.map((m) => <button key={m} className={m === mode ? "active" : ""} onClick={() => setMode(m)}>{m}</button>)}
          </div>
        </div>
        <table>
          <thead><tr><th>Question</th><th>Type</th><th>Answer</th><th className="num">Recall</th><th>Result</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.question}</td>
                <td className="small">{row.type}</td>
                <td className="small" style={{ maxWidth: 420, whiteSpace: "pre-wrap" }}>{row.answer}</td>
                <td className="num">{row.context_recall == null ? "-" : `${Math.round(row.context_recall * 100)}%`}</td>
                <td><span className={`badge ${row.answer_correct ? "ok" : "bad"}`}>{row.answer_correct ? "correct" : "wrong"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
