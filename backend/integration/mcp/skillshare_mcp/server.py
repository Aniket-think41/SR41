"""
SkillShare MCP server (stdio).

Exposes the registry to MCP clients — Claude Code, Claude Desktop, or any
agent runtime. Wraps the REST API in BACKEND_SPEC.md; auth is a Personal
Access Token (spec §10) via env:

    SKILLSHARE_API_URL   e.g. http://localhost:8400
    SKILLSHARE_TOKEN     skst_…  (mint with `skillshare login` or POST /api/auth/tokens)

Public marketplace tools work without a token; org/pod tools require one.
"""

import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("SKILLSHARE_API_URL", "http://localhost:8400").rstrip("/")
TOKEN = os.environ.get("SKILLSHARE_TOKEN", "")

mcp = FastMCP(
    "skillshare",
    instructions=(
        "SkillShare is a registry of AI skills, MCP servers, and team notes, "
        "organized as org → projects → pods. Use search/list tools to find "
        "resources, get_resource for full content (SKILL.md, MCP config JSON, "
        "note markdown), and create_note/star/import to write. Resources can "
        "carry typed attachments (link/image/video/file): upload_file stores a "
        "local file and returns a URL you can pass to create_note's attachments."
    ),
)


class SkillShareError(Exception):
    pass


def _request(method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> Any:
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        res = client.request(method, path, json=json, params=params, headers=headers)
    if res.status_code >= 400:
        try:
            err = res.json()["error"]
            raise SkillShareError(f"{err['code']}: {err['message']}")
        except (KeyError, ValueError):
            raise SkillShareError(f"HTTP {res.status_code}: {res.text[:200]}")
    return res.json()


def _upload(path: str, kind: str) -> dict:
    """Upload a local file to POST /api/uploads (multipart) → {file_url, ...}."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise SkillShareError(f"file not found: {path}")
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    with p.open("rb") as fh, httpx.Client(base_url=API_URL, timeout=120) as client:
        res = client.post("/api/uploads", data={"kind": kind}, files={"file": (p.name, fh)}, headers=headers)
    if res.status_code >= 400:
        try:
            err = res.json()["error"]
            raise SkillShareError(f"{err['code']}: {err['message']}")
        except (KeyError, ValueError):
            raise SkillShareError(f"HTTP {res.status_code}: {res.text[:200]}")
    return res.json()


def _summary(r: dict) -> dict:
    """Trimmed resource for list results — keeps agent context small."""
    return {
        "id": r["id"],
        "type": r["type"],
        "title": r["title"],
        "description": r["description"],
        "version": r["version"],
        "tags": r["tags"],
        "scope": r.get("scope_label") or r["scope_type"],
        "author": (r.get("author") or {}).get("username"),
        "stars": r["stars_count"],
        "is_public": r["is_public"],
        "updated_at": str(r["updated_at"]),
    }


# ---------- read: marketplace (no auth needed) ----------

@mcp.tool()
def search_marketplace(
    query: str = "",
    resource_type: str = "",
    tag: str = "",
    sort: str = "stars",
) -> list[dict]:
    """Search the public SkillShare marketplace for skills, MCP servers, and notes.

    Args:
        query: free-text search over title, description, and tags.
        resource_type: filter — "SKILL", "MCP", or "NOTE" (empty = all).
        tag: filter by exact tag, e.g. "code-review".
        sort: "stars" | "installs" | "newest" | "updated".
    """
    params = {"q": query or None, "type": resource_type or None, "tag": tag or None, "sort": sort}
    rows = _request("GET", "/api/public/resources", params={k: v for k, v in params.items() if v})
    return [_summary(r) for r in rows]


@mcp.tool()
def get_resource(resource_id: str) -> dict:
    """Get a resource's full content by id: SKILL.md for skills, server URL +
    config JSON for MCP servers, markdown body for notes. Works for public
    resources and (with a token) anything your orgs can see."""
    r = _request("GET", f"/api/resources/{resource_id}") if TOKEN else _request(
        "GET", f"/api/public/resources/{resource_id}"
    )
    out = _summary(r)
    out.update(
        {
            "content_md": r.get("content_md"),
            "server_url": r.get("server_url"),
            "config_json": r.get("config_json"),
            "file_url": r.get("file_url"),
            "attachments": r.get("attachments") or [],
        }
    )
    return out


@mcp.tool()
def get_publisher(username: str) -> dict:
    """Get a marketplace publisher's profile and their public resources."""
    p = _request("GET", f"/api/public/publishers/{username}")
    return {
        "username": p["username"],
        "display_name": p["display_name"],
        "bio": p["bio"],
        "verified": p.get("verified", False),
        "resources": [_summary(r) for r in p["resources"]],
    }


# ---------- read: my orgs (token required) ----------

@mcp.tool()
def whoami() -> dict:
    """Who am I authenticated as? (Requires SKILLSHARE_TOKEN.)"""
    u = _request("GET", "/api/auth/me")
    return {"username": u["username"], "display_name": u["display_name"], "email": u["email"]}


@mcp.tool()
def list_my_orgs() -> list[dict]:
    """List organizations the authenticated user belongs to."""
    return [
        {"slug": o["slug"], "name": o["name"], "role": o["my_role"], "plan": o["plan"]}
        for o in _request("GET", "/api/orgs")
    ]


@mcp.tool()
def list_org_structure(org_slug: str) -> dict:
    """List an org's projects and pods (ids + names), so you can target
    list_pod_resources / create_note at the right scope."""
    projects = _request("GET", f"/api/orgs/{org_slug}/projects")
    out = []
    for p in projects:
        pods = _request("GET", f"/api/projects/{p['id']}/pods")
        out.append(
            {
                "project_id": p["id"],
                "name": p["name"],
                "pods": [{"pod_id": x["id"], "name": x["name"], "purpose": x["purpose_tag"]} for x in pods],
            }
        )
    return {"org": org_slug, "projects": out}


@mcp.tool()
def list_org_resources(org_slug: str, query: str = "", resource_type: str = "") -> list[dict]:
    """List org-level resources (inherited by every project and pod)."""
    params = {"q": query or None, "type": resource_type or None}
    rows = _request("GET", f"/api/orgs/{org_slug}/resources", params={k: v for k, v in params.items() if v})
    return [_summary(r) for r in rows]


@mcp.tool()
def list_pod_resources(pod_id: str, scope: str = "all", query: str = "", resource_type: str = "") -> list[dict]:
    """List a pod's unified resource library — its own resources plus those
    inherited from the project and org (BACKEND_SPEC §5).

    Args:
        pod_id: the pod to query.
        scope: "all" | "pod" | "project" | "org" — filter by origin.
        query: free-text filter.
        resource_type: "SKILL" | "MCP" | "NOTE".
    """
    params = {"scope": scope, "q": query or None, "type": resource_type or None}
    rows = _request("GET", f"/api/pods/{pod_id}/resources", params={k: v for k, v in params.items() if v})
    return [_summary(r) for r in rows]


@mcp.tool()
def search_org(org_slug: str, query: str) -> dict:
    """Search one org across resources, projects, pods, and members
    (the same search the dashboard's ⌘K palette uses)."""
    res = _request("GET", f"/api/orgs/{org_slug}/search", params={"q": query})
    return {
        "resources": [_summary(r) for r in res["resources"]],
        "projects": [{"id": p["id"], "name": p["name"]} for p in res["projects"]],
        "pods": [{"id": p["id"], "name": p["name"]} for p in res["pods"]],
        "members": [{"username": u["username"], "name": u["display_name"]} for u in res["members"]],
    }


# ---------- write (token required) ----------

@mcp.tool()
def create_note(
    title: str,
    content_md: str,
    org_slug: str = "",
    pod_id: str = "",
    description: str = "",
    tags: list[str] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Create a NOTE resource — team knowledge in markdown. Provide either
    org_slug (org-level note, inherited everywhere) or pod_id (pod-level).

    Args:
        title: note title.
        content_md: markdown body.
        org_slug: target org slug for an org-level note.
        pod_id: target pod id for a pod-level note (overrides org_slug).
        description: one-line summary shown on cards.
        tags: e.g. ["process", "rag"].
        attachments: typed media, each {kind, url, title?, caption?} where kind
            is "link" | "image" | "video" | "file". Pass public URLs; to attach
            a local file, call upload_file first and use the returned file_url.
    """
    if pod_id:
        scope = {"scope_type": "POD", "scope_id": pod_id}
    elif org_slug:
        org = _request("GET", f"/api/orgs/{org_slug}")
        scope = {"scope_type": "ORG", "scope_id": org["id"]}
    else:
        raise SkillShareError("Provide org_slug or pod_id")
    r = _request(
        "POST",
        "/api/resources",
        json={
            "type": "NOTE",
            "title": title,
            "description": description,
            "content_md": content_md,
            "tags": tags or [],
            "attachments": attachments or [],
            **scope,
        },
    )
    return _summary(r)


@mcp.tool()
def upload_file(path: str, kind: str = "file") -> dict:
    """Upload a local file to SkillShare storage and return its public URL.

    Use this when you have a file on disk (e.g. a diagram or image you just
    generated) that you want to attach to a note. Pass the returned file_url
    in create_note's `attachments`.

    Args:
        path: local filesystem path to the file.
        kind: "image" (incl. diagrams), "video", or "file".
    """
    if kind not in ("image", "video", "file"):
        raise SkillShareError("kind must be image, video, or file")
    up = _upload(path, kind)
    return {"file_url": up["file_url"], "filename": up.get("filename"), "size_bytes": up.get("size_bytes")}


@mcp.tool()
def star_resource(resource_id: str) -> dict:
    """Star a resource so it shows on your profile's Stars tab."""
    return _summary(_request("POST", f"/api/resources/{resource_id}/star"))


@mcp.tool()
def import_resource(resource_id: str, org_slug: str) -> dict:
    """Copy a public marketplace resource into one of your orgs
    (the dashboard's "Add to my org")."""
    return _summary(_request("POST", f"/api/resources/{resource_id}/import", json={"org_slug": org_slug}))


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
