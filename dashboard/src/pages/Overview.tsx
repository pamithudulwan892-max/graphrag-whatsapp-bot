import { Link } from "react-router-dom";
import type { Status } from "../api";

export default function Overview({ status }: { status: Status | null }) {
  if (!status) return <div className="empty">Loading...</div>;
  const stats: [string, number | string][] = [
    ["Documents", status.documents],
    ["Chunks indexed", status.chunks],
    ["Graph entities", status.graph.nodes],
    ["Graph relations", status.graph.edges],
    ["Customers", status.conversations],
    ["Messages", status.messages],
    ["Unanswered (open)", status.unanswered_open],
    ["Waiting for a human", status.handovers_active],
  ];
  const types = Object.entries(status.graph.entity_types).slice(0, 10);
  const maxType = Math.max(1, ...types.map(([, n]) => n));

  return (
    <div className="stack">
      <div>
        <h1>Overview</h1>
        <p className="sub">The bot answers customers from the documents you upload, using vector search plus a knowledge graph.</p>
      </div>

      {status.documents === 0 && (
        <div className="card">
          <h2>Get started</h2>
          <p>Upload your company's documents (PDF, Word, text or a web page). The bot reads them, builds a knowledge graph, and can then answer customers on WhatsApp.</p>
          <Link to="/documents"><button className="primary">Upload documents</button></Link>
        </div>
      )}

      <div className="grid stats">
        {stats.map(([label, value]) => (
          <div key={label} className="card stat">
            <div className="label">{label}</div>
            <div className="value">{value}</div>
          </div>
        ))}
      </div>

      <div className="grid two">
        <div className="card">
          <h2>System</h2>
          <table>
            <tbody>
              <tr><td className="muted">Answer model</td><td>{status.llm_enabled ? `${status.llm_model} (${status.llm_provider})` : <span className="badge warn">offline: extractive answers</span>}</td></tr>
              <tr><td className="muted">Graph builder</td><td>{status.extractor === "llm" ? "LLM entity and relation extraction" : "Heuristic (patterns and co-occurrence)"}</td></tr>
              <tr><td className="muted">Embeddings</td><td>{status.embedding_model}</td></tr>
              <tr><td className="muted">Re-ranker</td><td>{status.reranker ?? "off"}</td></tr>
              <tr><td className="muted">WhatsApp</td><td>{status.whatsapp_provider} {status.whatsapp_dry_run && <span className="badge warn">dry run</span>}</td></tr>
              <tr><td className="muted">LLM calls (since start)</td><td>{status.llm_usage.calls} calls, {status.llm_usage.input_tokens.toLocaleString()} in / {status.llm_usage.output_tokens.toLocaleString()} out tokens</td></tr>
            </tbody>
          </table>
        </div>
        <div className="card">
          <h2>Entity types in the graph</h2>
          {types.length === 0 && <div className="muted">No entities yet.</div>}
          <table>
            <tbody>
              {types.map(([t, n]) => (
                <tr key={t}>
                  <td style={{ width: 140 }}>{t}</td>
                  <td><div className="bar"><span style={{ width: `${(n / maxType) * 100}%` }} /></div></td>
                  <td className="num" style={{ width: 50 }}>{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
