"""
Resource review workflow (spec §3).

A resource that wants public visibility carries ``is_public`` (the intent) plus
``approval_status`` (pending | approved | rejected). Review authority depends on
ownership:

  - publisher (PUBLIC-scope) content  → **platform admin** approves
  - org-owned content (ORG/PROJECT/POD)→ **org admin** approves (the org vouches
    for its own content); platform admins can also approve/reject anything.

Only ``approved`` + ``is_public`` resources appear on public read paths. A
resource published by someone who is already its reviewer is auto-approved; a
rejection carries a reason and unpublishes it, and the author may edit + resubmit
(PATCH re-runs :func:`submit_for_review`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import Notification, OrgMember, Organization, Resource, User
from .permissions import scope_org


def is_org_admin(db: Session, org: Organization | None, user: User) -> bool:
    if not org:
        return False
    m = (
        db.query(OrgMember)
        .filter(OrgMember.org_id == org.id, OrgMember.user_id == user.id)
        .first()
    )
    return bool(m and m.role == "ADMIN")


def can_review(db: Session, r: Resource, user: User) -> bool:
    """Whether ``user`` may approve/reject ``r`` for public listing."""
    if user.is_admin:
        return True
    return is_org_admin(db, scope_org(db, r), user)


def _mark(r: Resource, status: str, reviewer_id: str | None, note: str | None) -> None:
    r.approval_status = status
    r.review_note = note
    r.reviewed_by = reviewer_id
    r.reviewed_at = datetime.now(timezone.utc)


def _notify_author(db: Session, r: Resource, actor: User, verb: str, note: str | None = None) -> None:
    if r.author_id == actor.id:
        return  # never notify yourself about your own review action
    org = scope_org(db, r)
    db.add(
        Notification(
            user_id=r.author_id,
            actor_id=actor.id,
            org_id=org.id if org else None,
            scope_type=r.scope_type,
            scope_id=r.scope_id,
            verb=verb,
            object_type="resource",
            object_id=r.id,
            object_title=r.title,
            meta=note,
        )
    )


def submit_for_review(db: Session, r: Resource, actor: User) -> None:
    """Queue a resource for public listing. Auto-approves when the actor is
    already its reviewer; otherwise sets it pending."""
    if can_review(db, r, actor):
        _mark(r, "approved", actor.id, None)
    else:
        _mark(r, "pending", None, None)


def approve(db: Session, r: Resource, reviewer: User) -> None:
    _mark(r, "approved", reviewer.id, None)
    if not r.is_public:
        r.is_public = True  # approving a queued item makes it live
    _notify_author(db, r, reviewer, "approved")


def reject(db: Session, r: Resource, reviewer: User, note: str | None) -> None:
    _mark(r, "rejected", reviewer.id, note)
    r.is_public = False  # rejected content is not live
    _notify_author(db, r, reviewer, "rejected", note=note)


def is_publicly_visible(r: Resource) -> bool:
    """The single gate every public read path must apply."""
    return bool(r.is_public) and r.approval_status == "approved"
