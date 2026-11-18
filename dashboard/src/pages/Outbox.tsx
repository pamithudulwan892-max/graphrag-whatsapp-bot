import { useEffect, useState } from "react";
import { api, fmtTime } from "../api";

interface Row { id: number; provider: string; to_number: string; text: string; status: string; detail: string; created_at: number }

export default function Outbox() {
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => {
    const load = () => api<Row[]>("/api/outbox").then(setRows);
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="stack">
      <div>
        <h1>Outbox</h1>
        <p className="sub">Every WhatsApp message the bot sent (or, in dry-run mode, would have sent).</p>
      </div>
      <div className="card table-wrap">
        {rows.length === 0 ? <div className="empty">No outgoing messages yet.</div> : (
          <table>
            <thead><tr><th>To</th><th>Message</th><th>Status</th><th>Provider</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="small">{r.to_number}</td>
                  <td style={{ whiteSpace: "pre-wrap", maxWidth: 520 }}>{r.text}</td>
                  <td>
                    <span className={`badge ${r.status === "sent" ? "ok" : r.status === "failed" ? "bad" : "warn"}`}>{r.status}</span>
                    {r.detail && <div className="small" style={{ color: "var(--danger)" }}>{r.detail}</div>}
                  </td>
                  <td>{r.provider}</td>
                  <td className="small muted">{fmtTime(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
