"""Device-authorization login flow (app/routers/auth.py).

Driven through the real app with FastAPI's TestClient — no external network. Run:
    cd backend && .venv/bin/python -m pytest tests/test_device_auth.py -q
or standalone:
    cd backend && .venv/bin/python tests/test_device_auth.py
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# This test makes many /api/auth/* calls; turn off the auth rate limiter for it.
# (Must be set before app.main is imported so get_settings() picks it up.)
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
_n = [0]


def _user():
    """Create a fresh signed-in user; return its bearer headers."""
    _n[0] += 1
    r = c.post("/api/auth/signup", json={
        "email": f"dev{_n[0]}_{os.getpid()}@example.com",
        "password": "password123",
        "display_name": f"Dev {_n[0]}",
    })
    assert r.status_code < 400, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _start():
    s = c.post("/api/auth/device/start", json={"client_name": "Test CLI"})
    assert s.status_code < 400, s.text
    return s.json()


def test_start_returns_codes_and_verification_url():
    d = _start()
    assert d["device_code"] and d["user_code"]
    assert d["user_code"] in d["verification_uri_complete"]
    assert d["verification_uri_complete"].endswith(f"/activate?code={d['user_code']}")
    assert d["interval"] >= 1 and d["expires_in"] > 0


def test_poll_pending_before_approval():
    d = _start()
    p = c.post("/api/auth/device/token", json={"device_code": d["device_code"]})
    assert p.json()["status"] == "pending"


def test_full_approve_flow_issues_tokens():
    H = _user()
    d = _start()
    info = c.get(f"/api/auth/device/{d['user_code']}", headers=H)
    assert info.status_code < 400 and info.json()["client_name"] == "Test CLI"
    ap = c.post("/api/auth/device/approve", json={"user_code": d["user_code"]}, headers=H)
    assert ap.status_code < 400, ap.text
    p = c.post("/api/auth/device/token", json={"device_code": d["device_code"]}).json()
    assert p["status"] == "approved"
    assert p["access_token"] and p["refresh_token"]
    # the issued access token authenticates as the approver
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {p['access_token']}"})
    assert me.status_code == 200
    # one-time: a second poll after consumption no longer returns tokens
    again = c.post("/api/auth/device/token", json={"device_code": d["device_code"]}).json()
    assert again["status"] == "expired"


def test_refresh_by_body_rotates():
    H = _user()
    d = _start()
    c.post("/api/auth/device/approve", json={"user_code": d["user_code"]}, headers=H)
    tok = c.post("/api/auth/device/token", json={"device_code": d["device_code"]}).json()
    rf = c.post("/api/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert rf.status_code == 200, rf.text
    assert rf.json()["access_token"]
    new_refresh = rf.json()["refresh_token"]
    assert new_refresh and new_refresh != tok["refresh_token"]  # rotated
    # the old refresh token is now revoked
    reuse = c.post("/api/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert reuse.status_code == 401


def test_deny_flow():
    H = _user()
    d = _start()
    dn = c.post("/api/auth/device/deny", json={"user_code": d["user_code"]}, headers=H)
    assert dn.status_code < 400, dn.text
    p = c.post("/api/auth/device/token", json={"device_code": d["device_code"]}).json()
    assert p["status"] == "denied"


def test_info_and_approve_require_auth():
    d = _start()
    assert c.get(f"/api/auth/device/{d['user_code']}").status_code == 401
    assert c.post("/api/auth/device/approve", json={"user_code": d["user_code"]}).status_code == 401


def test_unknown_device_code_404():
    assert c.post("/api/auth/device/token", json={"device_code": "nope-nope-nope"}).status_code == 404


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
