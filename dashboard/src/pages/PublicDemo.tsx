import { useEffect, useRef, useState } from "react";

// Public, no-login demo: chat with the bot like a customer and see how each answer was found.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const REPO = "https://github.com/pamithudulwan892-max/graphrag-whatsapp-bot";

const SUGGESTIONS = [
  "How long is the compressor warranty on the Nila AirCool 12000?",
  "Can I pay for it in instalments?",
  "Which branches with a service centre are open on Sunday?",
  "Is delivery free if I order only a rice cooker to Colombo?",
  "When will the Jaffna branch open?",
];

interface Info { enabled: boolean; company: string; documents: string[]; graph: { nodes: number; edges: number }; llm: string | null }
interface Reply {
  reply: string | null;
  answerable?: boolean;
  kind?: string;
  entities: string[];
  facts: string[];
  sources: { n: number; title: string; page: number | null; snippet: string }[];
  timings?: Record<string, number>;
}
interface Bubble { role: "user" | "bot"; text: string; data?: Reply }

function sessionId(): string {
  try {
    const saved = sessionStorage.getItem("demo-session");
    if (saved) return saved;
    const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem("demo-session", id);
    return id;
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

export default function PublicDemo() {
  const [info, setInfo] = useState<Info | null>(null);
  const [msgs, setMsgs] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [session] = useState(sessionId);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${BASE}/api/public/info`).then((r) => r.json()).then(setInfo).catch(() => setError("The demo server is waking up. Refresh in a minute."));
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setInput("");
    setError("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await fetch(`${BASE}/api/public/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
      if (body.reply) {
        setMsgs((m) => {
          const next = [...m, { role: "bot" as const, text: body.reply, data: body }];
          setSelected(next.length - 1);
          return next;
        });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const shown = selected !== null ? msgs[selected]?.data : undefined;

  return (
    <div className="main" style={{ margin: "0 auto" }}>
      <div className="stack">
        <div>
          <h1>GraphRAG customer-support bot</h1>
          <p className="sub" style={{ marginBottom: 8 }}>
            This bot learned everything it knows from {info?.documents.length ?? "a set of"} documents of {info?.company ?? "a demo company"} (a
            fictional Sri Lankan electronics retailer). It searches them with vector search, keyword search and a knowledge
            graph of {info?.graph.nodes ?? "..."} entities, then answers with sources. The same bot answers customers on WhatsApp.
          </p>
          <div className="row small">
            <a href={REPO} target="_blank" rel="noreferrer">Code and evaluation on GitHub</a>
            <span className="muted">|</span>
            <span className="muted">Built by Pamithu Dulwan</span>
          </div>
        </div>

        {info && !info.enabled && <div className="error">The public demo is turned off right now.</div>}

        <div className="chat-layout">
          <div className="phone">
            <div className="phone-head">{info?.company ?? "Customer support"}<small>Ask anything a customer would ask</small></div>
            <div className="msgs">
              {msgs.length === 0 && (
                <div className="stack" style={{ alignItems: "center", marginTop: 30 }}>
                  <span className="muted">Try one of these, or type your own:</span>
                  {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
                </div>
              )}
              {msgs.map((m, i) => (
                <div
                  key={i}
                  className={`bubble ${m.role === "user" ? "out" : "in"} ${m.data ? "clickable" : ""} ${selected === i ? "selected" : ""}`}
                  onClick={() => m.data && setSelected(i)}
                >
                  {m.text}
                </div>
              ))}
              {busy && <div className="bubble in muted">typing... (the first answer can take up to a minute while the free server wakes up)</div>}
              <div ref={end} />
            </div>
            {error && <div className="error">{error}</div>}
            <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
              <input value={input} maxLength={500} onChange={(e) => setInput(e.target.value)} placeholder="Type a question" />
              <button className="primary" disabled={busy || !input.trim()}>Send</button>
            </form>
          </div>

          <div className="card inspector">
            <h2>How this answer was found</h2>
            {!shown && <div className="empty">Ask a question, then click the bot's reply to see the evidence behind it.</div>}
            {shown && shown.kind !== "rag" && <div className="empty">This was a greeting, so no document search was needed.</div>}
            {shown && shown.kind === "rag" && (
              <div className="stack small">
                <div className="row">
                  <span className={`badge ${shown.answerable ? "ok" : "bad"}`}>{shown.answerable ? "answered from the documents" : "not in the documents"}</span>
                  {shown.timings?.total_ms && <span className="badge">search {Math.round(shown.timings.total_ms)} ms</span>}
                </div>
                {!!shown.entities.length && (
                  <div>
                    <h3>Entities found in the question</h3>
                    <div className="row">{shown.entities.map((e) => <span key={e} className="badge">{e}</span>)}</div>
                  </div>
                )}
                {!!shown.facts.length && (
                  <div>
                    <h3>Knowledge graph facts used</h3>
                    {shown.facts.map((f, i) => <div key={i} className="fact">{f}</div>)}
                  </div>
                )}
                {!!shown.sources.length && (
                  <div>
                    <h3>Sources cited</h3>
                    {shown.sources.map((s) => (
                      <div key={s.n} className="chunk">
                        <div className="meta"><span>[{s.n}] {s.title}{s.page ? ` p.${s.page}` : ""}</span></div>
                        <div className="text">{s.snippet}</div>
                      </div>
                    ))}
                  </div>
                )}
                {!shown.answerable && <p className="muted">When the documents don't contain the answer, the bot says so and offers a human instead of guessing.</p>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
