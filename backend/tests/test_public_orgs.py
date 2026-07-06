"""Public organization pages + follow (public.py, orgs.py). Spec §6.

    cd backend && .venv/bin/python -m pytest tests/test_public_orgs.py -q
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


def _user(plan="ENTERPRISE", admin=False, publisher=False):
    _n[0] += 1
    email = f"po{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"PO{_n[0]}"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        u.plan, u.is_admin = plan, admin
        if publisher:
            u.is_publisher = True
        db.commit()
    finally:
        db.close()
    return h, uid


def _org(h):
    _n[0] += 1
    return c.post("/api/orgs", json={"name": f"POrg {_n[0]} {os.getpid()}"}, headers=h).json()["slug"]


def test_org_page_hidden_until_public_then_visible():
    admin_h, _ = _user()
    slug = _org(admin_h)

    # not public → 404
    assert c.get(f"/api/public/orgs/{slug}").status_code == 404

    # admin opts in
    up = c.patch(f"/api/orgs/{slug}", json={"is_public": True}, headers=admin_h)
    assert up.status_code == 200 and up.json()["is_public"] is True

    page = c.get(f"/api/public/orgs/{slug}")
    assert page.status_code == 200, page.text
    assert page.json()["slug"] == slug
    assert page.json()["followers_count"] == 0
    assert isinstance(page.json()["resources"], list)

    # appears in the directory
    assert any(o["slug"] == slug for o in c.get("/api/public/orgs").json())


def test_org_page_lists_only_approved_public_resources():
    admin_h, _ = _user(admin=True, publisher=True)  # admin → own content auto-approves
    slug = _org(admin_h)
    org_id = c.get(f"/api/orgs/{slug}", headers=admin_h).json()["id"]
    c.patch(f"/api/orgs/{slug}", json={"is_public": True}, headers=admin_h)

    # a private org resource — should NOT show
    c.post("/api/resources", json={"type": "NOTE", "title": "Private", "scope_type": "ORG", "scope_id": org_id}, headers=admin_h)
    # a published (auto-approved) resource — should show
    r = c.post("/api/resources", json={"type": "SKILL", "title": "Shared", "scope_type": "ORG", "scope_id": org_id}, headers=admin_h)
    rid = r.json()["id"]
    c.post(f"/api/resources/{rid}/publish", headers=admin_h)

    titles = [x["title"] for x in c.get(f"/api/public/orgs/{slug}").json()["resources"]]
    assert "Shared" in titles
    assert "Private" not in titles


def test_follow_org_updates_count_and_state():
    admin_h, _ = _user()
    slug = _org(admin_h)
    c.patch(f"/api/orgs/{slug}", json={"is_public": True}, headers=admin_h)

    follower_h, _ = _user()
    assert c.post(f"/api/orgs/{slug}/follow", headers=follower_h).status_code < 400
    page = c.get(f"/api/public/orgs/{slug}", headers=follower_h).json()
    assert page["followers_count"] == 1
    assert page["following"] is True

    c.delete(f"/api/orgs/{slug}/follow", headers=follower_h)
    assert c.get(f"/api/public/orgs/{slug}", headers=follower_h).json()["followers_count"] == 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
