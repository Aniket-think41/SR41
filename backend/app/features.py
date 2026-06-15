"""
Feature flag catalog + resolution (BACKEND_SPEC §2.12 / §3.7).
Resolution rule (must match the client):
  licensed = !premium || org.plan == PREMIUM
  enabled  = licensed && (override.enabled ?? default_enabled)
"""

from sqlalchemy.orm import Session

from .models import Organization, OrgFeature

CATALOG: list[dict] = [
    {
        "key": "marketplace",
        "name": "Public marketplace",
        "description": "Browse the public marketplace and import resources into the org.",
        "premium": False,
        "default_enabled": True,
    },
    {
        "key": "publishing",
        "name": "Marketplace publishing",
        "description": "Let members publish org resources to the public marketplace.",
        "premium": True,
        "default_enabled": True,
    },
    {
        "key": "command-palette",
        "name": "Command palette (⌘K)",
        "description": "Org-wide instant search across resources, projects, pods, and members.",
        "premium": False,
        "default_enabled": True,
    },
    {
        "key": "activity-feed",
        "name": "Activity feed",
        "description": "The who-did-what timeline on the dashboard home.",
        "premium": False,
        "default_enabled": True,
    },
    {
        "key": "notifications",
        "name": "Notifications",
        "description": "Notify members when resources are added or published in scopes they belong to (inbox in CLI, MCP, and the dashboard bell).",
        "premium": False,
        "default_enabled": True,
    },
    {
        "key": "custom-terminology",
        "name": "Custom terminology",
        "description": "Rename Projects and Pods to match how your org works — e.g. call pods “Teams”.",
        "premium": True,
        "default_enabled": True,
    },
]


def resolve_features(db: Session, org: Organization) -> list[dict]:
    overrides = {f.key: f.enabled for f in db.query(OrgFeature).filter(OrgFeature.org_id == org.id)}
    out = []
    for flag in CATALOG:
        licensed = (not flag["premium"]) or org.plan == "PREMIUM"
        enabled = licensed and overrides.get(flag["key"], flag["default_enabled"])
        out.append({**flag, "licensed": licensed, "enabled": enabled})
    return out


def feature_enabled(db: Session, org: Organization | None, key: str) -> bool:
    if org is None:
        return True  # resources outside an org scope aren't gated
    return next((f["enabled"] for f in resolve_features(db, org) if f["key"] == key), True)
