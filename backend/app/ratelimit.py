"""
Rate limiting (BACKEND_SPEC §4.3) — sliding-window counters.

In-memory by default (fine for a single process / local dev). For multi-
instance production deployments set REDIS_URL and swap the store — the
middleware interface stays the same.
"""

import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .errors import envelope

settings = get_settings()

_windows: dict[str, deque] = defaultdict(deque)


def _allow(key: str, limit: int, window_s: int = 60) -> bool:
    now = time.monotonic()
    q = _windows[key]
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        method = request.method.upper()

        if path.startswith("/api/auth/") and method == "POST":
            # 10 req/min per IP on auth endpoints
            if not _allow(f"auth:{ip}", settings.rate_limit_auth_per_min):
                return envelope(429, "RATE_LIMITED", "Too many auth attempts — try again in a minute")
        elif path == "/api/public/search":
            if not _allow(f"search:{ip}", settings.rate_limit_search_per_min):
                return envelope(429, "RATE_LIMITED", "Search rate limit reached — try again in a minute")
        elif method in ("POST", "PATCH", "DELETE") and path.startswith("/api/"):
            # 60 writes/min per user (falls back to IP when unauthenticated)
            who = request.headers.get("Authorization", ip)[-48:]
            if not _allow(f"write:{who}", settings.rate_limit_write_per_min):
                return envelope(429, "RATE_LIMITED", "Rate limit reached — slow down a little")

        return await call_next(request)
