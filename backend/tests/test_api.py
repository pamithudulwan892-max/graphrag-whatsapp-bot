import json
import time

import pytest
from fastapi.testclient import TestClient

from app.whatsapp import meta_signature, parse_meta, twilio_signature, verify_twilio

ADMIN = {"X-API-Key": "test-admin"}
DOC = """# Warranty
The Nila AirCool 12000 has the Gold Care warranty plan. Gold Care covers the inverter compressor for 10 years.

# Branches
The Galle Branch is at 12 Wakwella Road. It is open on Sunday from 10.00 AM - 2.00 PM.
"""


@pytest.fixture
def client(settings):
    from app.main import app

    with TestClient(app) as c:
        r = c.post("/api/documents/text", json={"title": "Policies", "text": DOC}, headers=ADMIN)
        assert r.status_code == 200
        for _ in range(50):
            docs = c.get("/api/documents", headers=ADMIN).json()
            if docs[0]["status"] != "processing":
                break
            time.sleep(0.1)
        assert docs[0]["status"] == "ready", docs[0]
        yield c


def test_admin_key_required(client):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers=ADMIN).status_code == 200


def test_chat_answers_with_citation(client):
    r = client.post("/api/chat", json={"message": "How long is the compressor covered on the AirCool 12000?", "phone": "test-1"}, headers=ADMIN).json()
    assert "10 years" in r["reply"]
    assert r["debug"]["citations"] and r["debug"]["citations"][0]["title"] == "Policies"


def test_greeting_and_human_handover(client):
    hi = client.post("/api/chat", json={"message": "hello", "phone": "test-2"}, headers=ADMIN).json()
    assert "Welcome" in hi["reply"]
    human = client.post("/api/chat", json={"message": "I want to talk to a human", "phone": "test-2"}, headers=ADMIN).json()
    assert "team" in human["reply"]
    # While a human owns the chat the bot stays quiet.
    quiet = client.post("/api/chat", json={"message": "hello?", "phone": "test-2"}, headers=ADMIN).json()
    assert quiet["reply"] is None
    unanswered = client.get("/api/unanswered", headers=ADMIN).json()
    assert any(u["reason"] == "customer asked for a human" for u in unanswered)


def test_memory_is_per_phone(client):
    client.post("/api/chat", json={"message": "Tell me about the Galle Branch", "phone": "test-3"}, headers=ADMIN)
    convo = client.get("/api/conversations/test-3", headers=ADMIN).json()
    assert [m["role"] for m in convo["messages"]] == ["user", "assistant"]
    assert client.get("/api/conversations/test-4", headers=ADMIN).json()["messages"] == []


def test_twilio_webhook_rejects_bad_signature(client):
    r = client.post("/webhooks/twilio", data={"From": "whatsapp:+94770000000", "Body": "hi"}, headers={"X-Twilio-Signature": "wrong"})
    assert r.status_code == 403


def test_twilio_webhook_end_to_end(client):
    form = {"From": "whatsapp:+94771234567", "Body": "What is the address of the Galle Branch?", "MessageSid": "SM1", "NumMedia": "0"}
    sig = twilio_signature("twilio-test-token", "http://testserver/webhooks/twilio", form)
    r = client.post("/webhooks/twilio", data=form, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200 and "<Response>" in r.text
    out = client.get("/api/outbox", headers=ADMIN).json()
    assert out and out[0]["to_number"] == "+94771234567" and "Wakwella" in out[0]["text"]
    # Twilio retries the same MessageSid: it must not be answered twice.
    client.post("/webhooks/twilio", data=form, headers={"X-Twilio-Signature": sig})
    assert len(client.get("/api/outbox", headers=ADMIN).json()) == 1


def test_meta_webhook_verify_and_message(client):
    ok = client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "meta-verify", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/webhooks/meta", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403

    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "94770001111", "profile": {"name": "Amal"}}],
        "messages": [{"id": "wamid.1", "from": "94770001111", "type": "text", "text": {"body": "When is the Galle Branch open on Sunday?"}}],
    }}]}]}
    body = json.dumps(payload).encode()
    bad = client.post("/webhooks/meta", content=body, headers={"X-Hub-Signature-256": "sha256=00", "Content-Type": "application/json"})
    assert bad.status_code == 403
    good = client.post("/webhooks/meta", content=body, headers={"X-Hub-Signature-256": meta_signature("meta-test-secret", body), "Content-Type": "application/json"})
    assert good.status_code == 200
    out = client.get("/api/outbox", headers=ADMIN).json()
    assert out[0]["provider"] == "meta" and out[0]["to_number"] == "+94770001111"


def test_delete_document_forgets_it(client):
    doc_id = client.get("/api/documents", headers=ADMIN).json()[0]["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=ADMIN).status_code == 200
    status = client.get("/api/status", headers=ADMIN).json()
    assert status["chunks"] == 0 and status["graph"]["nodes"] == 0


def test_signature_helpers():
    params = {"Body": "hi", "From": "whatsapp:+1"}
    sig = twilio_signature("tok", "https://x.test/webhooks/twilio", params)
    assert verify_twilio("tok", "https://x.test/webhooks/twilio", params, sig)
    assert not verify_twilio("tok", "https://x.test/webhooks/twilio", {**params, "Body": "tampered"}, sig)
    assert parse_meta({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}) == []


def test_public_demo_works_without_login(client):
    info = client.get("/api/public/info").json()
    assert info["enabled"] and info["documents"] == ["Policies"]
    r = client.post("/api/public/chat", json={"message": "Where is the Galle Branch?", "session": "abcdefgh12"})
    assert r.status_code == 200
    body = r.json()
    assert "Wakwella" in body["reply"] and body["sources"][0]["title"] == "Policies"
    # Public visitors show up in the dashboard's conversation list.
    assert any(c["phone"] == "web-abcdefgh12" for c in client.get("/api/conversations", headers=ADMIN).json())


def test_public_demo_limits(client, monkeypatch):
    import app.main as main
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "public_daily_limit", 2)
    main.public_guard = None
    ok = [client.post("/api/public/chat", json={"message": "hello", "session": f"sess{i:06d}"}).status_code for i in range(3)]
    assert ok == [200, 200, 429]
    assert client.post("/api/public/chat", json={"message": "hi", "session": "bad session!"}).status_code == 422
    main.public_guard = None
