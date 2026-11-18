// Small typed client for the backend admin API.

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const KEY_STORAGE = "graphrag-admin-key";

export function getKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setKey(key: string) {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "X-API-Key": getKey() };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });

export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

// --- Types -----------------------------------------------------------------

export interface Status {
  company: string;
  llm_enabled: boolean;
  llm_provider: string | null;
  llm_model: string | null;
  extractor: string;
  embedding_model: string;
  reranker: string | null;
  whatsapp_provider: string;
  whatsapp_dry_run: boolean;
  llm_usage: { calls: number; input_tokens: number; output_tokens: number };
  documents: number;
  chunks: number;
  conversations: number;
  messages: number;
  unanswered_open: number;
  handovers_active: number;
  graph: { nodes: number; edges: number; entity_types: Record<string, number>; relation_types: Record<string, number> };
}

export interface Doc {
  id: string;
  title: string;
  source: string;
  kind: string;
  status: "processing" | "ready" | "failed";
  error: string | null;
  n_chunks: number;
  n_entities: number;
  n_relations: number;
  created_at: number;
}

export interface Citation {
  n: number;
  chunk_id: string;
  title: string;
  section: string | null;
  page: number | null;
  snippet: string;
}

export interface Debug {
  kind: string;
  answerable?: boolean;
  needs_human?: boolean;
  standalone_question?: string;
  citations?: Citation[];
  mode?: string;
  seeds?: { name: string; type: string; score: number }[];
  facts?: string[];
  chunks?: { id: string; title: string; section: string | null; page: number | null; score: number; found_by: string[]; text: string }[];
  timings?: Record<string, number>;
  top_relevance?: number;
  llm?: boolean;
}

export interface Message {
  id: number;
  phone: string;
  role: "user" | "assistant" | "agent";
  text: string;
  channel: string;
  meta: Debug | null;
  created_at: number;
}

export interface GraphData {
  nodes: { id: string; name: string; type: string; description: string; degree: number }[];
  links: { source: string; target: string; relation: string; description: string }[];
}

export const fmtTime = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
