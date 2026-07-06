"""Billing scaffolding graceful degradation + cache no-op (billing.py, payments.py,
cache.py). Spec §5 / §8. With no Razorpay/Redis credentials configured,
everything must degrade cleanly rather than crash.

    cd backend && .venv/bin/python -m pytest tests/test_billing.py -q
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app import cache, payments  # noqa: E402

c = TestClient(app)
_n = [0]


def _user(plan="FREE"):
    _n[0] += 1
    email = f"bill{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"B{_n[0]}"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    if plan != "FREE":
        db = SessionLocal()
        db.get(User, uid).plan = plan
        db.commit()
        db.close()
    return h, uid


def test_payments_disabled_without_credentials():
    assert payments.is_enabled() is False
    cfg = c.get("/api/billing/config")
    assert cfg.status_code == 200
    assert cfg.json()["enabled"] is False
    assert cfg.json()["key_id"] is None
    assert len(cfg.json()["plans"]) == 3


def test_checkout_degrades_gracefully_when_not_configured():
    h, _ = _user()
    r = c.post("/api/billing/checkout", json={"plan": "PRO", "target_type": "user"}, headers=h)
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_checkout_rejects_invalid_plan():
    h, _ = _user()
    r = c.post("/api/billing/checkout", json={"plan": "FREE", "target_type": "user"}, headers=h)
    assert r.status_code == 422


def test_webhook_rejected_when_not_configured():
    r = c.post("/api/billing/webhook", content=b"{}", headers={"X-Razorpay-Signature": "x"})
    assert r.status_code == 503, r.text


def test_subscription_reports_current_plan():
    h, _ = _user(plan="PRO")
    r = c.get("/api/billing/subscription", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["plan"] == "PRO"
    assert isinstance(r.json()["payments"], list)


def test_cache_is_transparent_noop_without_redis():
    assert cache.enabled() is False
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return {"v": calls["n"]}

    # Without Redis, cached() always calls the producer (no stale reads).
    assert cache.cached("t:key", produce)["v"] == 1
    assert cache.cached("t:key", produce)["v"] == 2
    assert cache.get("t:key") is None  # nothing persisted


def test_public_stats_still_works_through_cache_helper():
    r = c.get("/api/public/stats")
    assert r.status_code == 200
    assert set(r.json()) == {"skills", "mcp", "notes", "total_installs", "total"}


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
