"""Local-artifact provenance & dismissal memory (F2).

The CLI/MCP scan a user's machine for local skills/MCP/notes and reconcile them
against this server-side state so a "pushed" or "dismissed" decision is
remembered across machines. Keyed by content fingerprint (per user)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LocalArtifactState, User
from ..schemas import LocalStateIn
from ..security import get_current_user

router = APIRouter(prefix="/api/local-state", tags=["local-state"])


def _out(s: LocalArtifactState) -> dict:
    return {
        "fingerprint": s.fingerprint,
        "kind": s.kind,
        "source": s.source,
        "status": s.status,
        "resource_id": s.resource_id,
        "name": s.name,
        "updated_at": s.updated_at,
    }


@router.get("")
def list_local_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """All provenance/dismissal rows for the caller — the CLI/MCP use this to
    filter scan results down to genuinely new candidates."""
    rows = db.query(LocalArtifactState).filter(LocalArtifactState.user_id == user.id).all()
    return [_out(s) for s in rows]


@router.post("")
def upsert_local_state(
    body: LocalStateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Record a decision for a fingerprint (pushed / dismissed). Upsert keyed by
    (user, fingerprint) so re-pushing or re-dismissing the same artifact updates
    in place."""
    row = (
        db.query(LocalArtifactState)
        .filter(LocalArtifactState.user_id == user.id, LocalArtifactState.fingerprint == body.fingerprint)
        .first()
    )
    if row:
        row.kind = body.kind
        row.status = body.status
        row.source = body.source
        row.resource_id = body.resource_id
        row.name = body.name
    else:
        row = LocalArtifactState(
            user_id=user.id,
            fingerprint=body.fingerprint,
            kind=body.kind,
            status=body.status,
            source=body.source,
            resource_id=body.resource_id,
            name=body.name,
        )
        db.add(row)
    db.commit()
    return _out(row)
