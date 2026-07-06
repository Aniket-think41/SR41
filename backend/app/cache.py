"""
Redis cache — scaffolded now, activates when ``redis_url`` is set (spec §8).

Every function degrades safely: with no Redis (or the ``redis`` package missing,
or ``cache_enabled=False``) reads miss and writes are dropped, so callers simply
hit the database directly. Adding ``REDIS_URL`` later turns caching on with no
code change. Values are JSON-serialized.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .config import get_settings

log = logging.getLogger("app.cache")
settings = get_settings()

try:  # optional dependency
    import redis as _redis
except Exception:  # pragma: no cover
    _redis = None

_client = None
_initialized = False


def _get_client():
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    if not (settings.cache_enabled and settings.redis_url and _redis):
        _client = None
        return None
    try:
        _client = _redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _client.ping()
        log.info("Redis cache enabled")
    except Exception:  # pragma: no cover - unreachable/misconfigured Redis
        log.warning("Redis unreachable — cache disabled, falling back to direct reads")
        _client = None
    return _client


def enabled() -> bool:
    return _get_client() is not None


def get(key: str) -> Any | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:  # pragma: no cover
        return None


def set(key: str, value: Any, ttl: int | None = None) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value, default=str), ex=ttl or settings.cache_default_ttl)
    except Exception:  # pragma: no cover
        pass


def delete(*keys: str) -> None:
    client = _get_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception:  # pragma: no cover
        pass


def cached(key: str, producer: Callable[[], Any], ttl: int | None = None) -> Any:
    """Return the cached value for ``key`` or compute + store it. Transparent
    when Redis is absent (always calls ``producer``)."""
    hit = get(key)
    if hit is not None:
        return hit
    value = producer()
    set(key, value, ttl)
    return value
