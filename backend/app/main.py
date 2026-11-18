"""FastAPI application: admin API, WhatsApp webhooks, and the built dashboard."""

import json
import logging
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import whatsapp
from .config import ROOT_DIR, get_settings
from .ingestion.parsers import SUPPORTED, Section, fetch_url, parse_file, parse_markdown
from .retrieval.hybrid import MODES
from .services import Services, answer_to_dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SAMPLE_DIR = ROOT_DIR / "sample_data"
PREBUILT_DIR = SAMPLE_DIR / "prebuilt_index"
DASHBOARD_DIST = ROOT_DIR / "dashboard" / "dist"
EVAL_RESULTS = ROOT_DIR / "eval" / "results" / "latest.json"

services: Services | None = None


def get_services() -> Services:
    if services is None:
        raise HTTPException(503, "Service is starting")
    return services


@asynccontextmanager
async def lifespan(app: FastAPI):
    global services
    settings = get_settings()
    fresh = not (settings.data_dir / "app.db").exists()
    if settings.seed_sample_docs and fresh and PREBUILT_DIR.exists():
        # Free hosts wipe the disk on restart: restore the prebuilt demo index (no LLM calls needed).
        log.info("Restoring prebuilt demo index from %s", PREBUILT_DIR)
        shutil.copytree(PREBUILT_DIR, settings.data_dir, dirs_exist_ok=True)
    services = Services(settings)
    log.info("LLM: %s | extractor: %s", services.llm.model or "offline", services.extractor.name)
    if settings.seed_sample_docs and not services.db.list_documents() and SAMPLE_DIR.exists():
        log.info("Seeding sample documents from %s in the background", SAMPLE_DIR)

        def seed():
            for path in sorted(SAMPLE_DIR.iterdir()):
                if path.suffix.lower() in SUPPORTED:
                    _ingest_file(services, path.name, path.read_bytes())

        threading.Thread(target=seed, daemon=True).start()
    # Load the models and pre-compute entity vectors now, so the first customer does not wait.
    threading.Thread(target=services.warm_up, daemon=True).start()
    yield


app = FastAPI(title="GraphRAG WhatsApp Support Bot", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_admin(x_api_key: str = Header(default="")):
    if x_api_key != get_settings().admin_api_key:
        raise HTTPException(401, "Invalid or missing X-API-Key")


admin = [Depends(require_admin)]


# --- Ingestion helpers -------------------------------------------------------

def _uploads_dir() -> Path:
    d = get_settings().data_dir / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _title_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\d+[_-]", "", stem)
    return re.sub(r"[_-]+", " ", stem).strip().title()


def _ingest_file(svc: Services, filename: str, data: bytes, doc_id: str | None = None):
    title = _title_from_filename(filename)
    doc_id = doc_id or svc.db.create_document(title, filename, Path(filename).suffix.lstrip(".").lower())
    (_uploads_dir() / f"{doc_id}__{Path(filename).name}").write_bytes(data)
    try:
        sections = parse_file(filename, data)
        with svc.ingest_lock:
            return svc.pipeline.ingest_sections(doc_id, title, sections)
    except Exception as e:
        svc.db.update_document(doc_id, status="failed", error=str(e)[:500])
        return None


def _ingest_sections(svc: Services, doc_id: str, title: str, sections: list[Section]):
    try:
        with svc.ingest_lock:
            svc.pipeline.ingest_sections(doc_id, title, sections)
    except Exception:
        pass  # error already stored on the document


# --- Health / status ---------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status", dependencies=admin)
def status(svc: Services = Depends(get_services)):
    return svc.status()


# --- Documents ---------------------------------------------------------------

@app.get("/api/documents", dependencies=admin)
def list_documents(svc: Services = Depends(get_services)):
    return svc.db.list_documents()


@app.post("/api/documents/upload", dependencies=admin)
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...), svc: Services = Depends(get_services)):
    created = []
    for f in files:
        if Path(f.filename or "").suffix.lower() not in SUPPORTED:
            raise HTTPException(400, f"{f.filename}: unsupported type. Allowed: {', '.join(sorted(SUPPORTED))}")
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{f.filename} is larger than 20 MB")
        title = _title_from_filename(f.filename)
        doc_id = svc.db.create_document(title, f.filename, Path(f.filename).suffix.lstrip(".").lower())
        background.add_task(_ingest_file, svc, f.filename, data, doc_id)
        created.append({"id": doc_id, "title": title, "status": "processing"})
    return created


class UrlIn(BaseModel):
    url: str


@app.post("/api/documents/url", dependencies=admin)
def add_url(body: UrlIn, background: BackgroundTasks, svc: Services = Depends(get_services)):
    try:
        title, sections = fetch_url(body.url)
    except Exception as e:
        raise HTTPException(400, f"Could not fetch the page: {e}")
    doc_id = svc.db.create_document(title[:120], body.url, "web")
    background.add_task(_ingest_sections, svc, doc_id, title[:120], sections)
    return {"id": doc_id, "title": title, "status": "processing"}


class TextIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=10)


@app.post("/api/documents/text", dependencies=admin)
def add_text(body: TextIn, background: BackgroundTasks, svc: Services = Depends(get_services)):
    doc_id = svc.db.create_document(body.title, "pasted text", "text")
    background.add_task(_ingest_sections, svc, doc_id, body.title, parse_markdown(body.text))
    return {"id": doc_id, "title": body.title, "status": "processing"}


@app.get("/api/documents/{doc_id}/chunks", dependencies=admin)
def doc_chunks(doc_id: str, svc: Services = Depends(get_services)):
    return svc.db.doc_chunks(doc_id)


@app.delete("/api/documents/{doc_id}", dependencies=admin)
def delete_document(doc_id: str, svc: Services = Depends(get_services)):
    if not svc.db.get_document(doc_id):
        raise HTTPException(404, "Document not found")
    with svc.ingest_lock:
        svc.pipeline.remove(doc_id)
    for p in _uploads_dir().glob(f"{doc_id}__*"):
        p.unlink(missing_ok=True)
    return {"deleted": doc_id}


@app.post("/api/reindex", dependencies=admin)
def reindex(background: BackgroundTasks, svc: Services = Depends(get_services)):
    """Rebuild every uploaded file (for example after adding an API key, to get an LLM-built graph)."""
    files = list(_uploads_dir().glob("*__*"))

    def run():
        for p in files:
            doc_id, name = p.name.split("__", 1)
            if svc.db.get_document(doc_id):
                with svc.ingest_lock:
                    svc.pipeline.remove(doc_id, keep_record=True)
                svc.db.update_document(doc_id, status="processing")
                _ingest_file(svc, name, p.read_bytes(), doc_id)

    background.add_task(run)
    return {"reindexing": len(files)}


# --- Knowledge graph ---------------------------------------------------------

@app.get("/api/graph", dependencies=admin)
def graph(limit: int = 400, doc_id: str | None = None, search: str | None = None, svc: Services = Depends(get_services)):
    return svc.graph.export(limit=limit, doc_id=doc_id, search=search)


@app.get("/api/graph/node/{node_id:path}", dependencies=admin)
def graph_node(node_id: str, svc: Services = Depends(get_services)):
    g = svc.graph.g
    if node_id not in g:
        raise HTTPException(404, "Entity not found")
    n = g.nodes[node_id]
    edges = []
    for u, v, d in list(g.out_edges(node_id, data=True)) + list(g.in_edges(node_id, data=True)):
        edges.append({"source": g.nodes[u]["name"], "target": g.nodes[v]["name"], "relation": d["relation"], "description": d["description"], "chunk_id": d["chunk_id"]})
    return {"id": node_id, "name": n["name"], "type": n["type"], "descriptions": n["descriptions"], "documents": sorted(n["doc_ids"]), "edges": edges[:100]}


# --- Chat ----------------------------------------------------------------------

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    phone: str = "test-user"
    mode: str = "graphrag"


@app.post("/api/chat", dependencies=admin)
def chat(body: ChatIn, svc: Services = Depends(get_services)):
    if body.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    return svc.handle_message(body.phone, body.message, channel="test", mode=body.mode)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: str = "graphrag"


@app.post("/api/ask", dependencies=admin)
def ask(body: AskIn, svc: Services = Depends(get_services)):
    """Stateless question answering, handy for comparing retrieval modes."""
    if body.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    out = svc.ask(body.question, [], body.mode)
    res = out["retrieval"]
    return {
        "answer": answer_to_dict(out["answer"]),
        "chunks": [{"id": c.id, "title": c.doc_title, "score": c.score, "found_by": c.sources, "text": c.text} for c in res.chunks],
        "facts": [f.as_text() for f in res.facts],
        "seeds": res.seeds,
        "timings": res.timings,
    }


# --- Conversations, unanswered, outbox ---------------------------------------

@app.get("/api/conversations", dependencies=admin)
def conversations(svc: Services = Depends(get_services)):
    active = {h["phone"] for h in svc.db.list_handovers()}
    rows = svc.db.conversations()
    for r in rows:
        r["handover"] = r["phone"] in active
    return rows


@app.get("/api/conversations/{phone}", dependencies=admin)
def conversation(phone: str, svc: Services = Depends(get_services)):
    return {"phone": phone, "handover": svc.db.handover_active(phone), "messages": svc.db.conversation(phone)}


@app.delete("/api/conversations/{phone}", dependencies=admin)
def delete_conversation(phone: str, svc: Services = Depends(get_services)):
    svc.db.clear_history(phone)
    svc.db.set_handover(phone, False)
    return {"deleted": phone}


class AgentReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


@app.post("/api/conversations/{phone}/reply", dependencies=admin)
def agent_reply(phone: str, body: AgentReplyIn, background: BackgroundTasks, svc: Services = Depends(get_services)):
    """A human agent replies to the customer (used during handover)."""
    svc.db.add_message(phone, "agent", body.text, "whatsapp")
    if not phone.startswith("test"):
        sender = whatsapp.WhatsAppSender(svc.settings, svc.db)
        background.add_task(sender.send, svc.settings.whatsapp_provider, phone, body.text)
    return {"ok": True}


class HandoverIn(BaseModel):
    active: bool


@app.post("/api/conversations/{phone}/handover", dependencies=admin)
def set_handover(phone: str, body: HandoverIn, svc: Services = Depends(get_services)):
    svc.db.set_handover(phone, body.active)
    return {"phone": phone, "handover": body.active}


@app.get("/api/unanswered", dependencies=admin)
def unanswered(svc: Services = Depends(get_services)):
    return svc.db.list_unanswered()


@app.post("/api/unanswered/{item_id}/resolve", dependencies=admin)
def resolve(item_id: int, svc: Services = Depends(get_services)):
    svc.db.resolve_unanswered(item_id)
    return {"ok": True}


@app.get("/api/outbox", dependencies=admin)
def outbox(svc: Services = Depends(get_services)):
    return svc.db.list_outbox()


@app.get("/api/eval/results", dependencies=admin)
def eval_results():
    if not EVAL_RESULTS.exists():
        return {"available": False}
    return {"available": True, **json.loads(EVAL_RESULTS.read_text(encoding="utf-8"))}


# --- WhatsApp webhooks -------------------------------------------------------

def _process_incoming(svc: Services, provider: str, msg: dict):
    if msg["id"] and svc.db.seen_event(f"{provider}:{msg['id']}"):
        return  # provider retry of a message we already handled
    text = "" if msg["has_media"] and not msg["text"] else msg["text"]
    try:
        out = svc.handle_message(msg["phone"], text, channel="whatsapp")
    except Exception:
        log.exception("Failed to answer %s", msg["phone"])
        out = {"reply": "Sorry, something went wrong on our side. Please try again in a moment."}
    if out.get("reply"):
        whatsapp.WhatsAppSender(svc.settings, svc.db).send(provider, msg["phone"], out["reply"])


def _public_url(request: Request) -> str:
    base = get_settings().public_base_url.rstrip("/")
    if base:
        return base + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")


@app.post("/webhooks/twilio")
async def twilio_webhook(request: Request, background: BackgroundTasks, x_twilio_signature: str = Header(default="")):
    svc = get_services()
    form = {k: str(v) for k, v in (await request.form()).items()}
    if not whatsapp.verify_twilio(svc.settings.twilio_auth_token, _public_url(request), form, x_twilio_signature):
        raise HTTPException(403, "Invalid Twilio signature")
    msg = whatsapp.parse_twilio(form)
    if msg:
        background.add_task(_process_incoming, svc, "twilio", msg)
    # Empty TwiML: the reply is sent separately through the REST API.
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")


@app.get("/webhooks/meta")
def meta_verify(request: Request):
    q = request.query_params
    token = get_settings().meta_verify_token
    if q.get("hub.mode") == "subscribe" and token and q.get("hub.verify_token") == token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@app.post("/webhooks/meta")
async def meta_webhook(request: Request, background: BackgroundTasks, x_hub_signature_256: str = Header(default="")):
    svc = get_services()
    body = await request.body()
    if not whatsapp.verify_meta(svc.settings.meta_app_secret, body, x_hub_signature_256):
        raise HTTPException(403, "Invalid Meta signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    for msg in whatsapp.parse_meta(payload):
        background.add_task(_process_incoming, svc, "meta", msg)
    return {"ok": True}


# --- Privacy policy (required to publish a Meta app) -------------------------

PRIVACY_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Privacy Policy</title>
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;line-height:1.6;color:#1b1f24}}</style>
</head><body><h1>Privacy Policy</h1>
<p>This is a portfolio demo of a WhatsApp customer-support chatbot for {company}, a fictional company.</p>
<h2>What we collect</h2><p>When you message the bot on WhatsApp we receive your phone number, your WhatsApp profile name
and the text of your messages. We store the conversation so the bot can remember context and so the
operator can review unanswered questions.</p>
<h2>How we use it</h2><p>Messages are used only to answer your questions. To write an answer, the text of your question and
excerpts from the company's documents are sent to an AI model provider (Google Gemini or Anthropic Claude).
We do not sell or share your data for advertising.</p>
<h2>Retention and deletion</h2><p>The demo runs on a free server that erases stored conversations when it restarts. You can ask for your
data to be deleted at any time by sending the message <b>reset</b> to the bot, which deletes your conversation history{contact}.</p>
</body></html>"""


@app.get("/privacy", include_in_schema=False)
@app.get("/data-deletion", include_in_schema=False)
def privacy():
    s = get_settings()
    contact = f", or by emailing the operator at {s.contact_email}" if s.contact_email else ""
    return Response(PRIVACY_HTML.format(company=s.company_name, contact=contact), media_type="text/html")


# --- Dashboard (built React app) ---------------------------------------------

if DASHBOARD_DIST.exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        target = (DASHBOARD_DIST / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(DASHBOARD_DIST.resolve()):
            return FileResponse(target)
        return FileResponse(DASHBOARD_DIST / "index.html")
