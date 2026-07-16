"""Hive (HR/directory) integration — connect, fetch→stage, review, selective
apply (members/projects/groups), dedup, and offboarding.

    cd backend && .venv/bin/python -m pytest tests/test_hive_integration.py -q
"""

from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import hive  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    HiveLink,
    Organization,
    OrgIntegration,
    OrgMember,
    Pod,
    PodMember,
    Project,
    ProjectMember,
    User,
)
from app.integrations import get_credentials  # noqa: E402
from app.routers import integrations as integ_router  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
_n = [0]

HIVE_TOKEN = "hive_faketoken_0123456789ABCDEF"

# Mutable canned Hive directory so a test can simulate a leaver.
DIRECTORY = {
    "employees": [
        {"member_id": "m1", "workspace_email": "alice@think41.com", "display_name": "Alice", "is_active": True, "department": "Eng"},
        {"member_id": "m2", "workspace_email": "bob@think41.com", "display_name": "Bob", "is_active": True},
        {"member_id": "m3", "workspace_email": "carol@think41.com", "display_name": "Carol", "is_active": True},
    ],
    "projects": [
        {"id": "p1", "name": "Apollo", "code": "AP", "status": "active", "tech_stack": ["react"], "pm_display_name": "Alice"},
    ],
    "allocations": [
        {"employee_id": "m1", "project_id": "p1", "percentage": 100, "is_active": True},
        {"employee_id": "m2", "project_id": "p1", "percentage": 50, "is_active": True},
    ],
    "groups": [
        {"id": "g1", "name": "Platform", "is_active": True},
    ],
    "group_members": {"g1": [{"employee_id": "m2"}, {"employee_id": "m3"}]},
}


class FakeTransport:
    """Stands in for the MCP HTTP transport — returns canned tool results so the
    real HiveClient normalizers run with no network."""

    def call_tool(self, tool, arguments):
        if tool == "list_employees":
            return {"items": DIRECTORY["employees"], "next_cursor": None}
        if tool == "list_projects":
            return {"items": DIRECTORY["projects"]}
        if tool == "list_allocations":
            return {"items": DIRECTORY["allocations"]}
        if tool == "list_groups":
            return {"items": DIRECTORY["groups"], "next_cursor": None}
        if tool == "list_group_members":
            gid = arguments.get("group_id")
            return {"items": DIRECTORY["group_members"].get(gid, []), "next_cursor": None}
        return {}


@pytest.fixture(autouse=True)
def _stub_hive(monkeypatch):
    monkeypatch.setattr(hive, "validate_connection", lambda creds, tenant: {"account_label": tenant})
    monkeypatch.setattr(integ_router, "hive_client", lambda db, conn: hive.HiveClient(FakeTransport(), "think41"))


def _user():
    _n[0] += 1
    email = f"hive{_n[0]}_{os.getpid()}@example.com"
    s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Hv {_n[0]}"}).json()
    r = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    u = db.get(User, uid)
    u.plan = "ENTERPRISE"
    db.commit()
    db.close()
    return h, uid


def _org(h, plan="ENTERPRISE"):
    _n[0] += 1
    slug = c.post("/api/orgs", json={"name": f"HiveOrg {_n[0]} {os.getpid()}"}, headers=h).json()["slug"]
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.slug == slug).first()
    org.plan = plan
    db.commit()
    db.close()
    return slug


def _connect_hive(h, slug):
    # The paste-token path goes through the generic connect endpoint; `account`
    # carries the Hive tenant code.
    return c.post(
        f"/api/orgs/{slug}/integrations/hive/connect",
        json={"token": HIVE_TOKEN, "account": "think41", "auth_method": "service_token"},
        headers=h,
    )


def test_hive_card_gated_to_enterprise():
    h, _ = _user()
    pro = _org(h, plan="PRO")
    keys = {p["key"] for p in c.get(f"/api/orgs/{pro}/integrations/providers", headers=h).json()}
    assert "hive" not in keys  # PRO is below the provider's ENTERPRISE min_plan
    ent = _org(h, plan="ENTERPRISE")
    keys = {p["key"] for p in c.get(f"/api/orgs/{ent}/integrations/providers", headers=h).json()}
    assert "hive" in keys


def test_connect_stores_encrypted_and_no_leak():
    h, _ = _user()
    slug = _org(h)
    r = _connect_hive(h, slug)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    # token never leaves the server
    assert HIVE_TOKEN not in r.text
    db = SessionLocal()
    org = db.query(Organization).filter_by(slug=slug).first()
    conn = db.query(OrgIntegration).filter_by(org_id=org.id, provider_key="hive").first()
    assert get_credentials(conn)["access_token"] == HIVE_TOKEN
    assert (conn.config or {}).get("tenant") == "think41"
    db.close()


def test_fetch_stages_without_adding_members():
    h, _ = _user()
    slug = _org(h)
    _connect_hive(h, slug)
    summary = c.post(f"/api/orgs/{slug}/integrations/hive/fetch", headers=h).json()
    assert summary["members"] == 3 and summary["projects"] == 1 and summary["groups"] == 1
    assert summary["allocations"] == 2
    # Fetch must NOT add org members (only the owner exists).
    db = SessionLocal()
    org = db.query(Organization).filter_by(slug=slug).first()
    assert db.query(OrgMember).filter_by(org_id=org.id).count() == 1
    db.close()
    staged = c.get(f"/api/orgs/{slug}/integrations/hive/staged", headers=h).json()
    assert staged["counts"]["pending"] == 5  # 3 people + 1 project + 1 group
    assert len(staged["groups"]["employee"]) == 3


def test_apply_all_creates_members_projects_pods_and_dedups():
    h, _ = _user()
    slug = _org(h)
    _connect_hive(h, slug)
    c.post(f"/api/orgs/{slug}/integrations/hive/fetch", headers=h)
    r = c.post(f"/api/orgs/{slug}/integrations/hive/apply", json={"scope": "all"}, headers=h).json()
    assert r["members_added"] == 3
    assert r["projects_created"] == 1
    assert r["pods_created"] == 1

    db = SessionLocal()
    org = db.query(Organization).filter_by(slug=slug).first()
    emails = {m.user.email for m in db.query(OrgMember).filter_by(org_id=org.id).all()}
    assert {"alice@think41.com", "bob@think41.com", "carol@think41.com"} <= emails
    apollo = db.query(Project).filter_by(org_id=org.id, name="Apollo").first()
    assert apollo is not None
    proj_emails = {m.user.email for m in db.query(ProjectMember).filter_by(project_id=apollo.id).all()}
    assert proj_emails == {"alice@think41.com", "bob@think41.com"}  # from allocations
    pod = db.query(Pod).join(Project, Pod.project_id == Project.id).filter(
        Project.org_id == org.id, Pod.name == "Platform").first()
    assert pod is not None
    pod_emails = {m.user.email for m in db.query(PodMember).filter_by(pod_id=pod.id).all()}
    assert pod_emails == {"bob@think41.com", "carol@think41.com"}  # group members
    db.close()

    # Re-apply is idempotent (dedup by HiveLink / email).
    again = c.post(f"/api/orgs/{slug}/integrations/hive/apply", json={"scope": "all"}, headers=h).json()
    assert again["members_added"] == 0 and again["projects_created"] == 0 and again["pods_created"] == 0


def test_selective_apply_members_only():
    h, _ = _user()
    slug = _org(h)
    _connect_hive(h, slug)
    c.post(f"/api/orgs/{slug}/integrations/hive/fetch", headers=h)
    r = c.post(f"/api/orgs/{slug}/integrations/hive/apply", json={"scope": "members"}, headers=h).json()
    assert r["members_added"] == 3 and r["projects_created"] == 0 and r["pods_created"] == 0
    db = SessionLocal()
    org = db.query(Organization).filter_by(slug=slug).first()
    assert db.query(Project).filter_by(org_id=org.id).count() == 0  # no structure
    db.close()


def test_offboarding_removes_only_sync_created_leavers():
    h, _ = _user()
    slug = _org(h)
    _connect_hive(h, slug)
    c.post(f"/api/orgs/{slug}/integrations/hive/fetch", headers=h)
    c.post(f"/api/orgs/{slug}/integrations/hive/apply", json={"scope": "all"}, headers=h)

    # Carol leaves: mark inactive in the directory + drop her from the group.
    orig_emps = [dict(e) for e in DIRECTORY["employees"]]
    orig_gm = {k: list(v) for k, v in DIRECTORY["group_members"].items()}
    try:
        for e in DIRECTORY["employees"]:
            if e["member_id"] == "m3":
                e["is_active"] = False
        DIRECTORY["group_members"]["g1"] = [{"employee_id": "m2"}]
        c.post(f"/api/orgs/{slug}/integrations/hive/fetch", headers=h)
        staged = c.get(f"/api/orgs/{slug}/integrations/hive/staged?status=removed", headers=h).json()
        removed_refs = {e["external_ref"] for e in staged["groups"]["employee"]}
        assert "m3" in removed_refs
        r = c.post(f"/api/orgs/{slug}/integrations/hive/apply",
                   json={"scope": "members", "offboard": True}, headers=h).json()
        assert r["offboarded"] == 1
        db = SessionLocal()
        org = db.query(Organization).filter_by(slug=slug).first()
        emails = {m.user.email for m in db.query(OrgMember).filter_by(org_id=org.id).all()}
        assert "carol@think41.com" not in emails
        assert "alice@think41.com" in emails and "bob@think41.com" in emails
        db.close()
    finally:
        DIRECTORY["employees"] = orig_emps
        DIRECTORY["group_members"] = orig_gm
