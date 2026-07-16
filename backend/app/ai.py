"""AI metadata generation (Anthropic). Inert until ANTHROPIC_API_KEY is set —
callers get None and fall back to raw values, mirroring the codebase's other
optional integrations (Razorpay/Sentry/SES). No SDK dependency: talks to the
Messages API over httpx.
"""

from __future__ import annotations

import json
import logging

from .config import get_settings

log = logging.getLogger("app.ai")
_API = "https://api.anthropic.com/v1/messages"


def enabled() -> bool:
    return bool(get_settings().anthropic_api_key)


def generate_metadata(title: str, kind: str, content: str) -> dict | None:
    """Draft {summary, description, tags[]} for a repo/resource. Returns None when
    disabled or on any error (best-effort enrichment — never blocks the caller)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    prompt = (
        f"You are cataloguing a software {kind}. Given its name and content, return "
        "STRICT JSON with keys: summary (<=140 chars), description (2-3 sentences), "
        "tags (array of <=6 short lowercase keywords). No prose, JSON only.\n\n"
        f"Name: {title}\n\nContent:\n{(content or '')[:6000]}"
    )
    try:
        import httpx

        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                _API,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if r.status_code >= 400:
            log.warning("Anthropic returned %s", r.status_code)
            return None
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        data = json.loads(text[start : end + 1])
        return {
            "summary": str(data.get("summary", ""))[:140],
            "description": str(data.get("description", "")),
            "tags": [str(t).lower()[:40] for t in (data.get("tags") or [])][:6],
        }
    except Exception:
        log.exception("AI metadata generation failed")
        return None
