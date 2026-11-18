import { useEffect, useState } from "react";
import { api, fmtTime, post } from "../api";

interface Row { id: number; provider: string; to_number: string; text: string; status: string; detail: string; created_at: number }

function ConnectMeta() {
  const [waba, setWaba] = useState("");
  const [result, setResult] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    setResult("");
    try {
      const r = await post<{ subscribe_status: number; subscribe_response: unknown; subscribed_apps: string[] }>(
        "/api/whatsapp/meta/subscribe", { waba_id: waba.trim() });
      setResult(r.subscribe_status === 200
        ? `Connected. Apps receiving this account's messages: ${r.subscribed_apps.join(", ") || "(none listed)"}`
        : `Meta said: ${JSON.stringify(r.subscribe_response)}`);
    } catch (e) {
      setResult((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="card stack">
      <h2 style={{ margin: 0 }}>Connect Meta WhatsApp account</h2>
      <p className="small muted" style={{ margin: 0 }}>
        If customers' messages never reach the bot, subscribe this app to your WhatsApp Business Account.
        The ID is shown as "Messaging account ID" (WhatsApp Business Account ID) in Meta's API setup page.
      </p>
      <div className="row">
        <input style={{ flex: 1, minWidth: 200 }} placeholder="WhatsApp Business Account ID" value={waba} onChange={(e) => setWaba(e.target.value)} />
        <button className="primary" disabled={busy || !/^\d{5,20}$/.test(waba.trim())} onClick={run}>{busy ? "Connecting..." : "Connect"}</button>
      </div>
      {result && <div className="small">{result}</div>}
    </div>
  );
}

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
      <ConnectMeta />
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
