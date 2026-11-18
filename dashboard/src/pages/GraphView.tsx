import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { api, type GraphData } from "../api";

const PALETTE = ["#0f7b6c", "#2f6fdf", "#c2410c", "#7c3aed", "#b42318", "#0e7490", "#a16207", "#be185d", "#4d7c0f", "#475569"];

interface NodeDetail {
  id: string;
  name: string;
  type: string;
  descriptions: string[];
  edges: { source: string; target: string; relation: string; description: string }[];
}

export default function GraphView() {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [error, setError] = useState("");
  const wrap = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 640 });

  useEffect(() => {
    const qs = query ? `?search=${encodeURIComponent(query)}` : "";
    api<GraphData>(`/api/graph${qs}`).then(setData).catch((e) => setError(e.message));
  }, [query]);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const colors = useMemo(() => {
    const types = [...new Set(data.nodes.map((n) => n.type))].sort();
    return Object.fromEntries(types.map((t, i) => [t, PALETTE[i % PALETTE.length]]));
  }, [data]);

  // react-force-graph mutates the objects it is given, so hand it a copy.
  const graph = useMemo(() => ({ nodes: data.nodes.map((n) => ({ ...n })), links: data.links.map((l) => ({ ...l })) }), [data]);

  const openNode = async (id: string) => {
    try {
      setDetail(await api<NodeDetail>(`/api/graph/node/${encodeURIComponent(id)}`));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="stack">
      <div>
        <h1>Knowledge graph</h1>
        <p className="sub">Entities and relationships extracted from your documents. The bot walks these links to answer questions that need facts from more than one place.</p>
      </div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); setQuery(search.trim()); }}>
        <input style={{ flex: 1, minWidth: 200 }} placeholder="Find an entity, e.g. AirCool or Galle" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button className="primary">Search</button>
        {query && <button type="button" onClick={() => { setSearch(""); setQuery(""); }}>Show all</button>}
        <span className="muted small">{data.nodes.length} entities, {data.links.length} relations shown</span>
      </form>
      {error && <div className="error">{error}</div>}
      <div className="legend">
        {Object.entries(colors).map(([t, c]) => (
          <span key={t}><span className="dot" style={{ background: c }} />{t}</span>
        ))}
      </div>
      <div className="graph-wrap" ref={wrap}>
        {data.nodes.length === 0 ? (
          <div className="empty">No entities yet. Upload documents first.</div>
        ) : (
          <ForceGraph2D
            graphData={graph}
            width={size.w}
            height={size.h}
            nodeId="id"
            nodeLabel={(n: any) => `${n.name} (${n.type})`}
            nodeVal={(n: any) => 1 + Math.sqrt(n.degree)}
            nodeColor={(n: any) => colors[n.type] ?? "#888"}
            linkLabel={(l: any) => l.relation}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkColor={() => "rgba(120,130,145,0.35)"}
            cooldownTicks={120}
            onNodeClick={(n: any) => openNode(n.id)}
            nodeCanvasObjectMode={() => "after"}
            nodeCanvasObject={(n: any, ctx, scale) => {
              if (scale < 1.6 && n.degree < 6) return;
              const fontSize = 11 / scale;
              ctx.font = `${fontSize}px sans-serif`;
              ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--text") || "#333";
              ctx.textAlign = "center";
              ctx.fillText(n.name.length > 28 ? n.name.slice(0, 27) + "..." : n.name, n.x, n.y + 8 / scale + fontSize);
            }}
          />
        )}
        {detail && (
          <div className="card graph-panel">
            <div className="row between">
              <h3 style={{ margin: 0 }}>{detail.name}</h3>
              <button onClick={() => setDetail(null)}>Close</button>
            </div>
            <span className="badge">{detail.type}</span>
            {detail.descriptions.map((d, i) => <p key={i} className="small">{d}</p>)}
            <h3 style={{ marginTop: 10 }}>Relations ({detail.edges.length})</h3>
            {detail.edges.map((e, i) => (
              <div key={i} className="fact">
                <a href="#" onClick={(ev) => { ev.preventDefault(); setSearch(e.source === detail.name ? e.target : e.source); setQuery(e.source === detail.name ? e.target : e.source); }}>
                  {e.source}
                </a>{" "}
                <strong>{e.relation}</strong> {e.target}
                {e.description && <div className="muted">{e.description}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
