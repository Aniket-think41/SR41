"""Plan tiers, quotas, and entitlement enforcement (app/entitlements.py + gates
in orgs.py / resources.py / admin.py). Spec §2.

    cd backend && .venv/bin/python -m pytest tests/test_entitlements.py -q
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
from app.entitlements import normalize_plan, plan_at_least, spec_for  # noqa: E402

c = TestClient(app)
_n = [0]


def _user(plan="FREE"):
    _n[0] += 1
    email = f"ent{_n[0]}_{os.getpid()}@example.com"
    _s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Ent {_n[0]}"})
    assert _s.status_code < 400, _s.text
    r = c.post("/api/auth/verify-email", json={"email": email, "code": _s.json()["dev_otp"]})
    assert r.status_code < 400, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    if plan != "FREE":
        _set_plan(uid, plan)
    return h, uid


def _admin():
    """A platform admin (needed to exercise the grant endpoints)."""
    h, uid = _user()
    db = SessionLocal()
    try:
        db.get(User, uid).is_admin = True
        db.commit()
        username = db.get(User, uid).username
    finally:
        db.close()
    return h, username


def _set_plan(user_id, plan):
    db = SessionLocal()
    try:
        db.get(User, user_id).plan = plan
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Pure logic
# --------------------------------------------------------------------------- #

def test_plan_normalization_and_ordering():
    assert normalize_plan(None) == "FREE"
    assert normalize_plan("premium") == "ENTERPRISE"  # legacy tier maps to top
    assert normalize_plan("garbage") == "FREE"
    assert plan_at_least("ENTERPRISE", "PRO")
    assert plan_at_least("PRO", "PRO")
    assert not plan_at_least("FREE", "PRO")
    assert spec_for("FREE").resource_quota == 100
    assert spec_for("ENTERPRISE").resource_quota is None
    assert spec_for("FREE").mcp_included is False
    assert spec_for("PRO").mcp_included is True


# --------------------------------------------------------------------------- #
# Org-creation quota
# --------------------------------------------------------------------------- #

def test_free_user_cannot_create_org():
    h, _ = _user("FREE")
    r = c.post("/api/orgs", json={"name": f"FreeOrg {os.getpid()}"}, headers=h)
    assert r.status_code == 402, r.text
    assert r.json()["error"]["code"] == "PAYMENT_REQUIRED"


def test_pro_user_capped_at_two_orgs():
    h, _ = _user("PRO")
    assert c.post("/api/orgs", json={"name": f"P1 {os.getpid()}{_n[0]}"}, headers=h).status_code < 400
    assert c.post("/api/orgs", json={"name": f"P2 {os.getpid()}{_n[0]}"}, headers=h).status_code < 400
    third = c.post("/api/orgs", json={"name": f"P3 {os.getpid()}{_n[0]}"}, headers=h)
    assert third.status_code == 402, third.text


def test_enterprise_user_unlimited_orgs():
    h, _ = _user("ENTERPRISE")
    for i in range(3):
        r = c.post("/api/orgs", json={"name": f"E{i} {os.getpid()}{_n[0]}"}, headers=h)
        assert r.status_code < 400, r.text


# --------------------------------------------------------------------------- #
# Entitlement surfaces
# --------------------------------------------------------------------------- #

def test_me_entitlements_reports_plan_and_usage():
    h, _ = _user("PRO")
    ent = c.get("/api/auth/me/entitlements", headers=h)
    assert ent.status_code == 200, ent.text
    body = ent.json()
    assert body["plan"] == "PRO"
    assert body["max_orgs"] == 2
    assert body["mcp_included"] is True
    assert body["publisher_resource_quota"] == 500


def test_public_plans_endpoint():
    r = c.get("/api/public/plans")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert keys == {"FREE", "PRO", "ENTERPRISE"}


# --------------------------------------------------------------------------- #
# Admin plan grant
# --------------------------------------------------------------------------- #

def test_admin_can_grant_plan_and_unlock_org_creation():
    admin_h, _ = _admin()
    h, uid = _user("FREE")
    # blocked while FREE
    assert c.post("/api/orgs", json={"name": f"NG {os.getpid()}{_n[0]}"}, headers=h).status_code == 402
    # admin grants PRO
    db = SessionLocal()
    username = db.get(User, uid).username
    db.close()
    g = c.patch(f"/api/admin/users/{username}/plan", json={"plan": "PRO"}, headers=admin_h)
    assert g.status_code == 200, g.text
    assert g.json()["plan"] == "PRO"
    # now allowed
    assert c.post("/api/orgs", json={"name": f"OK {os.getpid()}{_n[0]}"}, headers=h).status_code < 400


def test_non_admin_cannot_grant_plan():
    h, uid = _user("FREE")
    db = SessionLocal()
    username = db.get(User, uid).username
    db.close()
    r = c.patch(f"/api/admin/users/{username}/plan", json={"plan": "ENTERPRISE"}, headers=h)
    assert r.status_code == 403, r.text


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
