"""3.6 Public marketplace — no auth required (starred_by_me resolves when a
token is present so the dashboard's star states work)."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found, validation
from ..models import BlogPost, ChangelogEntry, ContentPage, Follow, Organization, Resource, User
from ..security import get_current_user, get_current_user_optional
from ..serialize import (
    blog_post_out,
    changelog_out,
    content_page_out,
    resource_out,
    search_rank,
    user_out,
)

router = APIRouter(prefix="/api/public", tags=["public"])


def _list_params(
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    publisher: str | None = Query(default=None),
):
    return {"q": q, "type_": type, "tag": tag, "sort": sort, "publisher": publisher}


def _public_rows(db: Session) -> list[Resource]:
    return db.query(Resource).filter(Resource.is_public.is_(True)).all()


def _org_name_map(db: Session) -> dict[str, str]:
    return {oid: name for oid, name in db.query(Organization.id, Organization.name).all()}


def _publisher_label(r: Resource, org_names: dict[str, str]) -> str:
    """Who a public resource is published by: the owning organization for
    org-scoped resources, otherwise the individual author. Mirrors the
    dashboard marketplace's attribution so the publisher filter matches."""
    if r.scope_type == "ORG" and r.scope_id:
        return org_names.get(r.scope_id, "")
    return r.author.display_name if r.author else ""


@router.get("/resources")
def public_resources(
    response: Response,
    params: dict = Depends(_list_params),
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    rows = search_rank(_public_rows(db), params["q"], params["type_"], params["tag"], params["sort"])
    if params.get("publisher"):
        org_names = _org_name_map(db)
        rows = [r for r in rows if _publisher_label(r, org_names) == params["publisher"]]
    # Total AFTER filtering, BEFORE paging — drives the client's page count.
    response.headers["X-Total-Count"] = str(len(rows))
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    if limit is not None:
        rows = rows[offset : offset + limit]
    return [resource_out(db, r, user) for r in rows]


@router.get("/facets")
def public_facets(db: Session = Depends(get_db)):
    """Lightweight filter facets — top tags (with counts) and the list of
    publishers (organizations or authors) — so the marketplace filter panel
    doesn't have to download every resource (and their content) just to build
    the sidebar."""
    org_names = _org_name_map(db)
    rows = (
        db.query(Resource.tags, Resource.scope_type, Resource.scope_id, User.display_name)
        .join(User, User.id == Resource.author_id, isouter=True)
        .filter(Resource.is_public.is_(True))
        .all()
    )
    tag_counts: dict[str, int] = {}
    publishers: set[str] = set()
    for tags, scope_type, scope_id, author_name in rows:
        for t in tags or []:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        if scope_type == "ORG" and scope_id:
            publishers.add(org_names.get(scope_id, ""))
        elif author_name:
            publishers.add(author_name)
    top_tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    return {
        "tags": [[t, n] for t, n in top_tags],
        "publishers": sorted(p for p in publishers if p),
    }


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
    followers_count = db.query(Follow).filter(Follow.publisher_id == pub.id).count()
    following = bool(
        user
        and db.query(Follow.id)
        .filter(Follow.publisher_id == pub.id, Follow.follower_id == user.id)
        .first()
    )
    return {
        **user_out(pub),
        "resources": [resource_out(db, r, user) for r in rows],
        "followers_count": followers_count,
        "following": following,
    }


def _publisher_or_404(db: Session, username: str) -> User:
    pub = db.query(User).filter(User.username == username).first()
    if not pub:
        raise not_found("Publisher")
    return pub


@router.post("/publishers/{username}/follow")
def follow_publisher(username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Follow a publisher — you'll be notified when they publish to the
    marketplace (see resources.publish → notify_followers)."""
    pub = _publisher_or_404(db, username)
    if pub.id == user.id:
        raise validation("You can't follow yourself")
    exists = (
        db.query(Follow)
        .filter(Follow.publisher_id == pub.id, Follow.follower_id == user.id)
        .first()
    )
    if not exists:
        db.add(Follow(follower_id=user.id, publisher_id=pub.id))
        db.commit()
    return {"following": True, "followers_count": db.query(Follow).filter(Follow.publisher_id == pub.id).count()}


@router.delete("/publishers/{username}/follow")
def unfollow_publisher(username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pub = _publisher_or_404(db, username)
    db.query(Follow).filter(Follow.publisher_id == pub.id, Follow.follower_id == user.id).delete()
    db.commit()
    return {"following": False, "followers_count": db.query(Follow).filter(Follow.publisher_id == pub.id).count()}


@router.get("/search")
def public_search(
    params: dict = Depends(_list_params),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    rows = search_rank(_public_rows(db), params["q"], params["type_"], params["tag"], params["sort"])
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
