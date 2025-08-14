"""
OpenAI Vision client — JSON output + dual throttling + real Retry-After handling.
"""

import asyncio
import base64
import json
import os
import re
import time
from typing import Optional
from openai import OpenAI

from ..models import OCRResult
from ..config import (
    OPENAI_MODEL,
    OPENAI_MAX_RPM,
    OPENAI_MAX_TPM,
    OPENAI_TOKENS_PER_IMAGE,
)

def _guess_mime(b: bytes) -> str:
    if b.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if b[0:3] == b"\xff\xd8\xff": return "image/jpeg"
    return "image/jpeg"

def _to_data_url(image_bytes: bytes) -> str:
    mime = _guess_mime(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl != -1: t = t[nl + 1 :]
        if t.endswith("```"): t = t[:-3]
    return t.strip()

def _parse_retry_after_seconds(msg: str) -> Optional[float]:
    msg = str(msg)
    m = re.search(r"try again in\s*(\d+)h(\d+)m(\d+)s", msg, re.I)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    m = re.search(r"try again in\s*(\d+)h(\d+)m", msg, re.I)
    if m: return int(m.group(1))*3600 + int(m.group(2))*60
    m = re.search(r"try again in\s*(\d+)m(\d+)s", msg, re.I)
    if m: return int(m.group(1))*60 + int(m.group(2))
    m = re.search(r"try again in\s*(\d+)m\b", msg, re.I)
    if m: return int(m.group(1))*60
    m = re.search(r"try again in\s*(\d+)s\b", msg, re.I)
    if m: return float(m.group(1))
    return None

INTERVAL_BY_RPM = (60.0 / OPENAI_MAX_RPM) if OPENAI_MAX_RPM > 0 else 0.0
INTERVAL_BY_TPM = (OPENAI_TOKENS_PER_IMAGE / OPENAI_MAX_TPM) * 60.0 if OPENAI_MAX_TPM > 0 else 0.0
MIN_INTERVAL_SEC = max(INTERVAL_BY_RPM, INTERVAL_BY_TPM)

_throttle_lock = asyncio.Lock()
_last_call_ts = 0.0
_next_allowed_ts = 0.0   # set when server tells us to retry later

async def _throttle_once():
    global _last_call_ts, _next_allowed_ts
    async with _throttle_lock:
        now = time.monotonic()
        wait_due_to_interval = max(0.0, MIN_INTERVAL_SEC - (now - _last_call_ts))
        wait_due_to_server = max(0.0, _next_allowed_ts - now)
        wait = max(wait_due_to_interval, wait_due_to_server)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_ts = time.monotonic()

class VisionClient:
    """OpenAI Chat Completions for vision OCR with robust backoff."""
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.model = OPENAI_MODEL or "gpt-4o-mini"

    async def extract(self, image_bytes: bytes) -> OCRResult:
        await _throttle_once()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_sync, image_bytes)

    def _extract_sync(self, image_bytes: bytes) -> OCRResult:
        global _next_allowed_ts
        data_url = _to_data_url(image_bytes)

        system_prompt = (
            "You are an OCR+reasoning parser for Instagram stats screenshots.\n"
            'Return JSON with keys: "username" (lowercase, no "@"), '
            '"followers" (as displayed, may include k/m), '
            '"confidence" (0..1). If not confident, set confidence <= 0.6. '
            "Return ONLY JSON."
        )

        max_attempts = 5
        base_backoff = 20.0

        for attempt in range(1, max_attempts + 1):
            try:
                chat = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract username and total followers. Output only JSON."},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        },
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                text = (chat.choices[0].message.content or "").strip()
                text = _strip_code_fences(text)
                data = json.loads(text)

                username = data.get("username") if isinstance(data, dict) else None
                followers = data.get("followers") if isinstance(data, dict) else None
                conf = data.get("confidence") if isinstance(data, dict) else None
                try:
                    conf = float(conf) if conf is not None else None
                except Exception:
                    conf = None

                print("VISION OK:", {"username": username, "followers": followers, "confidence": conf})
                return OCRResult(username=username, followers=followers, confidence=conf)

            except Exception as e:
                msg = str(e)
                retry_after = _parse_retry_after_seconds(msg)

                resp = getattr(e, "response", None)
                if resp is not None:
                    try:
                        h = getattr(resp, "headers", {}) or {}
                        retry_after_hdr = h.get("retry-after") or h.get("Retry-After")
                        if retry_after_hdr and not retry_after:
                            try:
                                retry_after = float(retry_after_hdr)
                            except Exception:
                                retry_after = None
                        reset_epoch = h.get("x-ratelimit-reset-requests") or h.get("x-ratelimit-reset-tokens")
                        if reset_epoch and str(reset_epoch).isdigit():
                            secs = max(0.0, float(reset_epoch) - time.time())
                            if secs > 0:
                                retry_after = max(retry_after or 0.0, secs)
                    except Exception:
                        pass

                if "Too Many Requests" in msg or "rate limit" in msg.lower() or "429" in msg:
                    if retry_after is None:
                        retry_after = base_backoff * (2 ** (attempt - 1))
                    _next_allowed_ts = max(_next_allowed_ts, time.monotonic() + retry_after)
                    print(f"VISION RATE-LIMIT: attempt {attempt}/{max_attempts}, sleeping {retry_after:.1f}s")
                    time.sleep(retry_after)
                    continue

                print("VISION ERROR (chat request):", repr(e))
                return OCRResult()

        print("VISION ERROR: exhausted retries due to rate limits.")
        return OCRResult()

def estimate_wait_seconds() -> float:
    now = time.monotonic()
    wait_due_to_interval = max(0.0, MIN_INTERVAL_SEC - (now - _last_call_ts))
    wait_due_to_server = max(0.0, _next_allowed_ts - now)
    return max(wait_due_to_interval, wait_due_to_server)
