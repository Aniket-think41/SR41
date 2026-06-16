"""3.6 Public marketplace — no auth required (starred_by_me resolves when a
token is present so the dashboard's star states work)."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found
from ..models import BlogPost, ChangelogEntry, ContentPage, Resource, User
from ..security import get_current_user_optional
from ..serialize import (
    blog_post_out,
    changelog_out,
    content_page_out,
    filter_resources,
    resource_out,
    sort_resources,
    user_out,
)

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
    response: Response,
    params: dict = Depends(_list_params),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    rows = sort_resources(filter_resources(_public_rows(db), params["q"], params["type_"], params["tag"]), params["sort"])
    # Total before paging — let the client drive "load more" / page counts.
    response.headers["X-Total-Count"] = str(len(rows))
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    if limit is not None:
        rows = rows[offset : offset + limit]
    return [resource_out(db, r, user) for r in rows]


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    """Aggregate counts for the marketplace hero — so the landing page can show
    totals without fetching the whole catalog."""
    rows = _public_rows(db)

    def count(t: str) -> int:
        return sum(1 for r in rows if r.type == t)

    return {
        "skills": count("SKILL"),
        "mcp": count("MCP"),
        "notes": count("NOTE"),
        "total_installs": sum(r.installs_count for r in rows),
        "total": len(rows),
    }


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


# ---- marketing content (blog, changelog, legal pages) ----
# Only published content is exposed here; drafts live behind /api/admin.


@router.get("/blog")
def public_blog(db: Session = Depends(get_db)):
    rows = (
        db.query(BlogPost)
        .filter(BlogPost.status == "published")
        .order_by(BlogPost.date.desc())
        .all()
    )
    return [blog_post_out(p) for p in rows]


@router.get("/blog/{slug}")
def public_blog_post(slug: str, db: Session = Depends(get_db)):
    p = db.query(BlogPost).filter(BlogPost.slug == slug, BlogPost.status == "published").first()
    if not p:
        raise not_found("Post")
    return blog_post_out(p)


@router.get("/changelog")
def public_changelog(db: Session = Depends(get_db)):
    rows = (
        db.query(ChangelogEntry)
        .filter(ChangelogEntry.status == "published")
        .order_by(ChangelogEntry.date.desc())
        .all()
    )
    return [changelog_out(c) for c in rows]


@router.get("/pages/{key}")
def public_page(key: str, db: Session = Depends(get_db)):
    p = db.query(ContentPage).filter(ContentPage.key == key, ContentPage.status == "published").first()
    if not p:
        raise not_found("Page")
    return content_page_out(p)
