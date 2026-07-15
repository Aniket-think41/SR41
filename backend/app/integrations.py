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
            "key": "github_app",
            "name": "GitHub App",
            "hint": "Org-grade install with fine-grained per-repo access and webhooks.",
            "available": False,
            "status": "coming_soon",
            "recommended": [],
        },
    ],
}

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
         "description": "Live sync on push/release via webhooks (coming soon).",
         "always": False, "scopes": ["admin:repo_hook"], "recommend": "admin:repo_hook"},
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
        "auth_methods": AUTH_METHODS.get(provider.key, []),
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
