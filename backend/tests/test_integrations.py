"""Org GitHub integration — gating, connect (encrypted, no leak), config, disconnect.

    cd backend && .venv/bin/python -m pytest tests/test_integrations.py -q
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

from app import github  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Organization, OrgIntegration, User  # noqa: E402
from app.integrations import get_credentials  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
_n = [0]

FAKE_TOKEN = "ghp_faketoken_0123456789ABCDEF"


def _user():
    _n[0] += 1
    email = f"int{_n[0]}_{os.getpid()}@example.com"
    s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Int {_n[0]}"}).json()
    r = c.post("/api/auth/verify-email", json={"email": email, "code": s["dev_otp"]})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    u = db.get(User, uid)
    u.plan = "ENTERPRISE"
    db.commit()
    db.close()
    return h, uid


def _org(h, plan="PRO"):
    _n[0] += 1
    slug = c.post("/api/orgs", json={"name": f"IntOrg {_n[0]} {os.getpid()}"}, headers=h).json()["slug"]
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.slug == slug).first()
    org.plan = plan
    db.commit()
    db.close()
    return slug


@pytest.fixture(autouse=True)
def _stub_github(monkeypatch):
    monkeypatch.setattr(
        github, "validate_token",
        lambda token: {"login": "acme", "name": "Acme", "type": "Organization"},
    )


def test_free_org_has_no_integrations():
    h, _ = _user()
    slug = _org(h, plan="FREE")
    r = c.get(f"/api/orgs/{slug}/integrations/providers", headers=h)
    assert r.status_code == 403, r.text


def test_pro_org_sees_github_card_not_connected():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.get(f"/api/orgs/{slug}/integrations/providers", headers=h)
    assert r.status_code == 200, r.text
    keys = {p["key"]: p for p in r.json()}
    assert "github" in keys
    assert keys["github"]["connected"] is False
    assert keys["github"]["auth_type"] == "pat"


def test_connect_encrypts_and_never_leaks_token():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.post(
        f"/api/orgs/{slug}/integrations/github/connect",
        json={"token": FAKE_TOKEN}, headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    conn = body["connection"]
    assert conn["account_label"] == "acme"
    assert conn["token_hint"] == FAKE_TOKEN[-4:]
    # The raw token must never appear anywhere in the response.
    assert FAKE_TOKEN not in r.text

    # Stored ciphertext != plaintext, but decrypts back to the token.
    db = SessionLocal()
    row = db.query(OrgIntegration).filter(OrgIntegration.provider_key == "github").order_by(OrgIntegration.created_at.desc()).first()
    assert row.credentials_enc and FAKE_TOKEN not in row.credentials_enc
    assert get_credentials(row)["token"] == FAKE_TOKEN
    db.close()


def test_non_admin_member_cannot_connect():
    admin_h, _ = _user()
    slug = _org(admin_h, plan="PRO")
    # invite a second user as MEMBER and accept
    member_h, member_uid = _user()
    member_email = c.get("/api/auth/me", headers=member_h).json()["email"]
    inv = c.post(f"/api/orgs/{slug}/invite", json={"email": member_email, "role": "MEMBER"}, headers=admin_h).json()
    c.post(f"/api/orgs/{slug}/join/{inv['token']}", headers=member_h)
    r = c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=member_h)
    assert r.status_code == 403, r.text


def test_github_search_uses_stored_token(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN, "account": "acme"}, headers=h)

    seen = {}

    def fake_search(query, token=None, account=None, per_page=30):
        seen["token"] = token
        seen["account"] = account
        return [{"full_name": f"{account}/hit", "name": "hit", "owner": account, "stars": 1,
                 "description": query, "private": False, "topics": [], "language": None,
                 "html_url": "", "default_branch": "main", "archived": False, "fork": False,
                 "updated_at": None}]

    monkeypatch.setattr(github, "search_repositories", fake_search)
    r = c.get(f"/api/orgs/{slug}/integrations/github/search?q=vector", headers=h)
    assert r.status_code == 200, r.text
    # The stored (decrypted) token and connected account reached the GitHub call.
    assert seen["token"] == FAKE_TOKEN
    assert seen["account"] == "acme"
    assert r.json()[0]["full_name"] == "acme/hit"


def test_github_search_requires_connection():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.get(f"/api/orgs/{slug}/integrations/github/search?q=x", headers=h)
    assert r.status_code == 422, r.text


def test_config_patch_and_disconnect():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)

    patched = c.patch(
        f"/api/orgs/{slug}/integrations/github",
        json={"config": {"sync_mode": "read_only"}}, headers=h,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["connection"]["config"]["sync_mode"] == "read_only"

    d = c.delete(f"/api/orgs/{slug}/integrations/github", headers=h)
    assert d.status_code == 200, d.text
    after = c.get(f"/api/orgs/{slug}/integrations/github", headers=h).json()
    assert after["connected"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
