"""Hierarchical membership: cascade-on-add, org-wide read transparency,
at-level write gating, and the pod service registry (app/routers/projects.py,
pods.py, resources.py, permissions.py).

Driven through the real app with FastAPI's TestClient — no external network. Run:
    cd backend && .venv/bin/python -m pytest tests/test_membership.py -q
or standalone:
    cd backend && .venv/bin/python tests/test_membership.py
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


def _user():
    """Create a fresh signed-in user; return (headers, user_id, email)."""
    _n[0] += 1
    email = f"mem{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Member {_n[0]}"})
    assert r.status_code < 400, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = c.get("/api/auth/me", headers=h)
    assert me.status_code == 200, me.text
    return h, me.json()["id"], email


def _org(h):
    _n[0] += 1
    r = c.post("/api/orgs", json={"name": f"Org {_n[0]} {os.getpid()}"}, headers=h)
    assert r.status_code < 400, r.text
    return r.json()["slug"]


def _project(h, slug, name="Proj"):
    r = c.post(f"/api/orgs/{slug}/projects", json={"name": name}, headers=h)
    assert r.status_code < 400, r.text
    return r.json()["id"]


def _pod(h, project_id, name="Pod"):
    r = c.post(f"/api/projects/{project_id}/pods", json={"name": name}, headers=h)
    assert r.status_code < 400, r.text
    return r.json()["id"]


def _make_resource(h, scope_type, scope_id):
    return c.post(
        "/api/resources",
        json={"type": "NOTE", "title": "t", "scope_type": scope_type, "scope_id": scope_id},
        headers=h,
    )


# --------------------------------------------------------------------------


def test_add_project_member_by_email_cascades_to_org():
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    out_h, out_id, out_email = _user()

    # outsider is NOT yet an org member → can't read org resources
    assert c.get(f"/api/orgs/{slug}/resources", headers=out_h).status_code == 403

    # add by email to the project → cascades org membership
    r = c.post(f"/api/projects/{p1}/members", json={"email": out_email}, headers=owner_h)
    assert r.status_code < 400, r.text
    assert r.json()["user_id"] == out_id

    # now an org member: org-gated read works
    assert c.get(f"/api/orgs/{slug}/resources", headers=out_h).status_code == 200


def test_org_member_reads_other_projects_but_cannot_write():
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    p2 = _project(owner_h, slug, "P2")
    pod1 = _pod(owner_h, p1)

    out_h, _, out_email = _user()
    # make the outsider an org member by adding to p2 (not p1)
    c.post(f"/api/projects/{p2}/members", json={"email": out_email}, headers=owner_h)

    # READ transparency: can view p1 (not a member) and pod1
    assert c.get(f"/api/orgs/{slug}/projects/{p1}", headers=out_h).status_code == 200
    assert c.get(f"/api/projects/{p1}/pods", headers=out_h).status_code == 200
    assert c.get(f"/api/projects/{p1}/pods/{pod1}", headers=out_h).status_code == 200
    assert c.get(f"/api/projects/{p1}/resources", headers=out_h).status_code == 200

    # WRITE gating: cannot push into p1 (not a member there)…
    assert _make_resource(out_h, "PROJECT", p1).status_code == 403
    # …but CAN push into p2 (a member) and at ORG level (org member)
    assert _make_resource(out_h, "PROJECT", p2).status_code < 400
    org_id = c.get(f"/api/orgs/{slug}", headers=out_h).json()["id"]
    assert _make_resource(out_h, "ORG", org_id).status_code < 400


def test_add_pod_member_cascades_to_project_and_org():
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    pod1 = _pod(owner_h, p1)
    newbie_h, newbie_id, newbie_email = _user()

    # brand-new user, not in the org at all
    assert c.get(f"/api/orgs/{slug}/resources", headers=newbie_h).status_code == 403

    r = c.post(f"/api/pods/{pod1}/members", json={"email": newbie_email}, headers=owner_h)
    assert r.status_code < 400, r.text

    # cascaded to org + project + pod
    assert c.get(f"/api/orgs/{slug}/resources", headers=newbie_h).status_code == 200       # org member
    assert _make_resource(newbie_h, "POD", pod1).status_code < 400                          # pod member → write
    assert _make_resource(newbie_h, "PROJECT", p1).status_code < 400                        # project member → write

    # idempotent: re-adding doesn't duplicate the pod membership
    c.post(f"/api/pods/{pod1}/members", json={"email": newbie_email}, headers=owner_h)
    members = c.get(f"/api/pods/{pod1}/members", headers=owner_h).json()
    assert sum(1 for m in members if m["user_id"] == newbie_id) == 1


def test_add_unknown_email_provisions_and_adds():
    """Adding an unknown email to a pod/project auto-provisions an account
    (temp password, must_change_password) and adds them — no org invite needed."""
    from app.database import SessionLocal
    from app.models import User

    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    pod1 = _pod(owner_h, p1)
    _n[0] += 1
    ghost = f"ghost{_n[0]}_{os.getpid()}@example.com"

    # add unknown email to the POD as ADMIN → provisions + cascades to project/org
    r = c.post(f"/api/pods/{pod1}/members", json={"email": ghost, "role": "ADMIN"}, headers=owner_h)
    assert r.status_code < 400, r.text
    assert r.json()["role"] == "ADMIN"

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == ghost).first()
        assert u is not None and u.must_change_password is True and u.password_hash
        ghost_id = u.id
    finally:
        db.close()

    # pod ADMIN, but only MEMBER at project + org (cascade adds shallower as MEMBER)
    pod_members = c.get(f"/api/pods/{pod1}/members", headers=owner_h).json()
    proj_members = c.get(f"/api/projects/{p1}/members", headers=owner_h).json()
    org_members = c.get(f"/api/orgs/{slug}/members", headers=owner_h).json()
    assert next(m for m in pod_members if m["user_id"] == ghost_id)["role"] == "ADMIN"
    assert next(m for m in proj_members if m["user_id"] == ghost_id)["role"] == "MEMBER"
    assert next(m for m in org_members if m["user_id"] == ghost_id)["role"] == "MEMBER"


def test_change_and_remove_pod_member_role():
    """A scope admin can promote/demote (ADMIN|MEMBER) and remove a member."""
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    pod1 = _pod(owner_h, p1)
    m_h, m_id, m_email = _user()
    c.post(f"/api/pods/{pod1}/members", json={"email": m_email, "role": "MEMBER"}, headers=owner_h)

    # promote to ADMIN
    up = c.patch(f"/api/pods/{pod1}/members/{m_id}", json={"role": "ADMIN"}, headers=owner_h)
    assert up.status_code < 400 and up.json()["role"] == "ADMIN"

    # remove
    assert c.delete(f"/api/pods/{pod1}/members/{m_id}", headers=owner_h).status_code < 400
    members = c.get(f"/api/pods/{pod1}/members", headers=owner_h).json()
    assert all(m["user_id"] != m_id for m in members)


def test_pod_service_registry_crud_and_access():
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    pod1 = _pod(owner_h, p1)
    base = f"/api/projects/{p1}/pods/{pod1}/services"

    # owner (pod OWNER) creates a service; secret_ref is a NAME, not a value
    r = c.post(base, json={
        "name": "Orders API", "kind": "DEPLOYED_API",
        "endpoint_url": "https://orders.example.com", "secret_ref": "ORDERS_API_KEY",
        "config": {"region": "us-central1"},
    }, headers=owner_h)
    assert r.status_code < 400, r.text
    svc = r.json()
    assert svc["kind"] == "DEPLOYED_API" and svc["secret_ref"] == "ORDERS_API_KEY"
    assert svc["config"]["region"] == "us-central1"

    # an org member who is NOT a pod member can VIEW but not CREATE
    out_h, _, out_email = _user()
    p2 = _project(owner_h, slug, "P2")
    c.post(f"/api/projects/{p2}/members", json={"email": out_email}, headers=owner_h)
    assert c.get(base, headers=out_h).status_code == 200
    assert len(c.get(base, headers=out_h).json()) == 1
    assert c.post(base, json={"name": "Nope"}, headers=out_h).status_code == 403

    # update + delete by the owner
    up = c.patch(f"{base}/{svc['id']}", json={"status": "paused"}, headers=owner_h)
    assert up.status_code < 400 and up.json()["status"] == "paused"
    assert c.delete(f"{base}/{svc['id']}", headers=owner_h).status_code < 400
    assert len(c.get(base, headers=owner_h).json()) == 0


def test_admin_table_edit_and_delete():
    # platform admin is required; promote a user directly in the DB
    from app.database import SessionLocal
    from app.models import User as U

    admin_h, admin_id, _ = _user()
    db = SessionLocal()
    try:
        db.get(U, admin_id).is_admin = True
        db.commit()
    finally:
        db.close()

    # a throwaway row to edit: a blog post
    cr = c.post("/api/admin/blog", json={"slug": f"t-{os.getpid()}-{_n[0]}", "title": "Hi", "date": "2026-06-18"}, headers=admin_h)
    assert cr.status_code < 400, cr.text
    post_id = cr.json()["id"]

    # edit the title via the generic table browser; id is ignored if sent
    up = c.patch(f"/api/admin/tables/blog_posts/{post_id}",
                 json={"updates": {"title": "Edited", "featured": True, "id": "hacked"}}, headers=admin_h)
    assert up.status_code < 400, up.text
    assert up.json()["title"] == "Edited" and up.json()["featured"] is True
    assert up.json()["id"] == post_id  # pk never reassigned

    # delete it
    assert c.delete(f"/api/admin/tables/blog_posts/{post_id}", headers=admin_h).status_code < 400
    assert c.delete(f"/api/admin/tables/blog_posts/{post_id}", headers=admin_h).status_code == 404

    # non-admin is locked out
    nob_h, _, _ = _user()
    assert c.get("/api/admin/tables", headers=nob_h).status_code == 403


def test_pod_member_cannot_delete_pod_but_admin_can():
    """A plain pod MEMBER must not be able to delete the pod (regression: they
    previously could). Pod owner / org admin still can."""
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    project_id = _project(owner_h, slug)
    pod_id = _pod(owner_h, project_id)

    # Add a second user as a plain pod MEMBER (cascades them into the org).
    member_h, member_id, member_email = _user()
    r = c.post(
        f"/api/pods/{pod_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers=owner_h,
    )
    assert r.status_code < 400, r.text

    # The member can still read/write the pod, but DELETE is forbidden.
    assert c.delete(f"/api/projects/{project_id}/pods/{pod_id}", headers=member_h).status_code == 403

    # The org admin / pod owner can delete it.
    assert c.delete(f"/api/projects/{project_id}/pods/{pod_id}", headers=owner_h).status_code < 400


def test_invite_unregistered_user_provisions_account_with_password_change_flag():
    """Inviting an email with no account creates a user flagged must_change_password."""
    from app.database import SessionLocal
    from app.models import User

    admin_h, _, _ = _user()
    slug = _org(admin_h)
    _n[0] += 1
    invitee_email = f"invitee{_n[0]}_{os.getpid()}@example.com"

    r = c.post(f"/api/orgs/{slug}/invite", json={"email": invitee_email, "role": "MEMBER"}, headers=admin_h)
    assert r.status_code < 400, r.text

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == invitee_email).first()
        assert u is not None, "invite should auto-provision an account"
        assert u.must_change_password is True
        assert u.password_hash, "a temp password should be set"
    finally:
        db.close()


def test_first_time_forced_change_then_normal_change():
    """Every new signup is flagged must_change_password. The first change is
    mandatory and skips current-password verification; once cleared, later
    changes require the correct current password."""
    _n[0] += 1
    email = f"pw{_n[0]}_{os.getpid()}@example.com"
    r = c.post("/api/auth/signup", json={"email": email, "password": "oldpassword1", "display_name": "PW"})
    assert r.json()["user"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # First (mandatory) change: no current password required, flag clears.
    ok = c.post("/api/auth/change-password", json={"new_password": "newpassword1"}, headers=h)
    assert ok.status_code < 400, ok.text
    assert ok.json()["must_change_password"] is False

    # new password works, old one doesn't
    assert c.post("/api/auth/login", json={"email": email, "password": "newpassword1"}).status_code < 400
    assert c.post("/api/auth/login", json={"email": email, "password": "oldpassword1"}).status_code == 401

    # A subsequent change now DOES require the correct current password.
    bad = c.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "third1234"}, headers=h)
    assert bad.status_code == 401, bad.text
    good = c.post("/api/auth/change-password", json={"current_password": "newpassword1", "new_password": "third1234"}, headers=h)
    assert good.status_code < 400, good.text


def test_publisher_can_add_public_resource_to_marketplace():
    """A registered publisher adds a resource at PUBLIC scope (no org) — it's
    public immediately and appears in the marketplace. Non-publishers can't."""
    h, _, _ = _user()

    # not a publisher yet → PUBLIC create is forbidden
    r = _make_resource(h, "PUBLIC", None)
    assert r.status_code == 403, r.text

    # register as a publisher, then it works
    assert c.post("/api/auth/become-publisher", headers=h).status_code < 400
    r = c.post(
        "/api/resources",
        json={"type": "SKILL", "title": "Public Skill", "scope_type": "PUBLIC", "scope_id": None},
        headers=h,
    )
    assert r.status_code < 400, r.text
    body = r.json()
    assert body["is_public"] is True and body["scope_type"] == "PUBLIC"

    # visible on the public marketplace (no auth needed)
    market = c.get("/api/public/resources").json()
    assert any(x["id"] == body["id"] for x in market)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
