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
    r = c.post(f"/api/orgs/{slug}/projects/{p1}/members", json={"email": out_email}, headers=owner_h)
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
    c.post(f"/api/orgs/{slug}/projects/{p2}/members", json={"email": out_email}, headers=owner_h)

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

    r = c.post(f"/api/projects/{p1}/pods/{pod1}/members", json={"email": newbie_email}, headers=owner_h)
    assert r.status_code < 400, r.text

    # cascaded to org + project + pod
    assert c.get(f"/api/orgs/{slug}/resources", headers=newbie_h).status_code == 200       # org member
    assert _make_resource(newbie_h, "POD", pod1).status_code < 400                          # pod member → write
    assert _make_resource(newbie_h, "PROJECT", p1).status_code < 400                        # project member → write

    # idempotent: re-adding doesn't duplicate the pod membership
    c.post(f"/api/projects/{p1}/pods/{pod1}/members", json={"email": newbie_email}, headers=owner_h)
    members = c.get(f"/api/projects/{p1}/pods/{pod1}/members", headers=owner_h).json()
    assert sum(1 for m in members if m["user_id"] == newbie_id) == 1


def test_add_member_unknown_user_404():
    owner_h, _, _ = _user()
    slug = _org(owner_h)
    p1 = _project(owner_h, slug, "P1")
    r = c.post(f"/api/orgs/{slug}/projects/{p1}/members", json={"email": "ghost-nobody@example.com"}, headers=owner_h)
    assert r.status_code == 404


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
    c.post(f"/api/orgs/{slug}/projects/{p2}/members", json={"email": out_email}, headers=owner_h)
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


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
