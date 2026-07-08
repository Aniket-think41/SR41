"""Activity feed fixes + client-source tracking (spec §7): starred is now logged,
resource actions carry a source (web/cli/mcp), a /use ping records client usage,
and the activity-feed flag is enforced server-side.

    cd backend && .venv/bin/python -m pytest tests/test_activity.py -q
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
    email = f"act{_n[0]}_{os.getpid()}@example.com"
    _s = c.post("/api/auth/signup", json={"email": email, "password": "password123", "display_name": f"Act {_n[0]}"})
    r = c.post("/api/auth/verify-email", json={"email": email, "code": _s.json()["dev_otp"]})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = c.get("/api/auth/me", headers=h).json()["id"]
    db = SessionLocal()
    db.get(User, uid).plan = "ENTERPRISE"
    username = db.get(User, uid).username
    db.commit()
    db.close()
    return h, uid, username


def _org(h):
    _n[0] += 1
    return c.post("/api/orgs", json={"name": f"ActOrg {_n[0]} {os.getpid()}"}, headers=h).json()["slug"]


def test_star_is_logged_to_activity():
    h, _, username = _user()
    slug = _org(h)
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    rid = c.post("/api/resources", json={"type": "NOTE", "title": "T", "scope_type": "ORG", "scope_id": org_id}, headers=h).json()["id"]

    c.post(f"/api/resources/{rid}/star", headers=h)
    acts = c.get(f"/api/users/{username}/activity", headers=h).json()
    assert any(a["verb"] == "starred" and a["object_id"] == rid for a in acts)


def test_client_source_header_is_recorded():
    h, _, username = _user()
    slug = _org(h)
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    # create via the CLI client
    c.post(
        "/api/resources",
        json={"type": "SKILL", "title": "CliMade", "scope_type": "ORG", "scope_id": org_id},
        headers={**h, "X-SkillShare-Client": "cli"},
    )
    acts = c.get(f"/api/users/{username}/activity", headers=h).json()
    created = next(a for a in acts if a["object_title"] == "CliMade")
    assert created["source"] == "cli"


def test_use_ping_tracks_mcp_usage_and_bumps_installs():
    h, _, username = _user()
    slug = _org(h)
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    rid = c.post("/api/resources", json={"type": "MCP", "title": "M", "scope_type": "ORG", "scope_id": org_id}, headers=h).json()["id"]

    used = c.post(f"/api/resources/{rid}/use", headers={**h, "X-SkillShare-Client": "mcp"})
    assert used.status_code == 200, used.text
    assert used.json()["installs_count"] == 1
    acts = c.get(f"/api/users/{username}/activity", headers=h).json()
    assert any(a["verb"] == "used" and a["source"] == "mcp" for a in acts)


def test_activity_feed_flag_enforced_server_side():
    h, _, _ = _user()
    slug = _org(h)
    # disable the activity-feed feature for the org
    off = c.patch(f"/api/orgs/{slug}/features/activity-feed", json={"enabled": False}, headers=h)
    assert off.status_code == 200, off.text
    assert c.get(f"/api/orgs/{slug}/activity", headers=h).json() == []


def test_unknown_client_header_defaults_to_web():
    h, _, username = _user()
    slug = _org(h)
    org_id = c.get(f"/api/orgs/{slug}", headers=h).json()["id"]
    c.post(
        "/api/resources",
        json={"type": "NOTE", "title": "WebMade", "scope_type": "ORG", "scope_id": org_id},
        headers={**h, "X-SkillShare-Client": "totally-bogus"},
    )
    acts = c.get(f"/api/users/{username}/activity", headers=h).json()
    assert next(a for a in acts if a["object_title"] == "WebMade")["source"] == "web"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
