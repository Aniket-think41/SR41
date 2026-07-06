"""
Razorpay integration — scaffolded now, activates when credentials are present
(spec §5).

With no key configured, every gated action degrades gracefully:
``is_enabled()`` is False, :func:`create_order` is never reached (the router
returns a clear "not configured" error), and :func:`verify_webhook` rejects.
Adding ``RAZORPAY_KEY_ID`` / ``RAZORPAY_KEY_SECRET`` (+ webhook secret) later
turns it on with no other code change. The ``razorpay`` SDK is an optional
dependency — its absence is treated the same as "not configured".
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from .config import get_settings

log = logging.getLogger("app.payments")
settings = get_settings()

try:  # optional dependency
    import razorpay as _razorpay
except Exception:  # pragma: no cover
    _razorpay = None


def is_enabled() -> bool:
    """True only when the SDK is installed AND both keys are configured."""
    return bool(_razorpay and settings.razorpay_key_id and settings.razorpay_key_secret)


def webhook_configured() -> bool:
    return bool(settings.razorpay_webhook_secret)


def public_config() -> dict:
    """Safe-to-expose config for the frontend checkout widget."""
    return {
        "enabled": is_enabled(),
        "key_id": settings.razorpay_key_id if is_enabled() else None,
        "provider": "razorpay",
        "currency": "USD",
    }


def _client():  # pragma: no cover - only runs with real credentials
    return _razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


def create_order(amount_cents: int, receipt: str, notes: dict) -> dict:  # pragma: no cover
    """Create a Razorpay order (smallest currency unit). Only called when
    :func:`is_enabled`."""
    client = _client()
    return client.order.create(
        {"amount": amount_cents, "currency": "USD", "receipt": receipt, "notes": notes, "payment_capture": 1}
    )


def verify_webhook(raw_body: bytes, signature: str | None) -> bool:
    """HMAC-SHA256 verification of a Razorpay webhook payload against the
    configured webhook secret. Returns False when unconfigured."""
    secret = settings.razorpay_webhook_secret
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
