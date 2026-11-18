"""WhatsApp providers: Twilio (sandbox, quick to test) and Meta WhatsApp Cloud API.

Both verify that webhooks really come from the provider before doing anything:
- Twilio signs each request with HMAC-SHA1 over the full URL + sorted form params.
- Meta signs the raw body with HMAC-SHA256 using the app secret (X-Hub-Signature-256).
Replies are sent through each provider's REST API from a background task, so
the webhook returns 200 immediately and providers do not time out or retry.
In dry-run mode replies are written to the outbox table instead of being sent.
"""

import base64
import hashlib
import hmac
import logging

import httpx

log = logging.getLogger(__name__)


# --- Signatures --------------------------------------------------------------

def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_twilio(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    if not auth_token or not signature:
        return False
    return hmac.compare_digest(twilio_signature(auth_token, url, params), signature)


def meta_signature(app_secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_meta(app_secret: str, body: bytes, signature: str) -> bool:
    if not app_secret or not signature:
        return False
    return hmac.compare_digest(meta_signature(app_secret, body), signature)


# --- Parsing -----------------------------------------------------------------

def parse_twilio(form: dict[str, str]) -> dict | None:
    sender = form.get("From", "")
    if not sender:
        return None
    return {
        "id": form.get("MessageSid") or form.get("SmsMessageSid") or "",
        "phone": sender.replace("whatsapp:", ""),
        "name": form.get("ProfileName", ""),
        "text": form.get("Body", ""),
        "has_media": int(form.get("NumMedia", "0") or 0) > 0,
    }


def parse_meta(payload: dict) -> list[dict]:
    """Extract incoming messages from a Meta webhook payload (ignores status updates)."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                mtype = m.get("type")
                text = ""
                if mtype == "text":
                    text = m.get("text", {}).get("body", "")
                elif mtype == "button":
                    text = m.get("button", {}).get("text", "")
                elif mtype == "interactive":
                    inter = m.get("interactive", {})
                    text = (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "")
                out.append({
                    "id": m.get("id", ""),
                    "phone": "+" + m.get("from", "").lstrip("+"),
                    "name": names.get(m.get("from"), ""),
                    "text": text,
                    "has_media": mtype not in ("text", "button", "interactive"),
                })
    return out


# --- Sending -----------------------------------------------------------------

class WhatsAppSender:
    def __init__(self, settings, db):
        self.s = settings
        self.db = db

    def send(self, provider: str, to: str, text: str) -> None:
        if self.s.whatsapp_dry_run:
            self.db.add_outbox(provider, to, text, "dry_run")
            log.info("[dry-run] to %s: %s", to, text[:80])
            return
        try:
            if provider == "twilio":
                self._send_twilio(to, text)
            else:
                self._send_meta(to, text)
            self.db.add_outbox(provider, to, text, "sent")
        except Exception as e:
            log.exception("Failed to send WhatsApp message to %s", to)
            self.db.add_outbox(provider, to, text, "failed", str(e)[:300])

    def _send_twilio(self, to: str, text: str):
        sid, token = self.s.twilio_account_sid, self.s.twilio_auth_token
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = {"From": self.s.twilio_whatsapp_from, "To": f"whatsapp:{to}", "Body": text}
        r = httpx.post(url, data=data, auth=(sid, token), timeout=20)
        r.raise_for_status()

    def _send_meta(self, to: str, text: str):
        url = f"https://graph.facebook.com/{self.s.meta_graph_version}/{self.s.meta_phone_number_id}/messages"
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {self.s.meta_access_token}"}, timeout=20)
        r.raise_for_status()
