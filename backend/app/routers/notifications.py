"""Per-user notification inbox (F1). Notifications are fanned out from activity
(see serialize.log_activity) to the members of the scope an event happened in.
Surfaced in the CLI (`skillshare inbox`), the MCP (`check_updates`), and the
dashboard bell."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import validation
from ..models import Notification, User, now
from ..schemas import NotificationReadIn
from ..security import get_current_user
from ..serialize import notification_out

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = Query(default=False),
    since: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    if since:
        try:
            dt = datetime.fromisoformat(since)
        except ValueError:
            raise validation("`since` must be an ISO-8601 timestamp")
        q = q.filter(Notification.created_at > dt)
    rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return [notification_out(db, n) for n in rows]


@router.get("/unread_count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user.id, Notification.read_at.is_(None))
        .scalar()
    )
    return {"count": count or 0}


@router.post("/read")
def mark_read(
    body: NotificationReadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.all and not body.ids:
        raise validation("Pass `ids` or `all: true`")
    q = db.query(Notification).filter(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if not body.all:
        q = q.filter(Notification.id.in_(body.ids))
    updated = q.update({Notification.read_at: now()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "marked": updated}
