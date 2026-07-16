"""AI metadata generation — provider-agnostic, inert until a key is configured
(callers get None and fall back to raw values, like the other optional
integrations). Supports a free provider (Google Gemini) and Anthropic; picks
whichever is configured. No SDK dependency — plain httpx.
"""

from __future__ import annotations

import json
import logging

from .config import get_settings

log = logging.getLogger("app.ai")
_ANTHROPIC = "https://api.anthropic.com/v1/messages"
_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


def _provider() -> str | None:
    """Resolve the active provider from config, or None when unconfigured."""
    s = get_settings()
    choice = (s.ai_provider or "auto").lower()
    if choice == "gemini":
        return "gemini" if s.gemini_api_key else None
    if choice == "anthropic":
        return "anthropic" if s.anthropic_api_key else None
    # auto: prefer the free provider (Gemini), then Anthropic
    if s.gemini_api_key:
        return "gemini"
    if s.anthropic_api_key:
        return "anthropic"
    return None


def enabled() -> bool:
    return _provider() is not None


def _prompt(title: str, kind: str, content: str) -> str:
    return (
        f"You are cataloguing a software {kind}. Given its name and content, return "
        "STRICT JSON with keys: summary (<=140 chars), description (2-3 sentences), "
        "tags (array of <=6 short lowercase keywords). No prose, JSON only.\n\n"
        f"Name: {title}\n\nContent:\n{(content or '')[:6000]}"
    )


def _extract(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return {
        "summary": str(data.get("summary", ""))[:140],
        "description": str(data.get("description", "")),
        "tags": [str(t).lower()[:40] for t in (data.get("tags") or [])][:6],
    }


def generate_metadata(title: str, kind: str, content: str) -> dict | None:
    """Draft {summary, description, tags[]}. None when disabled or on any error
    (best-effort enrichment — never blocks the caller)."""
    provider = _provider()
    if provider is None:
        return None
    s = get_settings()
    prompt = _prompt(title, kind, content)
    try:
        import time

        import httpx

        def _post(client: "httpx.Client", url: str, **kw):
            # Retry transient 429/503 (free-tier overload) a couple of times.
            for attempt in range(3):
                r = client.post(url, **kw)
                if r.status_code in (429, 503) and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return r
            return r

        if provider == "gemini":
            with httpx.Client(timeout=30.0) as c:
                r = _post(c, f"{_GEMINI}/{s.gemini_model}:generateContent",
                          params={"key": s.gemini_api_key},
                          json={"contents": [{"parts": [{"text": prompt}]}]})
            if r.status_code >= 400:
                log.warning("Gemini returned %s", r.status_code)
                return None
            cands = r.json().get("candidates") or []
            parts = (cands[0].get("content", {}).get("parts", []) if cands else [])
            text = "".join(p.get("text", "") for p in parts)
        else:  # anthropic
            with httpx.Client(timeout=30.0) as c:
                r = _post(c, _ANTHROPIC,
                          headers={"x-api-key": s.anthropic_api_key,
                                   "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": s.anthropic_model, "max_tokens": 400,
                                "messages": [{"role": "user", "content": prompt}]})
            if r.status_code >= 400:
                log.warning("Anthropic returned %s", r.status_code)
                return None
            text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return _extract(text)
    except Exception:
        log.exception("AI metadata generation failed")
        return None
