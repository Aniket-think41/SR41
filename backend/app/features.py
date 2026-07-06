"""
Feature flag catalog + resolution (BACKEND_SPEC §2.12 / §3.7).

Tier-aware since spec §2: each flag declares the minimum plan that unlocks it
(``min_plan`` on the FREE | PRO | ENTERPRISE ladder). Resolution rule:
  licensed = plan_at_least(org.plan, flag.min_plan)
  enabled  = licensed && (override.enabled ?? default_enabled)
``premium`` is still emitted in the payload (= min_plan != FREE) for older
clients, but ``min_plan`` is the source of truth.
"""

from sqlalchemy.orm import Session

from .entitlements import FREE, PRO, plan_at_least
from .models import Organization, OrgFeature

CATALOG: list[dict] = [
    {
        "key": "marketplace",
        "name": "Public marketplace",
        "description": "Browse the public marketplace and import resources into the org.",
        "min_plan": FREE,
        "default_enabled": True,
    },
    {
        "key": "publishing",
        "name": "Marketplace publishing",
        "description": "Let members publish org resources to the public marketplace.",
        "min_plan": PRO,
        "default_enabled": True,
    },
    {
        "key": "command-palette",
        "name": "Command palette (⌘K)",
        "description": "Org-wide instant search across resources, projects, pods, and members.",
        "min_plan": FREE,
        "default_enabled": True,
    },
    {
        "key": "activity-feed",
        "name": "Activity feed",
        "description": "The who-did-what timeline on the dashboard home.",
        "min_plan": FREE,
        "default_enabled": True,
    },
    {
        "key": "notifications",
        "name": "Notifications",
        "description": "Notify members when resources are added or published in scopes they belong to (inbox in CLI, MCP, and the dashboard bell).",
        "min_plan": FREE,
        "default_enabled": True,
    },
    {
        "key": "custom-terminology",
        "name": "Custom terminology",
        "description": "Rename Projects and Pods to match how your org works — e.g. call pods “Teams”.",
        "min_plan": PRO,
        "default_enabled": True,
    },
]


def resolve_features(db: Session, org: Organization) -> list[dict]:
    overrides = {f.key: f.enabled for f in db.query(OrgFeature).filter(OrgFeature.org_id == org.id)}
    out = []
    for flag in CATALOG:
        min_plan = flag.get("min_plan", FREE)
        licensed = plan_at_least(org.plan, min_plan)
        enabled = licensed and overrides.get(flag["key"], flag["default_enabled"])
        out.append({
            **flag,
            "min_plan": min_plan,
            "premium": min_plan != FREE,
            "licensed": licensed,
            "enabled": enabled,
        })
    return out


def feature_enabled(db: Session, org: Organization | None, key: str) -> bool:
    if org is None:
        return True  # resources outside an org scope aren't gated
    return next((f["enabled"] for f in resolve_features(db, org) if f["key"] == key), True)
