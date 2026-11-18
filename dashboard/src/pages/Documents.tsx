import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api, del, fmtTime, post, type Doc } from "../api";

type Tab = "file" | "url" | "text";

export default function Documents({ onChange }: { onChange: () => void }) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [tab, setTab] = useState<Tab>("file");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [chunks, setChunks] = useState<{ id: string; text: string; section: string | null; page: number | null }[]>([]);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await api<Doc[]>("/api/documents"));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while something is still processing.
  useEffect(() => {
    if (!docs.some((d) => d.status === "processing")) return;
    const t = setInterval(() => { load(); onChange(); }, 2000);
    return () => clearInterval(t);
  }, [docs, load, onChange]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const upload = (files: FileList | null) => {
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    run(() => post("/api/documents/upload", fd));
  };

  const showChunks = async (id: string) => {
    if (open === id) return setOpen(null);
    setOpen(id);
    setChunks(await api(`/api/documents/${id}/chunks`));
  };

  return (
    <div className="stack">
      <div>
        <h1>Documents</h1>
        <p className="sub">Everything the bot knows comes from these documents. Add product lists, price lists, policies, FAQs or web pages.</p>
      </div>

      <div className="card">
        <div className="tabs">
          <button className={tab === "file" ? "active" : ""} onClick={() => setTab("file")}>Upload files</button>
          <button className={tab === "url" ? "active" : ""} onClick={() => setTab("url")}>Web page</button>
          <button className={tab === "text" ? "active" : ""} onClick={() => setTab("text")}>Paste text / FAQ</button>
        </div>

        {tab === "file" && (
          <div
            className={`dropzone ${over ? "over" : ""}`}
            onClick={() => input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}
          >
            <strong>Drop files here or click to choose</strong>
            <div className="small">PDF, DOCX, TXT, MD or HTML, up to 20 MB each</div>
            <input ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md,.html,.htm" onChange={(e) => { upload(e.target.files); e.target.value = ""; }} />
          </div>
        )}

        {tab === "url" && (
          <form className="row" onSubmit={(e) => { e.preventDefault(); run(() => post("/api/documents/url", { url })).then(() => setUrl("")); }}>
            <input style={{ flex: 1, minWidth: 220 }} placeholder="https://yourcompany.com/faq" value={url} onChange={(e) => setUrl(e.target.value)} />
            <button className="primary" disabled={busy || !url}>Add page</button>
          </form>
        )}

        {tab === "text" && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); run(() => post("/api/documents/text", { title, text })).then(() => { setTitle(""); setText(""); }); }}>
            <input placeholder="Title, e.g. Delivery FAQ" value={title} onChange={(e) => setTitle(e.target.value)} />
            <textarea placeholder={"Q: Do you deliver on Sundays?\nA: No, deliveries are Monday to Saturday."} value={text} onChange={(e) => setText(e.target.value)} />
            <div><button className="primary" disabled={busy || !title || text.length < 10}>Add text</button></div>
          </form>
        )}
        {error && <div className="error" style={{ marginTop: 10 }}>{error}</div>}
      </div>

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Library ({docs.length})</h2>
          <button disabled={busy || !docs.length} onClick={() => confirm("Rebuild the index and knowledge graph for every document? Use this after adding an LLM API key.") && run(() => post("/api/reindex"))}>
            Rebuild all
          </button>
        </div>
        {docs.length === 0 ? (
          <div className="empty">No documents yet.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Title</th><th>Type</th><th>Status</th><th className="num">Chunks</th><th className="num">Entities</th><th className="num">Relations</th><th>Added</th><th /></tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <Fragment key={d.id}>
                    <tr>
                      <td><a href="#" onClick={(e) => { e.preventDefault(); showChunks(d.id); }}>{d.title}</a><div className="small muted">{d.source}</div></td>
                      <td><span className="badge">{d.kind}</span></td>
                      <td>
                        <span className={`badge ${d.status === "ready" ? "ok" : d.status === "failed" ? "bad" : "warn"}`}>{d.status}</span>
                        {d.error && <div className="small" style={{ color: "var(--danger)" }}>{d.error}</div>}
                      </td>
                      <td className="num">{d.n_chunks}</td>
                      <td className="num">{d.n_entities}</td>
                      <td className="num">{d.n_relations}</td>
                      <td className="small muted">{fmtTime(d.created_at)}</td>
                      <td><button className="danger" disabled={busy} onClick={() => confirm(`Delete "${d.title}"? The bot will forget it.`) && run(() => del(`/api/documents/${d.id}`))}>Delete</button></td>
                    </tr>
                    {open === d.id && (
                      <tr>
                        <td colSpan={8}>
                          {chunks.map((c) => (
                            <div key={c.id} className="chunk">
                              <div className="meta"><span>{c.section ?? "-"}</span><span>{c.page ? `page ${c.page}` : ""} {c.id}</span></div>
                              <div className="text">{c.text}</div>
                            </div>
                          ))}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
