"""3.8 Profiles — GitHub-style profile page data (§8 additions)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found
from ..models import (
    Activity,
    Follow,
    Organization,
    OrgMember,
    Resource,
    ResourcePin,
    ResourceStar,
    User,
    now,
)
from ..security import get_current_user
from ..serialize import activity_out, filter_resources, org_out, resource_out, sort_resources, user_out

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_or_404(db: Session, username: str) -> User:
    u = db.query(User).filter(User.username == username).first()
    if not u:
        raise not_found("User")
    return u


def _visible_resources(db: Session, target: User, viewer: User) -> list[Resource]:
    """Own profile → everything; someone else's → public only (§4.2)."""
    q = db.query(Resource).filter(Resource.author_id == target.id)
    if viewer.id != target.id:
        q = q.filter(Resource.is_public.is_(True))
    return q.all()


@router.get("/{username}")
def profile(username: str, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _user_or_404(db, username)
    mine = db.query(Resource).filter(Resource.author_id == target.id).all()
    return {
        **user_out(target),
        "stats": {
            "resources": len(mine),
            "public_resources": sum(1 for r in mine if r.is_public),
            "stars_received": sum(r.stars_count for r in mine),
            "stars_given": db.query(ResourceStar).filter(ResourceStar.user_id == target.id).count(),
            "orgs": db.query(OrgMember).filter(OrgMember.user_id == target.id).count(),
            "followers": db.query(Follow).filter(Follow.publisher_id == target.id).count(),
            "following": db.query(Follow).filter(Follow.follower_id == target.id).count(),
        },
    }


@router.get("/{username}/resources")
def user_resources(
    username: str,
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = _user_or_404(db, username)
    rows = sort_resources(filter_resources(_visible_resources(db, target, viewer), q, type, tag), sort)
    return [resource_out(db, r, viewer) for r in rows]


@router.get("/{username}/starred")
def user_starred(username: str, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _user_or_404(db, username)
    ids = [s.resource_id for s in db.query(ResourceStar).filter(ResourceStar.user_id == target.id).all()]
    rows = db.query(Resource).filter(Resource.id.in_(ids or [""])).all()
    if viewer.id != target.id:
        rows = [r for r in rows if r.is_public]
    return [resource_out(db, r, viewer) for r in rows]


@router.get("/{username}/pinned")
def user_pinned(username: str, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resources the user pinned to their profile, in pin order. Someone else's
    profile shows only pins that are public (own profile shows all)."""
    target = _user_or_404(db, username)
    pins = (
        db.query(ResourcePin)
        .filter(ResourcePin.user_id == target.id)
        .order_by(ResourcePin.position, ResourcePin.created_at)
        .all()
    )
    out = []
    for p in pins:
        r = db.get(Resource, p.resource_id)
        if r and (viewer.id == target.id or r.is_public):
            out.append(resource_out(db, r, viewer))
    return out


@router.get("/{username}/contributions")
def user_contributions(
    username: str,
    weeks: int = Query(default=26, ge=1, le=53),
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GitHub-style contribution heatmap. A "contribution" is a resource the user
    authored or a star they gave, bucketed per day over the trailing window.
    Derived from durable data (not just the activity log) so history is intact
    even for backfilled/seeded accounts."""
    target = _user_or_404(db, username)
    total_days = weeks * 7
    end = now().date()
    start = end - timedelta(days=total_days - 1)

    counts: dict[str, int] = {}

    def bump(d) -> None:
        if d is None:
            return
        day = d.date() if hasattr(d, "date") else d
        if start <= day <= end:
            key = day.isoformat()
            counts[key] = counts.get(key, 0) + 1

    for r in _visible_resources(db, target, viewer):
        bump(r.created_at)
    for s in db.query(ResourceStar).filter(ResourceStar.user_id == target.id).all():
        bump(s.created_at)

    days = []
    for i in range(total_days):
        key = (start + timedelta(days=i)).isoformat()
        days.append({"date": key, "count": counts.get(key, 0)})
    return {
        "weeks": weeks,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total": sum(counts.values()),
        "max": max(counts.values(), default=0),
        "days": days,
    }


@router.get("/{username}/activity")
def user_activity(username: str, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _user_or_404(db, username)
    rows = (
        db.query(Activity)
        .filter(Activity.user_id == target.id)
        .order_by(Activity.created_at.desc())
        .limit(20)
        .all()
    )
    return [activity_out(a) for a in rows]


@router.get("/{username}/orgs")
def user_orgs(username: str, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _user_or_404(db, username)
    # v1: org chips are visible to any signed-in viewer (profiles are in-app only).
    # When public profiles ship, filter by org.is_public for non-self viewers.
    out = []
    for m in db.query(OrgMember).filter(OrgMember.user_id == target.id).all():
        org = db.get(Organization, m.org_id)
        if org:
            out.append(org_out(org, m.role))
    return out
