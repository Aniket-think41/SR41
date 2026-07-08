"""Signup email-OTP verification flow (app/routers/auth.py).

Signup no longer creates an account directly: it emails a one-time code and the
account is created only after POST /api/auth/verify-email confirms it. With SES
disabled (the test default) the code comes back in the response as `dev_otp`.

    cd backend && .venv/bin/python -m pytest tests/test_signup_otp.py -q
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

c = TestClient(app)
_n = [0]


def _email() -> str:
    _n[0] += 1
    return f"otp{_n[0]}_{os.getpid()}@example.com"


def _signup(email: str, password: str = "password123", name: str = "OTP User") -> dict:
    return c.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": name},
    ).json()


def test_signup_does_not_create_account_until_verified():
    email = _email()
    s = _signup(email)
    # step 1: pending, code surfaced (SES off), NO session yet
    assert s["pending"] is True
    assert s["email"] == email
    assert "access_token" not in s
    assert s.get("dev_otp")
    # no user row exists yet, and login can't work
    db = SessionLocal()
    assert db.query(User).filter(User.email == email).first() is None
    db.close()
    assert c.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 401


def test_verify_creates_account_and_signs_in_without_reset_gate():
    email = _email()
    s = _signup(email)
    v = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    assert v.status_code < 400, v.text
    body = v.json()
    assert body["access_token"]
    # self-signup owns its password → NOT forced through the change-password gate
    assert body["user"]["must_change_password"] is False
    # now a real account exists and password login works
    assert c.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code < 400


def test_wrong_code_is_rejected_then_correct_works():
    email = _email()
    s = _signup(email)
    # a clearly-wrong code (guard against accidentally matching the real one)
    wrong = "1" * len(s["dev_otp"]) if s["dev_otp"] != "1" * len(s["dev_otp"]) else "2" * len(s["dev_otp"])
    bad = c.post("/api/auth/verify-email", json={"email": email, "code": wrong})
    assert bad.status_code == 401, bad.text
    good = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    assert good.status_code < 400, good.text


def test_too_many_attempts_locks_the_code():
    email = _email()
    s = _signup(email)
    wrong = "1" * len(s["dev_otp"]) if s["dev_otp"] != "1" * len(s["dev_otp"]) else "2" * len(s["dev_otp"])
    last = None
    for _ in range(6):
        last = c.post("/api/auth/verify-email", json={"email": email, "code": wrong})
    # after the attempt cap the pending record is dropped → "start again"
    assert last.status_code >= 400
    # even the correct code no longer works
    assert c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]}).status_code >= 400


def test_resend_issues_a_fresh_code():
    email = _email()
    s = _signup(email)
    r = c.post("/api/auth/signup/resend", json={"email": email})
    assert r.status_code < 400, r.text
    fresh = r.json()["dev_otp"]
    # the fresh code verifies
    assert c.post("/api/auth/verify-email", json={"email": email, "code": fresh}).status_code < 400


def test_duplicate_email_is_rejected_at_signup():
    email = _email()
    s = _signup(email)
    c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    # a second signup for the same (now-registered) email is a conflict
    again = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": "Dup"})
    assert again.status_code == 409, again.text


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
