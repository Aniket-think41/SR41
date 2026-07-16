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
from app.models import Organization, OrgIntegration, Resource, User  # noqa: E402
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
    # Scopes derived from the token so tests can exercise capability gating:
    # a token containing "limited" grants only read:user (no repo → no write).
    def fake_validate(token):
        scopes = ["read:user"] if "limited" in token else ["repo", "read:org", "read:user"]
        return {"login": "acme", "name": "Acme", "type": "Organization",
                "avatar_url": "https://x/a.png", "html_url": "https://github.com/acme",
                "scopes": scopes}

    monkeypatch.setattr(github, "validate_token", fake_validate)


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

    def fake_search(query, token=None, account=None, per_page=30, page=1):
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


def _caps(provider_body):
    return {c["key"]: c["enabled"] for c in provider_body["connection"]["capabilities"]}


def test_connect_detects_scopes_and_capabilities():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    body = r.json()
    conn = body["connection"]
    assert conn["auth_method"] == "classic_pat"
    assert set(conn["scopes"]) == {"repo", "read:org", "read:user"}
    assert conn["account_type"] == "Organization"
    assert conn["account_url"] == "https://github.com/acme"
    caps = _caps(body)
    # repo scope → private read + write enabled; always-on read/search enabled.
    assert caps["read_private"] and caps["write"] and caps["read_public"] and caps["search"]
    # provider advertises the classic_pat auth method
    assert any(m["key"] == "classic_pat" for m in body["auth_methods"])


def test_limited_token_disables_write_then_sync_enables_it(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    # Connect with a limited token → write capability off.
    c.post(f"/api/orgs/{slug}/integrations/github/connect",
           json={"token": "ghp_limited_0123456789"}, headers=h)
    got = c.get(f"/api/orgs/{slug}/integrations/github", headers=h).json()
    assert _caps(got)["write"] is False

    # Simulate the admin broadening the SAME token's scopes on GitHub, then Sync.
    monkeypatch.setattr(github, "validate_token", lambda token: {
        "login": "acme", "name": "Acme", "type": "Organization",
        "avatar_url": "", "html_url": "https://github.com/acme",
        "scopes": ["repo", "read:org", "read:user"]})
    synced = c.post(f"/api/orgs/{slug}/integrations/github/sync", headers=h)
    assert synced.status_code == 200, synced.text
    assert _caps(synced.json())["write"] is True
    assert synced.json()["connection"]["last_synced_at"]


def test_sync_requires_connection():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.post(f"/api/orgs/{slug}/integrations/github/sync", headers=h)
    assert r.status_code == 404, r.text


def test_unknown_auth_method_rejected():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.post(f"/api/orgs/{slug}/integrations/github/connect",
               json={"token": FAKE_TOKEN, "auth_method": "carrier-pigeon"}, headers=h)
    assert r.status_code == 422, r.text


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


def _org_resource(h, slug, title="My Skill", public=False):
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    rid = c.post("/api/resources", json={
        "type": "SKILL", "title": title, "content_md": "# hi", "scope_type": "ORG", "scope_id": org_id,
    }, headers=h).json()["id"]
    if public:  # flip visibility directly — we're testing the GitHub mirror, not the publish flow
        db = SessionLocal()
        r = db.get(Resource, rid)
        r.is_public = True
        db.commit()
        db.close()
    return rid


def _stub_writes(monkeypatch, created: dict):
    def fake_create_repo(token, name, *, private, description="", org=None):
        created["private"] = private
        created["org"] = org
        return {"full_name": f"acme/{name}", "html_url": f"https://github.com/acme/{name}",
                "private": private, "default_branch": "main"}
    monkeypatch.setattr(github, "create_repo", fake_create_repo)
    monkeypatch.setattr(github, "put_file", lambda *a, **k: "sha1")
    monkeypatch.setattr(github, "set_topics", lambda *a, **k: None)
    monkeypatch.setattr(github, "get_repo", lambda token, full: {
        "full_name": full, "html_url": f"https://github.com/{full}", "private": True, "default_branch": "main"})


def test_publish_creates_managed_repo_mirroring_visibility(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    rid = _org_resource(h, slug)  # private (default)
    created: dict = {}
    _stub_writes(monkeypatch, created)

    r = c.post(f"/api/orgs/{slug}/integrations/github/publish", json={"resource_id": rid}, headers=h)
    assert r.status_code == 200, r.text
    assert created["private"] is True  # private resource → private repo
    link = r.json()
    assert link["visibility"] == "private" and link["managed"] is True
    assert link["repo_full_name"].startswith("acme/")

    # reverse mapping: repo → resources
    rev = c.get(f"/api/orgs/{slug}/integrations/github/links?repo={link['repo_full_name']}", headers=h).json()
    assert any(x["resource_id"] == rid for x in rev)


def test_publish_public_resource_makes_public_repo(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    rid = _org_resource(h, slug, title="Public Skill", public=True)
    created: dict = {}
    _stub_writes(monkeypatch, created)
    r = c.post(f"/api/orgs/{slug}/integrations/github/publish", json={"resource_id": rid}, headers=h)
    assert r.status_code == 200, r.text
    assert created["private"] is False  # public resource → public repo
    assert r.json()["visibility"] == "public"


def test_publish_requires_write_capability():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": "ghp_limited_0123456789"}, headers=h)
    rid = _org_resource(h, slug)
    r = c.post(f"/api/orgs/{slug}/integrations/github/publish", json={"resource_id": rid}, headers=h)
    assert r.status_code == 403, r.text


def test_pull_updates_resource(monkeypatch):
    from app.github import DetectedResource

    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    rid = _org_resource(h, slug)
    created: dict = {}
    _stub_writes(monkeypatch, created)
    c.post(f"/api/orgs/{slug}/integrations/github/publish", json={"resource_id": rid}, headers=h)

    monkeypatch.setattr(github, "detect_from_url", lambda url, token=None: (
        None,
        [DetectedResource(kind="skill", title="My Skill", description="pulled desc", content_md="pulled body")],
        {},
    ))
    r = c.post(f"/api/orgs/{slug}/integrations/github/pull", json={"resource_id": rid}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "pulled desc"


def test_scan_lists_and_detects(monkeypatch):
    from app.github import DetectedResource
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    monkeypatch.setattr(github, "list_all_repos", lambda token, account=None, **k: [
        {"full_name": "acme/r1", "name": "r1", "description": ""},
        {"full_name": "acme/r2", "name": "r2", "description": ""},
    ])
    monkeypatch.setattr(github, "detect_from_url", lambda url, token=None: (
        None, [DetectedResource(kind="skill", title="S", fingerprint="fp1")], {}))
    r = c.post(f"/api/orgs/{slug}/integrations/github/scan", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["scanned"] == 2 and r.json()["results"][0]["detected"]


def test_bulk_import_creates_resources(monkeypatch):
    from app.github import DetectedResource
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    monkeypatch.setattr(github, "detect_from_url", lambda url, token=None: (
        None, [DetectedResource(kind="note", title="N", content_md="x", fingerprint="fpN")], {}))
    r = c.post(f"/api/orgs/{slug}/integrations/github/bulk-import",
               json={"repos": ["acme/r1"], "scope_type": "ORG"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 1


def test_publish_scope_publishes_all(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    _org_resource(h, slug, title="Skill A")
    _org_resource(h, slug, title="Skill B")
    created: dict = {}
    _stub_writes(monkeypatch, created)
    r = c.post(f"/api/orgs/{slug}/integrations/github/publish-scope", json={"scope_type": "ORG"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 2


def test_sync_all_pushes_links(monkeypatch):
    h, _ = _user()
    slug = _org(h, plan="PRO")
    c.post(f"/api/orgs/{slug}/integrations/github/connect", json={"token": FAKE_TOKEN}, headers=h)
    rid = _org_resource(h, slug)
    created: dict = {}
    _stub_writes(monkeypatch, created)
    c.post(f"/api/orgs/{slug}/integrations/github/publish", json={"resource_id": rid}, headers=h)
    r = c.post(f"/api/orgs/{slug}/integrations/github/sync-all", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pushed"] >= 1


def test_oauth_start():
    h, _ = _user()
    slug = _org(h, plan="PRO")
    r = c.post(f"/api/orgs/{slug}/integrations/github/oauth/start?method=oauth", headers=h)
    # 422 when OAuth isn't configured (CI), 200 + authorize_url when it is (local .env).
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert r.json()["authorize_url"].startswith("https://github.com/login/oauth")


def test_webhook_and_cron_gated():
    # webhook: 422 when no secret configured, 403 (bad signature) when it is.
    assert c.post("/api/integrations/github/webhook", content=b"{}").status_code in (403, 422)
    # cron: always 403 without a valid X-Cron-Secret header.
    assert c.post("/api/cron/integrations/sync").status_code == 403


def test_webhook_signature_verify():
    import hashlib
    import hmac
    from app.github import verify_webhook_signature
    secret, body = "s3cr3t", b'{"a":1}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(secret, body, good)
    assert not verify_webhook_signature(secret, body, "sha256=deadbeef")
    assert not verify_webhook_signature("", body, good)


def test_repo_summary_includes_health_metadata():
    from app.github import _repo_summary

    s = _repo_summary({
        "full_name": "acme/x", "name": "x", "owner": {"login": "acme"},
        "stargazers_count": 5, "forks_count": 3, "open_issues_count": 2,
        "license": {"spdx_id": "MIT", "name": "MIT License"},
        "pushed_at": "2026-07-01T00:00:00Z", "homepage": "https://x", "private": True,
    })
    assert s["forks"] == 3 and s["open_issues"] == 2
    assert s["license"] == "MIT" and s["pushed_at"] == "2026-07-01T00:00:00Z"
    assert s["homepage"] == "https://x" and s["private"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
