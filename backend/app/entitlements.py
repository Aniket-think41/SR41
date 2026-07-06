"""
Plan tiers, entitlements, and quota enforcement (spec §1 / §2 / §8.3).

Two billable entities share one 3-tier ladder:
  - a User's *personal / publisher* space  → ``User.plan``
  - an Organization                        → ``Organization.plan``

Limits are enforced *per entity*: every org carries its own resource quota and
the publisher space carries its own. A resource counts against whoever owns its
home scope (the org for ORG/PROJECT/POD scopes, the author for PUBLIC).

Legacy ``"PREMIUM"`` (from the old T41-PREM license flow) normalizes to
ENTERPRISE so existing paid orgs keep every feature. Enforcement lives here so
the API, the CLI, and the MCP server all read the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from .errors import payment_required
from .models import Organization, OrgMember, Pod, Project, Resource, User

FREE, PRO, ENTERPRISE = "FREE", "PRO", "ENTERPRISE"
PLANS = (FREE, PRO, ENTERPRISE)
_RANK = {FREE: 0, PRO: 1, ENTERPRISE: 2}


@dataclass(frozen=True)
class PlanSpec:
    key: str
    name: str
    price_usd: int              # per month
    max_orgs: int | None        # None = unlimited; 0 = cannot create orgs
    resource_quota: int | None  # per entity; None = unlimited
    mcp_included: bool
    tagline: str


PLAN_SPECS: dict[str, PlanSpec] = {
    FREE: PlanSpec(
        FREE, "Free", 0, max_orgs=0, resource_quota=100, mcp_included=False,
        tagline="Publish as an individual. Up to 100 resources.",
    ),
    PRO: PlanSpec(
        PRO, "Pro", 20, max_orgs=2, resource_quota=500, mcp_included=True,
        tagline="Up to 2 organizations, 500 resources each, MCP included.",
    ),
    ENTERPRISE: PlanSpec(
        ENTERPRISE, "Enterprise", 100, max_orgs=None, resource_quota=None, mcp_included=True,
        tagline="Unlimited organizations and resources. MCP unlimited.",
    ),
}


def normalize_plan(plan: str | None) -> str:
    if not plan:
        return FREE
    p = plan.strip().upper()
    if p == "PREMIUM":  # legacy binary tier → top tier so nothing regresses
        return ENTERPRISE
    return p if p in _RANK else FREE


def plan_rank(plan: str | None) -> int:
    return _RANK[normalize_plan(plan)]


def plan_at_least(plan: str | None, minimum: str) -> bool:
    return plan_rank(plan) >= _RANK[minimum]


def spec_for(plan: str | None) -> PlanSpec:
    return PLAN_SPECS[normalize_plan(plan)]


# --------------------------------------------------------------------------- #
# Usage counters
# --------------------------------------------------------------------------- #

def _org_scope_ids(db: Session, org_id: str) -> tuple[list[str], list[str]]:
    project_ids = [r[0] for r in db.query(Project.id).filter(Project.org_id == org_id).all()]
    pod_ids = [
        r[0]
        for r in db.query(Pod.id)
        .join(Project, Pod.project_id == Project.id)
        .filter(Project.org_id == org_id)
        .all()
    ]
    return project_ids, pod_ids


def org_resource_usage(db: Session, org: Organization) -> int:
    """Resources homed anywhere in the org subtree (ORG + its projects + pods)."""
    project_ids, pod_ids = _org_scope_ids(db, org.id)
    clauses = [and_(Resource.scope_type == "ORG", Resource.scope_id == org.id)]
    if project_ids:
        clauses.append(and_(Resource.scope_type == "PROJECT", Resource.scope_id.in_(project_ids)))
    if pod_ids:
        clauses.append(and_(Resource.scope_type == "POD", Resource.scope_id.in_(pod_ids)))
    return db.query(func.count(Resource.id)).filter(or_(*clauses)).scalar() or 0


def publisher_resource_usage(db: Session, user: User) -> int:
    """A user's own marketplace (PUBLIC) resources."""
    return (
        db.query(func.count(Resource.id))
        .filter(Resource.scope_type == "PUBLIC", Resource.author_id == user.id)
        .scalar()
        or 0
    )


def user_org_count(db: Session, user: User) -> int:
    """Organizations this user owns (the entity that consumes the max_orgs quota)."""
    return db.query(func.count(Organization.id)).filter(Organization.owner_id == user.id).scalar() or 0


# --------------------------------------------------------------------------- #
# Entitlement checks (MCP)
# --------------------------------------------------------------------------- #

def mcp_included_for_user(db: Session, user: User) -> bool:
    """MCP is included if the user's personal plan grants it OR they belong to
    any org whose plan grants it."""
    if spec_for(user.plan).mcp_included:
        return True
    for m in db.query(OrgMember).filter(OrgMember.user_id == user.id).all():
        org = db.get(Organization, m.org_id)
        if org and spec_for(org.plan).mcp_included:
            return True
    return False


# --------------------------------------------------------------------------- #
# Enforcement (raise on violation)
# --------------------------------------------------------------------------- #

def enforce_can_create_org(db: Session, user: User) -> None:
    spec = spec_for(user.plan)
    if spec.max_orgs == 0:
        raise payment_required(
            "Creating organizations requires a paid plan. Upgrade to Pro to create up to 2 organizations."
        )
    if spec.max_orgs is not None and user_org_count(db, user) >= spec.max_orgs:
        raise payment_required(
            f"Your {spec.name} plan allows up to {spec.max_orgs} organizations. "
            "Upgrade to Enterprise for unlimited organizations."
        )


def _resolve_owning_org(db: Session, scope_type: str, scope_id: str | None) -> Organization | None:
    if scope_type == "ORG":
        return db.get(Organization, scope_id) if scope_id else None
    if scope_type == "PROJECT":
        proj = db.get(Project, scope_id) if scope_id else None
        return db.get(Organization, proj.org_id) if proj else None
    if scope_type == "POD":
        pod = db.get(Pod, scope_id) if scope_id else None
        proj = db.get(Project, pod.project_id) if pod else None
        return db.get(Organization, proj.org_id) if proj else None
    return None


def enforce_can_add_resource(db: Session, user: User, scope_type: str, scope_id: str | None) -> None:
    """Block resource creation once the owning entity hits its quota (spec §2)."""
    if scope_type == "PUBLIC":
        spec = spec_for(user.plan)
        if spec.resource_quota is not None and publisher_resource_usage(db, user) >= spec.resource_quota:
            raise payment_required(
                f"Your {spec.name} plan allows up to {spec.resource_quota} published resources. "
                "Upgrade to publish more."
            )
        return
    org = _resolve_owning_org(db, scope_type, scope_id)
    if org is None:
        return
    spec = spec_for(org.plan)
    if spec.resource_quota is not None and org_resource_usage(db, org) >= spec.resource_quota:
        raise payment_required(
            f'"{org.name}" is on the {spec.name} plan (limit {spec.resource_quota} resources). '
            "Upgrade the organization to add more."
        )


# --------------------------------------------------------------------------- #
# Summaries (for /me, org settings, pricing page)
# --------------------------------------------------------------------------- #

def user_entitlements(db: Session, user: User) -> dict:
    spec = spec_for(user.plan)
    return {
        "plan": spec.key,
        "plan_name": spec.name,
        "publisher_resource_quota": spec.resource_quota,
        "publisher_resource_used": publisher_resource_usage(db, user),
        "max_orgs": spec.max_orgs,
        "orgs_owned": user_org_count(db, user),
        "mcp_included": mcp_included_for_user(db, user),
    }


def org_entitlements(db: Session, org: Organization) -> dict:
    spec = spec_for(org.plan)
    return {
        "plan": spec.key,
        "plan_name": spec.name,
        "resource_quota": spec.resource_quota,
        "resource_used": org_resource_usage(db, org),
        "mcp_included": spec.mcp_included,
    }


def plan_catalog() -> list[dict]:
    """Public pricing data (drives the marketing pricing page)."""
    return [
        {
            "key": s.key,
            "name": s.name,
            "price_usd": s.price_usd,
            "max_orgs": s.max_orgs,
            "resource_quota": s.resource_quota,
            "mcp_included": s.mcp_included,
            "tagline": s.tagline,
        }
        for s in PLAN_SPECS.values()
    ]
