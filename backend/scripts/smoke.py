"""
Contract smoke test — drives the API through the same call sequence the
dashboard makes, asserting the response shapes the client types expect.

  .venv/bin/python -m scripts.smoke      (uses a throwaway SQLite db)
"""

import os
import sys
import tempfile

sys.path.insert(0, ".")
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkstemp(suffix='.db')[1]}"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # the smoke test fires >60 writes/min

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from scripts.seed import seed  # noqa: E402

db = SessionLocal()
seed(db)
db.close()

c = TestClient(app)
checks = 0


def ok(cond, label):
    global checks
    checks += 1
    if not cond:
        print(f"  ✗ {label}")
        sys.exit(1)
    print(f"  ✓ {label}")


print("auth")
r = c.post("/api/auth/login", json={"email": "aniket.lnu@think41.com", "password": "skillshare-demo"})
ok(r.status_code == 200 and "access_token" in r.json(), "login returns session")
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}
ok(c.post("/api/auth/login", json={"email": "aniket.lnu@think41.com", "password": "wrong"}).status_code == 401, "bad password → 401 envelope")
me = c.get("/api/auth/me", headers=H).json()
ok(me["username"] == "aniket" and me["is_publisher"], "GET /auth/me")
r = c.post("/api/auth/refresh", cookies={"skillshare_refresh": r.cookies.get("skillshare_refresh", "")})
ok(r.status_code == 200, "refresh token rotation")

print("personal access tokens (CLI / MCP)")
pat = c.post("/api/auth/tokens", headers=H, json={"name": "smoke test"}).json()
ok(pat["token"].startswith("skst_") and pat["token_prefix"] == pat["token"][:12], "PAT minted, returned once")
PH_TOKEN = {"Authorization": f"Bearer {pat['token']}"}
ok(c.get("/api/auth/me", headers=PH_TOKEN).json()["username"] == "aniket", "PAT authenticates like a JWT")
ok(len(c.get("/api/auth/tokens", headers=H).json()) == 1, "PAT listed (hash only)")
ok(c.delete(f"/api/auth/tokens/{pat['id']}", headers=H).json()["ok"], "PAT revoked")
ok(c.get("/api/auth/me", headers=PH_TOKEN).status_code == 401, "revoked PAT rejected")

print("orgs")
orgs = c.get("/api/orgs", headers=H).json()
ok({o["slug"] for o in orgs} == {"think41", "studio-mono"} and orgs[0].get("my_role"), "GET /orgs with my_role")
org = c.get("/api/orgs/think41", headers=H).json()
ok(org["plan"] == "PREMIUM" and org["terminology"]["pod"] == "Team", "org plan + terminology")
members = c.get("/api/orgs/think41/members", headers=H).json()
ok(len(members) == 4 and members[0]["user"]["display_name"], "members embed user")
inv = c.post("/api/orgs/think41/invite", headers=H, json={"email": "new@think41.com", "role": "MEMBER"}).json()
ok(inv["token"], "invite created")
ok(len(c.get("/api/orgs/think41/invitations", headers=H).json()) == 2, "pending invitations listed")
search = c.get("/api/orgs/think41/search?q=retrieval", headers=H).json()
ok(search["pods"] and search["resources"], "⌘K search finds pods + resources")

print("features & licensing")
feats = c.get("/api/orgs/think41/features", headers=H).json()
ok(len(feats) == 5 and all(f["licensed"] for f in feats), "premium org: all flags licensed")
f = c.patch("/api/orgs/think41/features/activity-feed", headers=H, json={"enabled": False}).json()
ok(f["enabled"] is False, "flag toggled off")
c.patch("/api/orgs/think41/features/activity-feed", headers=H, json={"enabled": True})
mono_feats = c.get("/api/orgs/studio-mono/features", headers=H).json()
pub = next(x for x in mono_feats if x["key"] == "publishing")
ok(pub["licensed"] is False and pub["enabled"] is False, "FREE org: premium flag locked")
r = c.patch("/api/orgs/studio-mono/features/publishing", headers=H, json={"enabled": True})
ok(r.status_code == 403, "toggling unlicensed premium flag → 403")
r = c.post("/api/orgs/studio-mono/license", headers=H, json={"license_key": "T41-PREM-DEMO"})
ok(r.status_code == 403, "non-admin cannot activate license")
# studio-mono admin is u-mono; aniket is MEMBER there. Login as mono:
mono_token = c.post("/api/auth/login", json={"email": "hello@studiomono.dev", "password": "skillshare-demo"}).json()["access_token"]
MH = {"Authorization": f"Bearer {mono_token}"}
ok(c.post("/api/orgs/studio-mono/license", headers=MH, json={"license_key": "bad-key"}).status_code == 422, "bad license key → 422")
lic = c.post("/api/orgs/studio-mono/license", headers=MH, json={"license_key": "T41-PREM-DEMO"}).json()
ok(lic["plan"] == "PREMIUM", "license activation upgrades plan")
r = c.patch("/api/orgs/studio-mono", headers=MH, json={"terminology": {"project": "Project", "pod": "Squad"}})
ok(r.json()["terminology"]["pod"] == "Squad", "terminology write (now licensed)")

print("projects & pods")
projects = c.get("/api/orgs/think41/projects", headers=H).json()
ok(len(projects) == 2 and projects[0]["pods_count"] >= 1, "projects with counts")
proj = c.post("/api/orgs/think41/projects", headers=H, json={"name": "Smoke Project", "tags": ["x"]}).json()
pod = c.post(f"/api/projects/{proj['id']}/pods", headers=H, json={"name": "Smoke Pod", "purpose_tag": "test"}).json()
ok(pod["members_count"] == 1, "pod creator becomes member")

print("resources & inheritance")
res = c.post("/api/resources", headers=H, json={
    "type": "NOTE", "title": "Smoke Note", "content_md": "# hi",
    "scope_type": "POD", "scope_id": pod["id"], "tags": ["smoke"],
}).json()
ok(res["scope_label"] == "POD" and res["author"]["username"] == "aniket", "resource enrichment")
union = c.get(f"/api/pods/{pod['id']}/resources?scope=all", headers=H).json()
labels = {r["scope_label"] for r in union}
ok("POD" in labels and "ORG" in labels, "scope=all union includes inherited org resources")
only_pod = c.get(f"/api/pods/{pod['id']}/resources?scope=pod", headers=H).json()
ok(all(r["scope_label"] == "POD" for r in only_pod), "scope=pod filters")
inherited = c.get("/api/pods/pod-retrieval/resources?q=runbook", headers=H).json()
ok(len(inherited) == 1 and inherited[0]["id"] == "incident-runbook", "search within union")
starred = c.post(f"/api/resources/{res['id']}/star", headers=H).json()
ok(starred["starred_by_me"] and starred["stars_count"] == 1, "star")
ok(c.delete(f"/api/resources/{res['id']}/star", headers=H).json()["stars_count"] == 0, "unstar")
published = c.post(f"/api/resources/{res['id']}/publish", headers=H)
ok(published.status_code == 200 and published.json()["is_public"], "publish (publisher + feature on)")
ok(c.delete(f"/api/resources/{res['id']}/publish", headers=H).json()["is_public"] is False, "unpublish")
up = c.post("/api/resources/upload", headers=H, json={"filename": "my pkg.skill"}).json()
ok(up["file_url"].endswith(".skill"), "upload returns file_url")
ok(c.post("/api/resources/upload", headers=H, json={"filename": "evil.exe"}).status_code == 422, "non-.skill upload rejected")

print("public marketplace")
pub_list = c.get("/api/public/resources?type=MCP&sort=stars").json()
ok(pub_list and all(r["type"] == "MCP" for r in pub_list), "public list, no auth, type filter")
detail = c.get("/api/public/resources/pr-reviewer").json()
ok(detail["author"]["username"] == "ada-rao", "public detail embeds author")
publisher = c.get("/api/public/publishers/ada-rao").json()
ok(len(publisher["resources"]) == 2, "publisher profile")
imported = c.post("/api/resources/pr-reviewer/import", headers=H, json={"org_slug": "think41"}).json()
ok(imported["scope_type"] == "ORG" and imported["is_public"] is False, "marketplace import copies into org")
ok(c.get("/api/public/resources/pr-reviewer").json()["installs_count"] == 12841, "import bumps installs")

print("profiles")
prof = c.get("/api/users/aniket", headers=H).json()
ok(prof["stats"]["orgs"] == 2 and prof["stats"]["resources"] >= 3, "profile stats")
ok(len(c.get("/api/users/aniket/starred", headers=H).json()) == 3, "starred list")
ok(c.get("/api/users/aniket/activity", headers=H).json(), "activity list")
priya_view = c.get("/api/users/devraj/resources", headers=H).json()
ok(all(r["is_public"] for r in priya_view), "other users' resources: public only")

print("permissions & errors")
ok(c.get("/api/orgs/think41").status_code == 401, "no token → 401 envelope")
err = c.get("/api/orgs/nope", headers=H).json()
ok(err["error"]["code"] == "NOT_FOUND" and err["error"]["status"] == 404, "error envelope shape")
priya_token = c.post("/api/auth/login", json={"email": "priya@think41.com", "password": "skillshare-demo"}).json()["access_token"]
PH = {"Authorization": f"Bearer {priya_token}"}
ok(c.get("/api/orgs/studio-mono", headers=PH).status_code == 403, "non-member org access → 403")
ok(c.patch(f"/api/resources/{res['id']}", headers=PH, json={"title": "hijack"}).status_code == 403, "non-author edit → 403")
ok(c.get("/api/pods/pod-tokens/resources", headers=PH).status_code == 403, "pod access enforced")

print(f"\nALL {checks} CHECKS PASSED ✔")
