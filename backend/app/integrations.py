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
        "connected": bool(conn and conn.status == "connected"),
        "connection": connection_out(conn) if conn else None,
    }


def connection_out(conn: OrgIntegration | None) -> dict | None:
    if conn is None:
        return None
    return {
        "id": conn.id,
        "provider_key": conn.provider_key,
        "status": conn.status,
        "account_label": conn.account_label,
        "token_hint": conn.token_hint,
        "config": conn.config or {},
        "last_error": conn.last_error,
        "connected_by": conn.connected_by,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
    }
