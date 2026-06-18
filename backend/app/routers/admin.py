"""Platform-admin content management (User.is_admin only).

Manages the marketing site's blog posts (with draft|published status so old
posts can be hidden and new ones staged), the changelog, and legal pages
(privacy/terms). Also verifies publishers. The public, read-only views of this
content live under /api/public; everything here requires an admin token.
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import Boolean, Integer
from sqlalchemy import JSON as SAJSON
from sqlalchemy.orm import Session

from ..database import Base, get_db
from ..errors import conflict, not_found, validation
from ..models import BlogPost, ChangelogEntry, ContentPage, Feedback, User
from ..permissions import require_admin
from ..schemas import (
    AdminRowPatch,
    BlogPostCreate,
    BlogPostPatch,
    ChangelogCreate,
    ChangelogPatch,
    ContentPagePatch,
    FeedbackStatusIn,
    VerifyPublisherIn,
)
from ..security import get_current_user
from ..serialize import blog_post_out, changelog_out, content_page_out, feedback_out, user_out

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


# ---- feedback triage ----


@router.get("/feedback")
def list_feedback(
    status: str | None = None,
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    """The full feedback queue, newest first. Filter with ?status=open|reviewed."""
    q = db.query(Feedback)
    if status in ("open", "reviewed"):
        q = q.filter(Feedback.status == status)
    rows = q.order_by(Feedback.created_at.desc()).all()
    return [feedback_out(db, f, include_user=True) for f in rows]


@router.post("/feedback/{feedback_id}/status")
def set_feedback_status(
    feedback_id: str,
    body: FeedbackStatusIn,
    _: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    """Mark a feedback item reviewed (or reopen it)."""
    fb = db.get(Feedback, feedback_id)
    if not fb:
        raise not_found("Feedback")
    fb.status = body.status
    db.commit()
    return feedback_out(db, fb, include_user=True)


# ---- table browser (dev admin dashboard) ----


def _get_model_map() -> dict:
    """Map table names to their SQLAlchemy model classes."""
    mapper = {}
    for model in Base.registry.mappers:
        mapper[model.class_.__tablename__] = model.class_
    return mapper


def _model_or_404(table_name: str):
    model = _get_model_map().get(table_name)
    if not model:
        raise not_found(f'Table "{table_name}"')
    return model


def _row_to_dict(model, row) -> dict:
    d = {}
    for c in model.__table__.columns:
        val = getattr(row, c.name)
        if hasattr(val, "isoformat"):  # datetime/date → ISO string for display
            val = val.isoformat()
        d[c.name] = val
    return d


def _coerce(col, value):
    """Coerce a JSON value from the browser into the column's Python type so an
    inline edit ("true", "42", a JSON object) lands as the right type."""
    if value is None:
        return None
    col_type = col.type
    try:
        if isinstance(col_type, Boolean):
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("true", "1", "yes", "on")
        if isinstance(col_type, Integer):
            return int(value)
        if isinstance(col_type, SAJSON):
            return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise validation(f'Could not parse value for "{col.name}": {e}')
    return value


@router.get("/tables")
def list_tables(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    """List all database tables with approximate row counts."""
    models = _get_model_map()
    tables = []
    for name, model in sorted(models.items()):
        try:
            count = db.query(model).count()
        except Exception:
            count = -1
        tables.append({"name": name, "count": count})
    return {"tables": tables}


@router.get("/tables/{table_name}")
def browse_table(table_name: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Return all rows from a table as a JSON array. Includes column names."""
    model = _model_or_404(table_name)
    rows = db.query(model).order_by(model.id).all() if hasattr(model, "id") else db.query(model).all()
    cols = [c.name for c in model.__table__.columns]
    data = [_row_to_dict(model, row) for row in rows]
    return {"table": table_name, "columns": cols, "rows": len(data), "data": data}


@router.patch("/tables/{table_name}/{row_id}")
def update_row(
    table_name: str, row_id: str, body: AdminRowPatch,
    _: User = Depends(admin_user), db: Session = Depends(get_db),
):
    """Edit a row in place (platform-admin only). Updates are coerced to each
    column's type; the primary key column is never modified. Direct DB write —
    bypasses app-level validation, so use with care."""
    model = _model_or_404(table_name)
    obj = db.get(model, row_id)
    if not obj:
        raise not_found(f'Row "{row_id}"')
    cols = {c.name: c for c in model.__table__.columns}
    pk = {c.name for c in model.__table__.primary_key.columns}
    for field, value in body.updates.items():
        if field not in cols or field in pk:
            continue  # ignore unknown columns and never reassign the primary key
        setattr(obj, field, _coerce(cols[field], value))
    db.commit()
    return _row_to_dict(model, obj)


@router.delete("/tables/{table_name}/{row_id}")
def delete_row(table_name: str, row_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Delete a row by primary key (platform-admin only). No cascade — related
    rows in other tables are left as-is."""
    model = _model_or_404(table_name)
    obj = db.get(model, row_id)
    if not obj:
        raise not_found(f'Row "{row_id}"')
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(_: User = Depends(admin_user)):
    """Admin HTML dashboard for browsing all database tables."""
    html_path = Path(__file__).resolve().parent.parent / "templates" / "admin.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Admin dashboard template not found</h1>", status_code=500)


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
