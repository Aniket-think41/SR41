"""In-dashboard password reset via email OTP, and the Microsoft-disabled path.

    cd backend && .venv/bin/python -m pytest tests/test_password_reset.py -q
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

c = TestClient(app)
_n = [0]


def _signed_in():
    _n[0] += 1
    email = f"pr{_n[0]}_{os.getpid()}@example.com"
    s = c.post("/api/auth/signup", json={"email": email, "password": "oldpassword1", "display_name": "PR"}).json()
    r = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return h, email


def test_password_reset_via_otp_changes_password():
    h, email = _signed_in()
    start = c.post("/api/auth/password/reset-otp", json={}, headers=h)
    assert start.status_code < 400, start.text
    otp = start.json()["dev_otp"]

    # wrong code is rejected
    bad = c.post("/api/auth/password/reset-verify", json={"code": "999999", "new_password": "brandnew123"}, headers=h)
    assert bad.status_code == 401, bad.text

    # correct code sets the new password (no current password needed)
    ok = c.post("/api/auth/password/reset-verify", json={"code": otp, "new_password": "brandnew123"}, headers=h)
    assert ok.status_code < 400, ok.text
    assert ok.json()["must_change_password"] is False

    # new password works, old one doesn't
    assert c.post("/api/auth/login", json={"email": email, "password": "brandnew123"}).status_code < 400
    assert c.post("/api/auth/login", json={"email": email, "password": "oldpassword1"}).status_code == 401


def test_reset_requires_auth():
    assert c.post("/api/auth/password/reset-otp", json={}).status_code == 401


def test_microsoft_disabled_without_client_id():
    # No MICROSOFT_CLIENT_ID configured in tests → clear 403, not a crash.
    r = c.post("/api/auth/microsoft", json={"id_token": "whatever"})
    assert r.status_code == 403, r.text


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
