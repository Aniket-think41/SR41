"""3.6 Public marketplace — no auth required (starred_by_me resolves when a
token is present so the dashboard's star states work)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found
from ..models import Resource, User
from ..security import get_current_user_optional
from ..serialize import filter_resources, resource_out, sort_resources, user_out

router = APIRouter(prefix="/api/public", tags=["public"])


def _list_params(
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str | None = Query(default=None),
):
    return {"q": q, "type_": type, "tag": tag, "sort": sort}


def _public_rows(db: Session) -> list[Resource]:
    return db.query(Resource).filter(Resource.is_public.is_(True)).all()


@router.get("/resources")
def public_resources(
    params: dict = Depends(_list_params),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    rows = sort_resources(filter_resources(_public_rows(db), params["q"], params["type_"], params["tag"]), params["sort"])
    return [resource_out(db, r, user) for r in rows]


@router.get("/resources/{resource_id}")
def public_resource(
    resource_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    r = db.get(Resource, resource_id)
    if not r or not r.is_public:
        raise not_found("Resource")
    return resource_out(db, r, user)


@router.get("/publishers/{username}")
def publisher(
    username: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    pub = db.query(User).filter(User.username == username).first()
    if not pub:
        raise not_found("Publisher")
    rows = db.query(Resource).filter(Resource.is_public.is_(True), Resource.author_id == pub.id).all()
    return {**user_out(pub), "resources": [resource_out(db, r, user) for r in rows]}


@router.get("/search")
def public_search(
    params: dict = Depends(_list_params),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    rows = sort_resources(filter_resources(_public_rows(db), params["q"], params["type_"], params["tag"]), params["sort"])
    return [resource_out(db, r, user) for r in rows]
