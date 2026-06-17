"""Product feedback — a rating + message users can send from anywhere
(dashboard CTA, `skillshare feedback`, or the MCP `submit_feedback` tool).

Feedback is about the platform in general or a specific resource. Anyone signed
in can submit and list their own; platform admins (User.is_admin) read the full
queue and mark items reviewed (the same admin role that manages marketing
content). Kept deliberately simple: one table, no threading, no per-org routing.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found, validation
from ..models import Feedback, Resource, User, now
from ..permissions import require_admin
from ..schemas import FeedbackIn, FeedbackStatusIn
from ..security import get_current_user
from ..serialize import feedback_out

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit feedback. Requires auth so we know who to follow up with; the
    submitter is never shown publicly. A resource-scoped item must point at a
    resource that exists and is visible as a public/marketplace entry-or one the
    caller can otherwise reference."""
    if body.target_type == "resource":
        if not body.target_id:
            raise validation("`target_id` is required when target_type is 'resource'")
        if not db.get(Resource, body.target_id):
            raise not_found("Resource")
    fb = Feedback(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id if body.target_type == "resource" else None,
        rating=body.rating,
        category=body.category,
        message=body.message.strip(),
        source=body.source,
        context=body.context,
    )
    db.add(fb)
    db.commit()
    return feedback_out(db, fb)


@router.get("/mine")
def list_my_feedback(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
):
    """The caller's own submissions, newest first."""
    rows = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id)
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [feedback_out(db, f) for f in rows]
