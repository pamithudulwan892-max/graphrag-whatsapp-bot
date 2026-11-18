import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ApiError, api, getKey, setKey, type Status } from "./api";
import Overview from "./pages/Overview";
import Documents from "./pages/Documents";
import GraphView from "./pages/GraphView";
import TestChat from "./pages/TestChat";
import Conversations from "./pages/Conversations";
import Unanswered from "./pages/Unanswered";
import Outbox from "./pages/Outbox";
import Evaluation from "./pages/Evaluation";
import PublicDemo from "./pages/PublicDemo";

function Login({ onDone }: { onDone: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setKey(value.trim());
    try {
      await api("/api/status");
      onDone();
    } catch (err) {
      setKey("");
      setError(err instanceof ApiError && err.status === 401 ? "That admin key is not correct." : `Cannot reach the API: ${(err as Error).message}`);
    }
  };
  return (
    <div className="login card">
      <h1>Support Bot Admin</h1>
      <p className="sub">Enter the ADMIN_API_KEY from the server's .env file.</p>
      <form onSubmit={submit} className="stack">
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Admin key" autoFocus />
        {error && <div className="error">{error}</div>}
        <button className="primary" type="submit" disabled={!value.trim()}>Sign in</button>
      </form>
      <p className="small muted" style={{ marginTop: 14 }}>Just visiting? <a href="/try">Try the bot without signing in</a>.</p>
    </div>
  );
}

export default function App() {
  // The public demo needs no login.
  if (useLocation().pathname.startsWith("/try")) return <PublicDemo />;
  return <AdminApp />;
}

function AdminApp() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api<Status>("/api/status"));
      setAuthed(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setAuthed(false);
      else setAuthed((a) => (a === null ? false : a));
    }
  }, []);

  useEffect(() => {
    if (!getKey()) {
      setAuthed(false);
      return;
    }
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, [refresh, authed]);

  if (authed === null) return <div className="empty">Loading...</div>;
  if (!authed) return <Login onDone={() => { setAuthed(true); refresh(); }} />;

  const links: [string, string, number?][] = [
    ["/", "Overview"],
    ["/documents", "Documents"],
    ["/graph", "Knowledge graph"],
    ["/chat", "Test chat"],
    ["/conversations", "Conversations", status?.handovers_active || undefined],
    ["/unanswered", "Unanswered", status?.unanswered_open || undefined],
    ["/outbox", "Outbox"],
    ["/evaluation", "Evaluation"],
  ];

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          {status?.company ?? "Support Bot"}
          <small>GraphRAG WhatsApp assistant</small>
        </div>
        <nav className="nav">
          {links.map(([to, label, count]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <span>{label}</span>
              {count ? <span className="count">{count}</span> : null}
            </NavLink>
          ))}
        </nav>
        <div className="spacer" />
        <div className="foot small muted" style={{ padding: "0 10px" }}>
          {status && (
            <>
              <div>LLM: {status.llm_enabled ? status.llm_model : "offline mode"}</div>
              <div>WhatsApp: {status.whatsapp_provider}{status.whatsapp_dry_run ? " (dry run)" : ""}</div>
            </>
          )}
          <button style={{ marginTop: 10 }} onClick={() => { setKey(""); setAuthed(false); }}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview status={status} />} />
          <Route path="/documents" element={<Documents onChange={refresh} />} />
          <Route path="/graph" element={<GraphView />} />
          <Route path="/chat" element={<TestChat />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/unanswered" element={<Unanswered onChange={refresh} />} />
          <Route path="/outbox" element={<Outbox />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
