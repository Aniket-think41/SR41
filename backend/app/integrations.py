"""Integrations registry + connection helpers (org Integrations section).

Two halves:

  * PROVIDER_CATALOG — the code source-of-truth for connectable integrations,
    upserted into the ``integration_providers`` table on boot (``sync_providers``)
    so the registry exists on prod without a reseed while staying editable here.
  * connection helpers — availability filtering (tier + per-provider feature
    flag, layered on the org's ``integrations`` feature), credential set/get with
    Fernet encryption (app/crypto.py), and client-safe serialization that never
    leaks the stored token.

GitHub is the first provider. Adding another (Slack, GitLab, …) is: append a
catalog entry here, optionally add a matching flag to features.CATALOG and set
``feature_flag`` so only orgs with that flag see it, and implement its connect
validation in the router.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import crypto
from .entitlements import plan_at_least
from .features import feature_enabled
from .models import IntegrationProvider, Organization, OrgIntegration, User

# The base feature flag that gates the whole Integrations section.
INTEGRATIONS_FLAG = "integrations"

# Code source-of-truth. `feature_flag=None` → visible to every org that has the
# base integrations feature (GitHub). Give a future provider its own flag to
# show it only to a subset of premium orgs.
PROVIDER_CATALOG: list[dict] = [
    {
        "key": "github",
        "name": "GitHub",
        "tagline": "Turn your repositories into a living catalog of skills, MCP servers, and notes.",
        "description": (
            "Connect your organization's GitHub and SkillShare discovers resources from your "
            "repositories automatically, keeps them in sync, and lets your team manage everything "
            "from Git. Import public repos, keep private ones in sync, attach repos to resources, "
            "and search them straight from the CLI and MCP."
        ),
        "category": "Source Control",
        "icon": "github",
        "docs_url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
        "auth_type": "pat",
        "min_plan": "PRO",
        "feature_flag": None,
        "status": "available",
        "sort_order": 10,
        "enabled": True,
    },
    {
        "key": "hive",
        "name": "Hive",
        "tagline": "Mirror your company's people and teams from Hive into your organization.",
        "description": (
            "Connect Hive (your HR & delivery system) and SkillShare keeps your organization "
            "in step with the real company: import employees as members, map delivery projects "
            "to projects and teams to pods, and keep membership current as people join, move, "
            "and leave. Connecting only fetches the directory for review — nothing is added until "
            "you approve it, and imports never send bulk mail."
        ),
        "category": "HR & Directory",
        "icon": "hive",
        "docs_url": "https://hive.think41.com/",
        "auth_type": "oauth",
        "min_plan": "ENTERPRISE",
        "feature_flag": None,
        "status": "available",
        "sort_order": 20,
        "enabled": True,
    },
]

_CATALOG_KEYS = {p["key"] for p in PROVIDER_CATALOG}

# --------------------------------------------------------------------------- #
# Connection methods + capabilities (per provider)
# --------------------------------------------------------------------------- #

# How you can connect a provider. `available=False` → shown as "coming soon".
# `recommended` scopes drive the connect screen's permission checklist.
AUTH_METHODS: dict[str, list[dict]] = {
    "github": [
        {
            "key": "classic_pat",
            "name": "Personal Access Token (classic)",
            "hint": "The quickest way to connect. Create a token with the scopes below.",
            "docs_url": "https://github.com/settings/tokens/new",
            "available": True,
            "recommended": [
                {"scope": "repo", "why": "Read private repositories and push changes back", "required": False},
                {"scope": "read:org", "why": "Discover your organization's repositories", "required": False},
                {"scope": "read:user", "why": "Identify the connected account", "required": True},
                {"scope": "admin:repo_hook", "why": "Receive repository events (live sync, coming soon)", "required": False},
            ],
        },
        {
            "key": "oauth",
            "name": "Sign in with GitHub (OAuth)",
            "hint": "Authorize SkillShare in your browser — no token to paste.",
            "available": False,  # activated when GITHUB_OAUTH_CLIENT_ID/SECRET are set
            "recommended": [
                {"scope": "repo", "why": "Read private repos and push changes", "required": False},
                {"scope": "read:org", "why": "Discover organization repositories", "required": False},
            ],
        },
        {
            "key": "github_app",
            "name": "GitHub App",
            "hint": "Org-grade install with fine-grained per-repo access and webhooks.",
            "available": False,  # activated when GITHUB_APP_ID + private key are set
            "recommended": [],
        },
    ],
    "hive": [
        {
            "key": "oauth",
            "name": "Sign in with Hive",
            "hint": "Authorize SkillShare in your browser — no token to paste. Sign in with the "
                    "Google account you use for Hive; use an HR / allocation-manager account so "
                    "the sync can see everyone (including leavers) and all project allocations.",
            "docs_url": "https://hive.think41.com/",
            "available": True,
            "recommended": [
                {"scope": "employees:read", "why": "Import employees as organization members", "required": True},
                {"scope": "delivery:read", "why": "Map delivery projects to projects", "required": False},
                {"scope": "allocations:read", "why": "Place people on the right project/pod", "required": False},
                {"scope": "groups:read", "why": "Map teams to pods with their members", "required": False},
            ],
        },
        {
            "key": "service_token",
            "name": "Paste a Hive token",
            "hint": "Advanced / testing: paste a short-lived Hive access token and the tenant code.",
            "available": True,
            "recommended": [],
        },
    ],
}


def auth_methods_for(provider_key: str) -> list[dict]:
    """The connect methods for a provider with availability resolved from config.
    OAuth/App become available only when their credentials are set (else they
    render as 'coming soon')."""
    from .config import get_settings

    base = [dict(m) for m in AUTH_METHODS.get(provider_key, [])]
    if provider_key != "github":
        return base
    s = get_settings()
    oauth_on = bool(s.github_oauth_client_id and s.github_oauth_client_secret)
    app_on = bool(s.github_app_id and s.github_app_private_key)
    for m in base:
        if m["key"] == "oauth":
            m["available"] = oauth_on
            if not oauth_on:
                m["status"] = "coming_soon"
        elif m["key"] == "github_app":
            m["available"] = app_on
            if not app_on:
                m["status"] = "coming_soon"
            elif s.github_app_slug:
                m["install_url"] = f"https://github.com/apps/{s.github_app_slug}/installations/new"
    return base

# Capabilities a connection can unlock, and what grants them. `always` = any valid
# token. `scopes` = classic-PAT scopes that grant it (any one suffices).
CAPABILITY_CATALOG: dict[str, list[dict]] = {
    "github": [
        {"key": "read_public", "name": "Read public repositories",
         "description": "Discover and read any public repository.",
         "always": True, "scopes": []},
        {"key": "search", "name": "Search repositories",
         "description": "Search across the connected account's repositories.",
         "always": True, "scopes": []},
        {"key": "read_org", "name": "Read organization repositories",
         "description": "List and read repositories owned by your organization.",
         "always": False, "scopes": ["read:org", "repo"], "recommend": "read:org"},
        {"key": "read_private", "name": "Access private repositories",
         "description": "Read private repositories and import their resources.",
         "always": False, "scopes": ["repo"], "recommend": "repo"},
        {"key": "write", "name": "Push changes to GitHub",
         "description": "Two-way / write-only sync back to repositories.",
         "always": False, "scopes": ["repo"], "recommend": "repo"},
        {"key": "webhooks", "name": "Receive repository events",
         "description": "Live sync on push/release via webhooks. GitHub App installs get this automatically; a classic PAT needs the admin:repo_hook scope.",
         "always": False, "scopes": ["admin:repo_hook"], "recommend": "admin:repo_hook"},
    ],
    # Hive access is governed by the connecting user's role in Hive (OPA), not by
    # OAuth scopes we can introspect — so these show as available and the connect
    # hint warns that an HR / allocation-manager account is needed for full reach.
    "hive": [
        {"key": "read_people", "name": "Read employees",
         "description": "Import employees as organization members and detect leavers.",
         "always": True, "scopes": []},
        {"key": "read_projects", "name": "Read delivery projects",
         "description": "Map Hive projects to SkillShare projects.",
         "always": True, "scopes": []},
        {"key": "read_allocations", "name": "Read allocations",
         "description": "Place people on the projects/pods they're allocated to.",
         "always": True, "scopes": []},
        {"key": "read_groups", "name": "Read teams",
         "description": "Map Hive groups/teams to pods with their members.",
         "always": True, "scopes": []},
    ],
}


def compute_capabilities(provider_key: str, scopes: list[str] | None) -> list[str]:
    """Derive the enabled capability keys from granted scopes (classic PAT)."""
    granted = set(scopes or [])
    out = []
    for cap in CAPABILITY_CATALOG.get(provider_key, []):
        if cap.get("always") or (granted & set(cap.get("scopes", []))):
            out.append(cap["key"])
    return out


def has_capability(conn: OrgIntegration, key: str) -> bool:
    return bool(conn and conn.capabilities and key in conn.capabilities)


def sync_providers(db: Session) -> None:
    """Upsert PROVIDER_CATALOG into the DB. Idempotent; safe to call on boot."""
    existing = {p.key: p for p in db.query(IntegrationProvider).all()}
    changed = False
    for spec in PROVIDER_CATALOG:
        row = existing.get(spec["key"])
        if row is None:
            db.add(IntegrationProvider(**spec))
            changed = True
            continue
        for field, value in spec.items():
            if field == "key":
                continue
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
    if changed:
        db.commit()


# --------------------------------------------------------------------------- #
# Availability (which cards an org may see)
# --------------------------------------------------------------------------- #

def provider_available(db: Session, org: Organization, provider: IntegrationProvider) -> bool:
    """A provider shows for an org when: it's globally enabled, the org has the
    base integrations feature, the org meets the provider's tier, and (if the
    provider names one) the org has that extra feature flag enabled."""
    if not provider.enabled:
        return False
    if not feature_enabled(db, org, INTEGRATIONS_FLAG):
        return False
    if not plan_at_least(org.plan, provider.min_plan):
        return False
    if provider.feature_flag and not feature_enabled(db, org, provider.feature_flag):
        return False
    return True


def available_providers(db: Session, org: Organization) -> list[IntegrationProvider]:
    rows = db.query(IntegrationProvider).order_by(IntegrationProvider.sort_order).all()
    return [p for p in rows if provider_available(db, org, p)]


# --------------------------------------------------------------------------- #
# Credentials (encrypted at rest)
# --------------------------------------------------------------------------- #

def set_credentials(conn: OrgIntegration, creds: dict) -> None:
    """Encrypt and store a credential blob on the connection row."""
    conn.credentials_enc = crypto.encrypt(json.dumps(creds))


def get_credentials(conn: OrgIntegration) -> dict:
    """Decrypt the stored credential blob ({} if none / undecryptable)."""
    if not conn.credentials_enc:
        return {}
    try:
        return json.loads(crypto.decrypt(conn.credentials_enc))
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# Hive credential helpers (OAuth access token with auto-refresh)
# --------------------------------------------------------------------------- #

def hive_tenant(conn: OrgIntegration) -> str:
    """The Hive tenant code this connection is bound to."""
    tenant = (conn.config or {}).get("tenant") or conn.account_label
    if not tenant:
        from .errors import validation

        raise validation("This Hive connection has no tenant set — reconnect it")
    return tenant


def hive_access_token(db: Session, conn: OrgIntegration) -> str:
    """Return a valid Hive access token, refreshing from the stored refresh token
    if it has expired (the A+ flow) and persisting the rotated credential."""
    from . import hive

    creds = get_credentials(conn)
    if not creds.get("access_token"):
        from .errors import validation

        raise validation("This Hive connection has no access token — reconnect it")
    if hive.token_expired(creds) and creds.get("refresh_token"):
        creds = hive.refresh_access_token(creds)
        set_credentials(conn, creds)
        db.commit()
    return creds["access_token"]


def hive_client(db: Session, conn: OrgIntegration):
    """Build a live HiveClient for this connection (token refreshed as needed)."""
    from . import hive

    token = hive_access_token(db, conn)
    return hive.build_client({"access_token": token}, hive_tenant(conn))


# --------------------------------------------------------------------------- #
# Serialization (client-safe — never leaks the token)
# --------------------------------------------------------------------------- #

def provider_out(provider: IntegrationProvider, conn: OrgIntegration | None = None) -> dict:
    return {
        "key": provider.key,
        "name": provider.name,
        "tagline": provider.tagline,
        "description": provider.description,
        "category": provider.category,
        "icon": provider.icon,
        "docs_url": provider.docs_url,
        "auth_type": provider.auth_type,
        "status": provider.status,
        "auth_methods": auth_methods_for(provider.key),
        "connected": bool(conn and conn.status == "connected"),
        "connection": connection_out(conn) if conn else None,
    }


def _capabilities_out(conn: OrgIntegration) -> list[dict]:
    """Full capability list for the UI: each catalog entry + whether it's enabled
    for this connection, so features can gate on it and show what to grant."""
    enabled = set(conn.capabilities or [])
    return [
        {
            "key": c["key"],
            "name": c["name"],
            "description": c["description"],
            "recommend": c.get("recommend"),
            "enabled": c["key"] in enabled,
        }
        for c in CAPABILITY_CATALOG.get(conn.provider_key, [])
    ]


def resource_repo_files(resource) -> list[tuple[str, str]]:
    """Render a resource into the files that represent it in a GitHub repo
    (the publish content mapping). Always writes a `skillshare.json` manifest."""
    manifest = {
        "skillshare_id": resource.id,
        "type": resource.type,
        "title": resource.title,
        "version": resource.version,
        "tags": resource.tags or [],
        "visibility": "public" if resource.is_public else "private",
    }
    files: list[tuple[str, str]] = [("skillshare.json", json.dumps(manifest, indent=2) + "\n")]
    if resource.type == "SKILL":
        fm = f"---\nname: {resource.title}\ndescription: {resource.description or ''}\n---\n\n"
        files.append(("SKILL.md", fm + (resource.content_md or "")))
    elif resource.type == "MCP":
        if resource.config_json:
            files.append((".mcp.json", resource.config_json))
        readme = f"# {resource.title}\n\n{resource.description or ''}\n"
        if resource.server_url:
            readme += f"\nServer: {resource.server_url}\n"
        files.append(("README.md", readme))
    else:  # NOTE
        files.append(("README.md", f"# {resource.title}\n\n{resource.content_md or resource.description or ''}\n"))
    return files


def link_out(link, resource=None) -> dict:
    return {
        "id": link.id,
        "resource_id": link.resource_id,
        "resource_title": getattr(resource, "title", None),
        "resource_type": getattr(resource, "type", None),
        "provider_key": link.provider_key,
        "repo_full_name": link.repo_full_name,
        "repo_url": link.repo_url,
        "path": link.path,
        "visibility": link.visibility,
        "managed": link.managed,
        "direction": link.direction,
        "last_pushed_at": link.last_pushed_at.isoformat() if link.last_pushed_at else None,
        "last_pulled_at": link.last_pulled_at.isoformat() if link.last_pulled_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _resource_subpath(resource) -> str:
    import re

    slug = re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", (resource.title or "resource").lower())) or "resource"
    return f"{resource.type.lower()}/{slug}"


def _scope_chain(db: Session, resource) -> set[tuple[str, str]]:
    """The set of (scope_type, scope_id) that "cover" a resource: its own scope
    plus every ancestor (pod → project → org). A scope-repo link on any of these
    catches the resource."""
    from .models import Pod, Project

    st, sid = resource.scope_type, resource.scope_id
    if st == "PUBLIC" or not sid:
        return set()
    out: set[tuple[str, str]] = {(st, sid)}
    if st == "POD":
        pod = db.get(Pod, sid)
        if pod:
            out.add(("PROJECT", pod.project_id))
            proj = db.get(Project, pod.project_id)
            if proj:
                out.add(("ORG", proj.org_id))
    elif st == "PROJECT":
        proj = db.get(Project, sid)
        if proj:
            out.add(("ORG", proj.org_id))
    return out


def visibility_matches(link_visibility: str, is_public: bool) -> bool:
    if link_visibility == "public":
        return bool(is_public)
    if link_visibility == "private":
        return not is_public
    return True  # "all"


def connection_token(conn: OrgIntegration) -> str | None:
    """Return a usable GitHub token for a connection — minting a fresh App
    installation token when needed. None if unavailable."""
    from . import github
    from .config import get_settings

    creds = get_credentials(conn)
    if conn.auth_method == "github_app":
        s = get_settings()
        iid = creds.get("installation_id")
        if not iid or not (s.github_app_id and s.github_app_private_key):
            return None
        try:
            return github.installation_token(s.github_app_id, s.github_app_private_key_pem, iid)["token"]
        except Exception:
            return None
    return creds.get("token")


def scope_link_out(link) -> dict:
    return {
        "id": link.id,
        "scope_type": link.scope_type,
        "scope_id": link.scope_id,
        "provider_key": link.provider_key,
        "repo_full_name": link.repo_full_name,
        "repo_url": link.repo_url,
        "repo_private": bool(getattr(link, "repo_private", False)),
        "path_prefix": link.path_prefix,
        "visibility": link.visibility,
        "sync_direction": getattr(link, "sync_direction", "push"),
        "auto_sync": link.auto_sync,
        "last_synced_at": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def push_allowed(link, resource) -> bool:
    """Safety: never push a PRIVATE resource to a PUBLIC repo, regardless of route
    (defence-in-depth on top of visibility routing)."""
    if not resource.is_public and not getattr(link, "repo_private", False):
        return False
    return visibility_matches(link.visibility, resource.is_public)


def push_resource_to(token: str, full_name: str, resource, base_path: str) -> str | None:
    """Push a resource's files into <base_path>/<type>/<slug>/ in a repo (so many
    resources coexist in one mono-repo). Returns the last blob sha."""
    from . import github

    branch = (github.get_repo(token, full_name) or {}).get("default_branch") or "main"
    prefix = f"{base_path.rstrip('/')}/" if base_path else ""
    sub = _resource_subpath(resource)
    last = None
    for p, content in resource_repo_files(resource):
        last = github.put_file(token, full_name, f"{prefix}{sub}/{p}", content,
                               f"skillshare: sync {resource.title}", branch)
    return last


def autosync_resource(db: Session, resource) -> None:
    """Best-effort: push a resource to every auto_sync scope-repo link that covers
    its scope and matches its visibility. Never raises (guards resource writes)."""
    try:
        from .models import OrgIntegration, ScopeRepoLink

        chain = _scope_chain(db, resource)
        if not chain:
            return
        ids = [sid for (_st, sid) in chain]
        links = [
            l for l in db.query(ScopeRepoLink)
            .filter(ScopeRepoLink.provider_key == "github", ScopeRepoLink.scope_id.in_(ids)).all()
            if (l.scope_type, l.scope_id) in chain
            and getattr(l, "sync_direction", "push") in ("push", "both")
            and push_allowed(l, resource)
        ]
        if not links:
            return
        conn = (
            db.query(OrgIntegration)
            .filter(OrgIntegration.org_id == links[0].org_id,
                    OrgIntegration.provider_key == "github", OrgIntegration.status == "connected")
            .first()
        )
        if not conn or "write" not in (conn.capabilities or []):
            return
        token = connection_token(conn)
        if not token:
            return
        import datetime as _dt

        for link in links:
            try:
                push_resource_to(token, link.repo_full_name, resource, link.path_prefix)
                link.last_synced_at = _dt.datetime.now(_dt.timezone.utc)
            except Exception:
                continue
        db.commit()
    except Exception:
        pass


def connection_out(conn: OrgIntegration | None) -> dict | None:
    if conn is None:
        return None
    return {
        "id": conn.id,
        "provider_key": conn.provider_key,
        "status": conn.status,
        "auth_method": conn.auth_method,
        "account_label": conn.account_label,
        "account_type": conn.account_type,
        "account_url": conn.account_url,
        "account_avatar": conn.account_avatar,
        "token_hint": conn.token_hint,
        "scopes": conn.scopes or [],
        "capabilities": _capabilities_out(conn),
        "config": conn.config or {},
        "last_error": conn.last_error,
        "connected_by": conn.connected_by,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    }
