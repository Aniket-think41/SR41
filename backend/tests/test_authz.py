"""Broken-access-control regressions (spec §4.5): management/destructive ops
require the right ROLE at the right SCOPE, not just membership.

    cd backend && .venv/bin/python -m pytest tests/test_authz.py -q
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
    email = f"az{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"AZ {_n[0]}"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    db.get(User, uid).plan = "ENTERPRISE"
    db.commit()
    db.close()
    return h, uid, email


def _setup():
    """Owner with an org + two projects; a plain MEMBER added to P1 only."""
    ah, _, _ = _user()
    slug = c.post("/api/orgs", json={"name": f"AZOrg {_n[0]} {os.getpid()}"}, headers=ah).json()["slug"]
    p1 = c.post(f"/api/orgs/{slug}/projects", json={"name": "P1"}, headers=ah).json()["id"]
    p2 = c.post(f"/api/orgs/{slug}/projects", json={"name": "P2"}, headers=ah).json()["id"]
    mh, _, me = _user()
    c.post(f"/api/projects/{p1}/members", json={"email": me, "role": "MEMBER"}, headers=ah)
    return ah, mh, slug, p1, p2


def test_non_project_member_cannot_create_pod():
    ah, mh, slug, p1, p2 = _setup()
    # member of P1 is an org member but NOT a member of P2 → blocked from P2
    r = c.post(f"/api/projects/{p2}/pods", json={"name": "nope"}, headers=mh)
    assert r.status_code == 403, r.text


def test_plain_member_cannot_delete_project():
    ah, mh, slug, p1, p2 = _setup()
    r = c.delete(f"/api/orgs/{slug}/projects/{p1}", headers=mh)
    assert r.status_code == 403, r.text
    # the project still exists
    assert c.get(f"/api/orgs/{slug}/projects/{p1}", headers=ah).status_code == 200


def test_plain_member_cannot_edit_project_settings():
    ah, mh, slug, p1, p2 = _setup()
    r = c.patch(f"/api/orgs/{slug}/projects/{p1}", json={"visibility": "PUBLIC"}, headers=mh)
    assert r.status_code == 403, r.text


def test_project_admin_can_manage_project():
    ah, mh, slug, p1, p2 = _setup()
    # promote the member to project admin
    db = SessionLocal()
    from app.models import ProjectMember

    uid = c.get("/api/auth/me", headers=mh).json()["id"]
    m = db.query(ProjectMember).filter(ProjectMember.project_id == p1, ProjectMember.user_id == uid).first()
    m.role = "ADMIN"
    db.commit()
    db.close()
    assert c.patch(f"/api/orgs/{slug}/projects/{p1}", json={"description": "x"}, headers=mh).status_code == 200
    assert c.delete(f"/api/orgs/{slug}/projects/{p1}", headers=mh).status_code == 200


def test_org_admin_can_manage_any_project():
    ah, mh, slug, p1, p2 = _setup()
    assert c.patch(f"/api/orgs/{slug}/projects/{p2}", json={"description": "y"}, headers=ah).status_code == 200
    assert c.delete(f"/api/orgs/{slug}/projects/{p2}", headers=ah).status_code == 200


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
