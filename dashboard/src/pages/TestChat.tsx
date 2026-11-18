import { useEffect, useRef, useState } from "react";
import { api, del, post, type Debug, type Message } from "../api";
import Inspector from "../components/Inspector";

const SUGGESTIONS = [
  "Hi",
  "How long is the compressor warranty on the Nila AirCool 12000?",
  "Which branches with a service centre are open on Sunday?",
  "Can I pay for it in instalments?",
  "Do you sell iPhones?",
];

interface Bubble { role: "user" | "assistant" | "agent"; text: string; debug: Debug | null }

export default function TestChat() {
  const [phone] = useState("test-dashboard");
  const [mode, setMode] = useState("graphrag");
  const [msgs, setMsgs] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<{ messages: Message[] }>(`/api/conversations/${phone}`).then((r) =>
      setMsgs(r.messages.map((m) => ({ role: m.role, text: m.text, debug: m.meta }))),
    );
  }, [phone]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const send = async (text: string) => {
    if (!text.trim() || busy) return;
    setInput("");
    setError("");
    setMsgs((m) => [...m, { role: "user", text, debug: null }]);
    setBusy(true);
    try {
      const r = await post<{ reply: string | null; debug: Debug | null }>("/api/chat", { message: text, phone, mode });
      if (r.reply) {
        setMsgs((m) => {
          const next = [...m, { role: "assistant" as const, text: r.reply!, debug: r.debug }];
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

  const reset = async () => {
    await del(`/api/conversations/${phone}`);
    setMsgs([]);
    setSelected(null);
  };

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <h1>Test chat</h1>
          <p className="sub" style={{ marginBottom: 0 }}>Chat exactly like a WhatsApp customer would. Click a reply to see the sources behind it.</p>
        </div>
        <div className="row">
          <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ width: "auto" }} aria-label="Retrieval mode">
            <option value="graphrag">GraphRAG (vector + keyword + graph)</option>
            <option value="hybrid">Hybrid (vector + keyword)</option>
            <option value="vector">Vector only</option>
          </select>
          <button onClick={reset}>New conversation</button>
        </div>
      </div>
      <div className="chat-layout">
        <div className="phone">
          <div className="phone-head">Customer support<small>simulated WhatsApp chat (memory is kept per phone number)</small></div>
          <div className="msgs">
            {msgs.length === 0 && (
              <div className="stack" style={{ alignItems: "center", marginTop: 40 }}>
                <span className="muted">Try one of these:</span>
                {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
              </div>
            )}
            {msgs.map((m, i) => (
              <div
                key={i}
                className={`bubble ${m.role === "user" ? "in" : m.role === "agent" ? "agent" : "out"} ${m.debug ? "clickable" : ""} ${selected === i ? "selected" : ""}`}
                onClick={() => m.debug && setSelected(i)}
              >
                {m.text}
              </div>
            ))}
            {busy && <div className="bubble out muted">typing...</div>}
            <div ref={end} />
          </div>
          {error && <div className="error">{error}</div>}
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type a message" />
            <button className="primary" disabled={busy || !input.trim()}>Send</button>
          </form>
        </div>
        <div className="card inspector">
          <h2>How this was answered</h2>
          <Inspector debug={selected !== null ? msgs[selected]?.debug ?? null : null} />
        </div>
      </div>
    </div>
  );
}
