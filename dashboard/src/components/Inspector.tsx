import type { Debug } from "../api";

// Shows how an answer was produced: rewritten question, linked entities, graph facts and retrieved chunks.
export default function Inspector({ debug }: { debug: Debug | null }) {
  if (!debug) return <div className="empty">Click a bot reply to see how it was answered.</div>;
  if (debug.kind !== "rag") return <div className="empty">This reply was a {debug.kind} message (no document search).</div>;
  const cited = new Set((debug.citations ?? []).map((c) => c.chunk_id));
  return (
    <div className="stack small">
      <div className="row">
        <span className={`badge ${debug.answerable ? "ok" : "bad"}`}>{debug.answerable ? "answered from documents" : "not in documents"}</span>
        {debug.needs_human && <span className="badge warn">human handover offered</span>}
        <span className="badge">{debug.mode}</span>
        <span className="badge">{debug.llm ? "LLM answer" : "offline answer"}</span>
      </div>
      {debug.standalone_question && (
        <div><div className="muted">Search question</div>{debug.standalone_question}</div>
      )}
      {debug.timings && (
        <div className="muted">
          {Object.entries(debug.timings).map(([k, v]) => `${k.replace("_ms", "")}: ${v} ms`).join(" | ")}
        </div>
      )}
      {!!debug.seeds?.length && (
        <div>
          <h3>Linked entities</h3>
          <div className="row">{debug.seeds.map((s) => <span key={s.name} className="badge">{s.name} <span className="muted">({s.type})</span></span>)}</div>
        </div>
      )}
      {!!debug.facts?.length && (
        <div>
          <h3>Graph facts used</h3>
          {debug.facts.map((f, i) => <div key={i} className="fact">{f}</div>)}
        </div>
      )}
      <div>
        <h3>Retrieved chunks</h3>
        {(debug.chunks ?? []).map((c, i) => (
          <div key={c.id} className="chunk" style={cited.has(c.id) ? { borderColor: "var(--accent)" } : undefined}>
            <div className="meta">
              <span>[{i + 1}] {c.title}{c.page ? ` p.${c.page}` : ""}{cited.has(c.id) ? " (cited)" : ""}</span>
              <span>{c.found_by.join(" + ")} | {c.score}</span>
            </div>
            <div className="text">{c.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
