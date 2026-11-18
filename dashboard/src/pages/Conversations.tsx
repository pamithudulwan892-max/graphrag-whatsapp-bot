import { useCallback, useEffect, useState } from "react";
import { api, fmtTime, post, type Debug, type Message } from "../api";
import Inspector from "../components/Inspector";

interface Convo { phone: string; channel: string; n_messages: number; last_at: number; last_text: string; handover: boolean }

export default function Conversations() {
  const [list, setList] = useState<Convo[]>([]);
  const [phone, setPhone] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [handover, setHandover] = useState(false);
  const [debug, setDebug] = useState<Debug | null>(null);
  const [reply, setReply] = useState("");

  const loadList = useCallback(() => api<Convo[]>("/api/conversations").then(setList), []);
  const loadConvo = useCallback(async (p: string) => {
    const r = await api<{ messages: Message[]; handover: boolean }>(`/api/conversations/${encodeURIComponent(p)}`);
    setMsgs(r.messages);
    setHandover(r.handover);
  }, []);

  useEffect(() => {
    loadList();
    const t = setInterval(loadList, 8000);
    return () => clearInterval(t);
  }, [loadList]);

  useEffect(() => {
    if (!phone) return;
    loadConvo(phone);
    const t = setInterval(() => loadConvo(phone), 5000);
    return () => clearInterval(t);
  }, [phone, loadConvo]);

  const sendReply = async () => {
    if (!phone || !reply.trim()) return;
    await post(`/api/conversations/${encodeURIComponent(phone)}/reply`, { text: reply });
    setReply("");
    loadConvo(phone);
  };

  const toggleHandover = async () => {
    if (!phone) return;
    await post(`/api/conversations/${encodeURIComponent(phone)}/handover`, { active: !handover });
    loadConvo(phone);
    loadList();
  };

  return (
    <div className="stack">
      <div>
        <h1>Conversations</h1>
        <p className="sub">Every customer chat, grouped by phone number. When a customer asks for a human, the bot stops replying and you can answer here.</p>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(240px, 300px) minmax(0, 1fr)" }}>
        <div className="card" style={{ padding: 0, maxHeight: 660, overflowY: "auto" }}>
          {list.length === 0 && <div className="empty">No conversations yet.</div>}
          {list.map((c) => (
            <div
              key={c.phone}
              onClick={() => { setPhone(c.phone); setDebug(null); }}
              style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", cursor: "pointer", background: phone === c.phone ? "var(--accent-soft)" : undefined }}
            >
              <div className="row between">
                <strong>{c.phone}</strong>
                {c.handover && <span className="badge warn">human</span>}
              </div>
              <div className="small muted" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last_text}</div>
              <div className="small muted">{c.n_messages} messages | {fmtTime(c.last_at)} | {c.channel}</div>
            </div>
          ))}
        </div>
        {phone ? (
          <div className="chat-layout">
            <div className="phone">
              <div className="phone-head row between">
                <span>{phone}<small>{handover ? "A human agent is handling this chat" : "Bot is replying"}</small></span>
                <button onClick={toggleHandover}>{handover ? "Give back to bot" : "Take over"}</button>
              </div>
              <div className="msgs">
                {msgs.map((m) => (
                  <div
                    key={m.id}
                    className={`bubble ${m.role === "user" ? "in" : m.role === "agent" ? "agent" : "out"} ${m.meta?.kind ? "clickable" : ""}`}
                    onClick={() => m.meta?.kind && setDebug(m.meta)}
                  >
                    {m.role === "agent" && <div className="small muted">Agent</div>}
                    {m.text}
                    <span className="time">{fmtTime(m.created_at)}</span>
                  </div>
                ))}
              </div>
              <form className="composer" onSubmit={(e) => { e.preventDefault(); sendReply(); }}>
                <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply as a human agent" />
                <button className="primary" disabled={!reply.trim()}>Send</button>
              </form>
            </div>
            <div className="card inspector"><h2>How this was answered</h2><Inspector debug={debug} /></div>
          </div>
        ) : (
          <div className="card empty">Choose a conversation.</div>
        )}
      </div>
    </div>
  );
}
