"""Platform-admin content management (User.is_admin only).

Manages the marketing site's blog posts (with draft|published status so old
posts can be hidden and new ones staged), the changelog, and legal pages
(privacy/terms). Also verifies publishers. The public, read-only views of this
content live under /api/public; everything here requires an admin token.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import conflict, not_found
from ..models import BlogPost, ChangelogEntry, ContentPage, User
from ..permissions import require_admin
from ..schemas import (
    BlogPostCreate,
    BlogPostPatch,
    ChangelogCreate,
    ChangelogPatch,
    ContentPagePatch,
    VerifyPublisherIn,
)
from ..security import get_current_user
from ..serialize import blog_post_out, changelog_out, content_page_out, user_out

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_user(user: User = Depends(get_current_user)) -> User:
    return require_admin(user)


def _apply(obj, data: dict) -> None:
    for field, value in data.items():
        setattr(obj, field, value)


# ---- blog posts ----


@router.get("/blog")
def list_blog(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.query(BlogPost).order_by(BlogPost.date.desc()).all()
    return [blog_post_out(p, admin=True) for p in rows]


@router.post("/blog")
def create_blog(body: BlogPostCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.query(BlogPost.id).filter(BlogPost.slug == body.slug).first():
        raise conflict(f'A post with slug "{body.slug}" already exists')
    data = body.model_dump()
    data["body"] = [b for b in data["body"]]  # already plain dicts via model_dump
    post = BlogPost(**data)
    db.add(post)
    db.commit()
    return blog_post_out(post, admin=True)


@router.get("/blog/{post_id}")
def get_blog(post_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    post = db.get(BlogPost, post_id)
    if not post:
        raise not_found("Post")
    return blog_post_out(post, admin=True)


@router.patch("/blog/{post_id}")
def update_blog(post_id: str, body: BlogPostPatch, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    post = db.get(BlogPost, post_id)
    if not post:
        raise not_found("Post")
    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"] != post.slug:
        if db.query(BlogPost.id).filter(BlogPost.slug == data["slug"]).first():
            raise conflict(f'A post with slug "{data["slug"]}" already exists')
    _apply(post, data)
    db.commit()
    return blog_post_out(post, admin=True)


@router.post("/blog/{post_id}/publish")
def publish_blog(post_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    post = db.get(BlogPost, post_id)
    if not post:
        raise not_found("Post")
    post.status = "published"
    db.commit()
    return blog_post_out(post, admin=True)


@router.post("/blog/{post_id}/unpublish")
def unpublish_blog(post_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    post = db.get(BlogPost, post_id)
    if not post:
        raise not_found("Post")
    post.status = "draft"
    db.commit()
    return blog_post_out(post, admin=True)


@router.delete("/blog/{post_id}")
def delete_blog(post_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    post = db.get(BlogPost, post_id)
    if not post:
        raise not_found("Post")
    db.delete(post)
    db.commit()
    return {"ok": True}


# ---- changelog ----


@router.get("/changelog")
def list_changelog(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.query(ChangelogEntry).order_by(ChangelogEntry.date.desc()).all()
    return [changelog_out(c, admin=True) for c in rows]


@router.post("/changelog")
def create_changelog(body: ChangelogCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    entry = ChangelogEntry(**body.model_dump())
    db.add(entry)
    db.commit()
    return changelog_out(entry, admin=True)


@router.patch("/changelog/{entry_id}")
def update_changelog(entry_id: str, body: ChangelogPatch, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    entry = db.get(ChangelogEntry, entry_id)
    if not entry:
        raise not_found("Changelog entry")
    _apply(entry, body.model_dump(exclude_unset=True))
    db.commit()
    return changelog_out(entry, admin=True)


@router.delete("/changelog/{entry_id}")
def delete_changelog(entry_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    entry = db.get(ChangelogEntry, entry_id)
    if not entry:
        raise not_found("Changelog entry")
    db.delete(entry)
    db.commit()
    return {"ok": True}


# ---- legal / content pages (privacy, terms) ----


@router.get("/pages")
def list_pages(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [content_page_out(p, admin=True) for p in db.query(ContentPage).all()]


@router.get("/pages/{key}")
def get_page(key: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    page = db.query(ContentPage).filter(ContentPage.key == key).first()
    if not page:
        raise not_found("Page")
    return content_page_out(page, admin=True)


@router.patch("/pages/{key}")
def update_page(key: str, body: ContentPagePatch, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    page = db.query(ContentPage).filter(ContentPage.key == key).first()
    if not page:
        raise not_found("Page")
    _apply(page, body.model_dump(exclude_unset=True))
    db.commit()
    return content_page_out(page, admin=True)


# ---- publisher verification ----


@router.get("/publishers")
def list_publishers(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.is_publisher.is_(True)).order_by(User.created_at).all()
    return [user_out(u) for u in rows]


@router.post("/publishers/{username}/verify")
def verify_publisher(
    username: str,
    body: VerifyPublisherIn,
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    pub = db.query(User).filter(User.username == username).first()
    if not pub:
        raise not_found("Publisher")
    # Verifying implies they are a publisher; unverifying leaves is_publisher intact.
    if body.verified:
        pub.is_publisher = True
    pub.verified = body.verified
    db.commit()
    return user_out(pub)
