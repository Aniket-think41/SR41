"""Public website feedback: anonymous submit + moderation + public list
(public.py + admin.py). Spec §4.

    cd backend && .venv/bin/python -m pytest tests/test_public_feedback.py -q
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


def _admin():
    _n[0] += 1
    email = f"pfa{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"A{_n[0]}"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    try:
        db.get(User, uid).is_admin = True
        db.commit()
    finally:
        db.close()
    return h


def test_anonymous_submit_is_pending_and_hidden_until_approved():
    sub = c.post(
        "/api/public/feedback",
        json={"message": "Love this product!", "rating": 5, "name": "Jamie"},
    )
    assert sub.status_code == 200, sub.text
    fid = sub.json()["id"]
    assert sub.json()["status"] == "pending"

    # not visible on the public list yet
    assert not any(f["id"] == fid for f in c.get("/api/public/feedback").json())

    # admin approves → now visible, and it never leaks the email
    admin_h = _admin()
    mod = c.post(f"/api/admin/feedback/{fid}/moderate", json={"decision": "approve"}, headers=admin_h)
    assert mod.status_code == 200, mod.text
    listed = c.get("/api/public/feedback").json()
    row = next((f for f in listed if f["id"] == fid), None)
    assert row is not None
    assert row["author"] == "Jamie"
    assert "email" not in row and "author_email" not in row


def test_reject_keeps_it_hidden():
    sub = c.post("/api/public/feedback", json={"message": "spammy", "name": "Spammer"})
    fid = sub.json()["id"]
    admin_h = _admin()
    c.post(f"/api/admin/feedback/{fid}/moderate", json={"decision": "reject"}, headers=admin_h)
    assert not any(f["id"] == fid for f in c.get("/api/public/feedback").json())


def test_admin_queue_shows_website_feedback():
    c.post("/api/public/feedback", json={"message": "from the web", "name": "Web User"})
    admin_h = _admin()
    rows = c.get("/api/admin/feedback", headers=admin_h).json()
    assert any(f["source"] == "website" for f in rows)


def test_public_submit_requires_message():
    r = c.post("/api/public/feedback", json={"name": "NoMessage"})
    assert r.status_code == 422


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
