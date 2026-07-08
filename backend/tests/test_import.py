"""Marketplace import — no duplicates: an org can't import its own resource, and
re-importing returns the existing copy instead of duplicating (bug fix).

    cd backend && .venv/bin/python -m pytest tests/test_import.py -q
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


def _user():
    _n[0] += 1
    email = f"imp{_n[0]}_{os.getpid()}@example.com"
    s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Imp {_n[0]}"}).json()
    r = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    u = db.get(User, uid)
    u.plan = "ENTERPRISE"
    u.is_publisher = True
    db.commit()
    db.close()
    return h


def _org(h):
    _n[0] += 1
    return c.post("/api/orgs", json={"name": f"ImpOrg {_n[0]} {os.getpid()}"}, headers=h).json()["slug"]


def _published_org_resource(h, slug):
    """Create an ORG resource and publish it live (owner is org admin → auto-approve)."""
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    rid = c.post(
        "/api/resources",
        json={"type": "SKILL", "title": "Shared Skill", "scope_type": "ORG", "scope_id": org_id},
        headers=h,
    ).json()["id"]
    pub = c.post(f"/api/resources/{rid}/publish", headers=h)
    assert pub.json()["approval_status"] == "approved", pub.text
    return rid


def test_org_cannot_import_its_own_resource():
    owner = _user()
    slug = _org(owner)
    rid = _published_org_resource(owner, slug)
    r = c.post(f"/api/resources/{rid}/import", json={"org_slug": slug}, headers=owner)
    assert r.status_code == 422, r.text
    assert "already belongs" in r.json()["error"]["message"].lower()


def test_reimport_returns_existing_copy_no_duplicate():
    owner = _user()
    owner_slug = _org(owner)
    rid = _published_org_resource(owner, owner_slug)

    importer = _user()
    imp_slug = _org(importer)

    first = c.post(f"/api/resources/{rid}/import", json={"org_slug": imp_slug}, headers=importer)
    assert first.status_code < 400, first.text
    copy_id = first.json()["id"]

    second = c.post(f"/api/resources/{rid}/import", json={"org_slug": imp_slug}, headers=importer)
    assert second.status_code < 400, second.text
    # Same copy returned — no duplicate created.
    assert second.json()["id"] == copy_id

    rows = c.get(f"/api/orgs/{imp_slug}/resources", headers=importer).json()
    assert sum(1 for x in rows if x["id"] == copy_id) == 1
    assert sum(1 for x in rows if x["title"] == "Shared Skill") == 1


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
