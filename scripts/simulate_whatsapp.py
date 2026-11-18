"""Pretend to be a WhatsApp customer: send a correctly signed Twilio webhook to the
running bot and print the reply from the outbox.

Use it to test the full webhook path before you have real WhatsApp credentials.
It signs requests with TWILIO_AUTH_TOKEN from .env, exactly like Twilio does.

  python scripts/simulate_whatsapp.py "Do you deliver to Kandy?"
  python scripts/simulate_whatsapp.py --phone +94771234567 --url http://127.0.0.1:8000 "hi"
"""

import argparse
import base64
import hashlib
import hmac
import sys
import time
import uuid
from pathlib import Path

import httpx


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def sign(token: str, url: str, params: dict) -> str:
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("message")
    ap.add_argument("--phone", default="+94770000001")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    args = ap.parse_args()

    env = load_env(Path(__file__).resolve().parents[1] / ".env")
    token, admin = env.get("TWILIO_AUTH_TOKEN", ""), env.get("ADMIN_API_KEY", "change-me")
    if not token:
        sys.exit("Set TWILIO_AUTH_TOKEN in .env (any value works for local testing).")

    hook = f"{env.get('PUBLIC_BASE_URL') or args.url}".rstrip("/") + "/webhooks/twilio"
    form = {"From": f"whatsapp:{args.phone}", "To": "whatsapp:+14155238886", "Body": args.message,
            "MessageSid": "SM" + uuid.uuid4().hex, "NumMedia": "0", "ProfileName": "Test Customer"}
    with httpx.Client(timeout=30) as c:
        before = {r["id"] for r in c.get(f"{args.url}/api/outbox", headers={"X-API-Key": admin}).json()}
        r = c.post(f"{args.url}/webhooks/twilio", data=form, headers={"X-Twilio-Signature": sign(token, hook, form)})
        print(f"webhook -> {r.status_code}")
        r.raise_for_status()
        for _ in range(120):
            new = [o for o in c.get(f"{args.url}/api/outbox", headers={"X-API-Key": admin}).json()
                   if o["id"] not in before and o["to_number"] == args.phone]
            if new:
                print(f"\nCustomer: {args.message}\nBot ({new[0]['status']}):\n{new[0]['text']}")
                return
            time.sleep(0.5)
    print("No reply within 60 seconds (is the customer in human-handover mode?)")


if __name__ == "__main__":
    main()
