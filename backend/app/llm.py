"""One small interface over two LLM providers.

- Google Gemini (default, has a free tier): REST API, JSON-schema output.
- Anthropic Claude (paid, optional): Messages API with structured outputs.

Every call asks for JSON that matches a schema, so the rest of the code never
parses free text. With no key configured, `LLM.enabled` is False and callers
use their offline fallbacks instead.
"""

import copy
import json
import logging
import random
import re
import threading
import time

import httpx

from .config import Settings

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider = settings.active_provider
        self.enabled = self.provider is not None
        self.model = settings.llm_model
        self.usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        self._lock = threading.Lock()
        self._fallbacks = settings.llm_fallbacks
        self._gemini_json_schema = True  # switch to the older responseSchema field if rejected
        self._anthropic = None
        self._http = httpx.Client(timeout=90)
        if self.provider == "anthropic":
            import anthropic

            self._anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)

    def json(self, system: str, user: str, schema: dict, *, effort: str | None = None, max_tokens: int = 8000) -> dict:
        if not self.enabled:
            raise LLMError("LLM is disabled (no API key configured)")
        if self.provider == "gemini":
            text = self._gemini(system, user, schema, effort or self.settings.llm_effort, max_tokens)
        else:
            text = self._claude(system, user, schema, effort or self.settings.llm_effort, max_tokens)
        return parse_json(text)

    def _count(self, inp: int, out: int):
        with self._lock:
            self.usage["calls"] += 1
            self.usage["input_tokens"] += inp or 0
            self.usage["output_tokens"] += out or 0

    # --- Gemini -------------------------------------------------------------
    def _gemini(self, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> str:
        gen = {"responseMimeType": "application/json", "maxOutputTokens": max_tokens, "temperature": 0.1}
        if self._gemini_json_schema:
            gen["responseJsonSchema"] = schema
        else:
            gen["responseSchema"] = _openapi_schema(schema)
        if effort == "low":
            # Less thinking = faster chat replies. Gemini 2.5 uses a token budget, Gemini 3+ a level.
            if self.model.startswith("gemini-2.5-flash"):
                gen["thinkingConfig"] = {"thinkingBudget": 0}
            elif self.model.startswith("gemini-3"):
                gen["thinkingConfig"] = {"thinkingLevel": "low"}
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        url = GEMINI_URL.format(model=self.model)
        headers = {"x-goog-api-key": self.settings.gemini_api_key}
        for attempt in range(6):
            try:
                r = self._http.post(url, json=body, headers=headers)
            except httpx.HTTPError as e:
                if attempt == 5:
                    raise LLMError(f"Could not reach the Gemini API: {e}") from e
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 400 and self._gemini_json_schema and "responseJsonSchema" in r.text:
                self._gemini_json_schema = False
                return self._gemini(system, user, schema, effort, max_tokens)
            if r.status_code in (429, 500, 503) and attempt < 5:
                # Free tier allows a limited number of requests per minute: wait and retry.
                m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                wait = int(m.group(1)) + 1 if m else min(60, 2 ** attempt * 3)
                log.info("Gemini %s, retrying in %ss", r.status_code, wait)
                time.sleep(wait + random.random())
                continue
            if r.status_code != 200:
                raise LLMError(f"Gemini API error {r.status_code}: {r.text[:300]}")
            data = r.json()
            meta = data.get("usageMetadata", {})
            self._count(meta.get("promptTokenCount", 0), meta.get("candidatesTokenCount", 0))
            cands = data.get("candidates") or []
            if not cands:
                raise LLMError(f"Gemini returned no answer: {data.get('promptFeedback')}")
            finish = cands[0].get("finishReason")
            if finish not in (None, "STOP"):
                raise LLMError(f"Gemini stopped early: {finish}")
            parts = cands[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
        raise LLMError("Gemini API kept failing")

    # --- Claude -------------------------------------------------------------
    def _claude(self, system: str, user: str, schema: dict, effort: str, max_tokens: int) -> str:
        import anthropic

        params = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        try:
            resp = None
            if self._fallbacks:
                try:
                    resp = self._anthropic.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
                except anthropic.BadRequestError as e:
                    if "fallback" not in str(e.message).lower():
                        raise
                    self._fallbacks = False
            if resp is None:
                resp = self._anthropic.messages.create(**params)
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Could not reach the Claude API: {e}") from e
        self._count(getattr(resp.usage, "input_tokens", 0), getattr(resp.usage, "output_tokens", 0))
        if resp.stop_reason == "refusal":
            raise LLMError("The model declined this request")
        if resp.stop_reason == "max_tokens":
            raise LLMError("The model ran out of output tokens")
        return next((b.text for b in resp.content if b.type == "text"), "")


def parse_json(text: str) -> dict:
    """Parse model output as JSON, tolerating ```json fences that some open models add."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(t[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError(f"Model returned invalid JSON: {text[:200]}")


def _openapi_schema(schema: dict) -> dict:
    """Gemini's older responseSchema field does not accept additionalProperties."""
    s = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            node.pop("additionalProperties", None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s
