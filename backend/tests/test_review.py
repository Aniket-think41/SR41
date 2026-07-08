"""Resource review workflow (app/review.py + gates in resources.py / admin.py /
orgs.py / public.py). Spec §3.

    cd backend && .venv/bin/python -m pytest tests/test_review.py -q
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
    email = f"rev{_n[0]}_{os.getpid()}@example.com"
    _s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Rev {_n[0]}"})
    assert _s.status_code < 400, _s.text
    r = c.post("/api/auth/verify-email", json={"email": email, "code": _s.json()["dev_otp"]})
    assert r.status_code < 400, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        u.plan = plan
        u.is_admin = admin
        if publisher:
            u.is_publisher = True
        username = u.username
        db.commit()
    finally:
        db.close()
    return h, uid, username


def _org(h):
    _n[0] += 1
    r = c.post("/api/orgs", json={"name": f"RevOrg {_n[0]} {os.getpid()}"}, headers=h)
    assert r.status_code < 400, r.text
    return r.json()["slug"]


# --------------------------------------------------------------------------- #
# Publisher content → platform admin review
# --------------------------------------------------------------------------- #

def test_publisher_content_is_owner_governed_no_review():
    """A personal (PUBLIC-scope) resource is owner-governed: created UNPUBLISHED
    with no review, and publishing it goes live immediately — no admin gate."""
    pub_h, _, _ = _user(plan="PRO", publisher=True)
    r = c.post(
        "/api/resources",
        json={"type": "SKILL", "title": "Queued Skill", "scope_type": "PUBLIC", "scope_id": None},
        headers=pub_h,
    )
    assert r.status_code < 400, r.text
    rid = r.json()["id"]
    # Default: an unpublished private draft the author owns — NOT pending review.
    assert r.json()["is_public"] is False
    assert r.json()["approval_status"] == "approved"
    assert not any(x["id"] == rid for x in c.get("/api/public/resources").json())
    assert c.get(f"/api/public/resources/{rid}").status_code == 404

    # The author publishes → live immediately, no reviewer needed.
    pub = c.post(f"/api/resources/{rid}/publish", headers=pub_h)
    assert pub.status_code == 200, pub.text
    assert pub.json()["is_public"] is True
    assert pub.json()["approval_status"] == "approved"
    assert any(x["id"] == rid for x in c.get("/api/public/resources").json())
    assert c.get(f"/api/public/resources/{rid}").status_code == 200


def test_platform_admin_can_moderate_public_content():
    """Publisher content self-publishes, but a platform admin keeps a takedown
    backstop (reject → unpublished)."""
    pub_h, _, _ = _user(plan="PRO", publisher=True)
    rid = c.post(
        "/api/resources",
        json={"type": "NOTE", "title": "Live Note", "scope_type": "PUBLIC", "scope_id": None},
        headers=pub_h,
    ).json()["id"]
    c.post(f"/api/resources/{rid}/publish", headers=pub_h)
    assert any(x["id"] == rid for x in c.get("/api/public/resources").json())

    admin_h, _, _ = _user(admin=True)
    rj = c.post(f"/api/resources/{rid}/review", json={"decision": "reject", "note": "policy"}, headers=admin_h)
    assert rj.status_code == 200, rj.text
    assert rj.json()["approval_status"] == "rejected"
    assert rj.json()["is_public"] is False
    assert not any(x["id"] == rid for x in c.get("/api/public/resources").json())


def test_org_content_reject_notifies_and_edit_resubmits():
    """Org-owned content still goes through org-admin review: a member's publish
    pends, a rejection notifies + unpublishes, and editing resubmits."""
    admin_h, _, _ = _user(publisher=True)  # org owner/admin
    slug = _org(admin_h)
    org_id = c.get(f"/api/orgs/{slug}", headers=admin_h).json()["id"]
    proj = c.post(f"/api/orgs/{slug}/projects", json={"name": "P"}, headers=admin_h).json()["id"]
    member_h, _, _ = _user(publisher=True)
    memail = c.get("/api/auth/me", headers=member_h).json()["email"]
    c.post(f"/api/projects/{proj}/members", json={"email": memail, "role": "MEMBER"}, headers=admin_h)

    rid = c.post(
        "/api/resources",
        json={"type": "NOTE", "title": "OrgDoc", "scope_type": "ORG", "scope_id": org_id},
        headers=member_h,
    ).json()["id"]
    pub = c.post(f"/api/resources/{rid}/publish", headers=member_h)  # member isn't a reviewer → pending
    assert pub.json()["approval_status"] == "pending"

    rj = c.post(
        f"/api/resources/{rid}/review",
        json={"decision": "reject", "note": "needs more detail"},
        headers=admin_h,
    )
    assert rj.status_code == 200, rj.text
    assert rj.json()["approval_status"] == "rejected"
    assert rj.json()["review_note"] == "needs more detail"
    assert rj.json()["is_public"] is False

    # author got a rejection notification carrying the reason
    notifs = c.get("/api/notifications", headers=member_h).json()
    assert any(n["verb"] == "rejected" and n["meta"] == "needs more detail" for n in notifs)

    # republish → back into the queue (pending)
    re = c.post(f"/api/resources/{rid}/publish", headers=member_h)
    assert re.json()["approval_status"] == "pending"


# --------------------------------------------------------------------------- #
# Org content → org admin review
# --------------------------------------------------------------------------- #

def test_org_member_publish_pends_until_org_admin_approves():
    admin_h, _, _ = _user(publisher=True)  # org owner/admin
    slug = _org(admin_h)
    org_id = c.get(f"/api/orgs/{slug}", headers=admin_h).json()["id"]

    # a non-admin member (added via project cascade → org MEMBER)
    proj = c.post(f"/api/orgs/{slug}/projects", json={"name": "P"}, headers=admin_h).json()["id"]
    member_h, _, _ = _user(publisher=True)
    memail = c.get("/api/auth/me", headers=member_h).json()["email"]
    c.post(f"/api/projects/{proj}/members", json={"email": memail, "role": "MEMBER"}, headers=admin_h)

    # member authors an ORG resource and publishes it → pending (not a reviewer)
    r = c.post(
        "/api/resources",
        json={"type": "NOTE", "title": "MemberDoc", "scope_type": "ORG", "scope_id": org_id},
        headers=member_h,
    )
    rid = r.json()["id"]
    pub = c.post(f"/api/resources/{rid}/publish", headers=member_h)
    assert pub.status_code < 400, pub.text
    assert pub.json()["approval_status"] == "pending"

    # it shows in the org admin's review queue
    queue = c.get(f"/api/orgs/{slug}/review-queue", headers=admin_h).json()
    assert any(x["id"] == rid for x in queue)

    # a plain member can't approve; the org admin can
    assert c.post(f"/api/resources/{rid}/review", json={"decision": "approve"}, headers=member_h).status_code == 403
    ap = c.post(f"/api/resources/{rid}/review", json={"decision": "approve"}, headers=admin_h)
    assert ap.status_code == 200, ap.text
    assert ap.json()["approval_status"] == "approved"


def test_org_review_queue_lists_pending_org_content():
    admin_h, _, _ = _user()
    slug = _org(admin_h)
    org_id = c.get(f"/api/orgs/{slug}", headers=admin_h).json()["id"]
    q = c.get(f"/api/orgs/{slug}/review-queue", headers=admin_h)
    assert q.status_code == 200, q.text
    assert isinstance(q.json(), list)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
