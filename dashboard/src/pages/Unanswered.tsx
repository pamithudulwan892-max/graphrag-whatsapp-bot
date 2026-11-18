import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtTime, post } from "../api";

interface Item { id: number; phone: string; question: string; reason: string; resolved: number; created_at: number }

export default function Unanswered({ onChange }: { onChange: () => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const load = useCallback(() => api<Item[]>("/api/unanswered").then(setItems), []);
  useEffect(() => { load(); }, [load]);

  const resolve = async (id: number) => {
    await post(`/api/unanswered/${id}/resolve`);
    load();
    onChange();
  };

  return (
    <div className="stack">
      <div>
        <h1>Unanswered questions</h1>
        <p className="sub">Questions the bot could not answer from your documents, or where the customer asked for a person. Add the missing information as a document, then mark the question resolved.</p>
      </div>
      <div className="card table-wrap">
        {items.length === 0 ? <div className="empty">Nothing here. The bot has answered everything so far.</div> : (
          <table>
            <thead><tr><th>Question</th><th>Reason</th><th>Customer</th><th>When</th><th /></tr></thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} style={i.resolved ? { opacity: 0.5 } : undefined}>
                  <td>{i.question}</td>
                  <td><span className={`badge ${i.reason.includes("human") ? "warn" : "bad"}`}>{i.reason}</span></td>
                  <td className="small">{i.phone}</td>
                  <td className="small muted">{fmtTime(i.created_at)}</td>
                  <td className="row">
                    {!i.resolved && <Link to="/documents"><button>Add answer</button></Link>}
                    {!i.resolved ? <button onClick={() => resolve(i.id)}>Mark resolved</button> : <span className="badge ok">resolved</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
