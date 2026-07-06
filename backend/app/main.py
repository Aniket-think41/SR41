"""
SkillShare API — FastAPI implementation of backend/BACKEND_SPEC.md.

The dashboard client (../client) attaches by setting
NEXT_PUBLIC_API_URL to this server's origin; the wire format matches
client/src/lib/types.ts exactly.
"""

import logging
import os

from fastapi import FastAPI

# Route app-level log messages to stdout so Cloud Logging picks them up.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, engine
from .errors import install_handlers
from .ratelimit import RateLimitMiddleware
from .routers import (
    admin,
    auth,
    billing,
    feedback,
    local_state,
    members,
    notifications,
    orgs,
    pods,
    projects,
    public,
    resources,
    users,
)

settings = get_settings()


def _init_sentry() -> None:
    """Error monitoring (spec §8). No-op unless SENTRY_DSN is set and the SDK is
    installed — adding the DSN later activates it with no code change."""
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            environment=settings.env,
        )
        logging.getLogger("app.sentry").info("Sentry error monitoring enabled")
    except Exception:  # pragma: no cover
        logging.getLogger("app.sentry").warning("Sentry DSN set but sentry_sdk unavailable — skipping")


_init_sentry()

app = FastAPI(
    title="SkillShare API",
    version="1.0.0",
    description="Skill & MCP registry — orgs, projects, pods, resources, marketplace.",
)

# v1: create tables on boot. Move to Alembic migrations before real prod data.
Base.metadata.create_all(bind=engine)


def _ensure_additive_columns() -> None:
    """Tiny stand-in for migrations: create_all() never ALTERs existing tables,
    so additive columns on tables that already exist in prod (Neon) must be added
    by hand. Idempotent — only adds a column when the live table lacks it. Works
    for both SQLite (dev) and Postgres (prod)."""
    from sqlalchemy import inspect, text

    log = logging.getLogger("app.migrate")
    # (table, column, DDL type with default) — keep in sync with models.py.
    additive = [
        ("users", "must_change_password", "BOOLEAN NOT NULL DEFAULT FALSE"),
        # Personal/publisher subscription tier (spec §2). Existing users default
        # to FREE, matching the free-publisher baseline.
        ("users", "plan", "VARCHAR NOT NULL DEFAULT 'FREE'"),
        # Nullable, NO default: legacy rows stay NULL, which the read logic
        # interprets as the home-scope default (pod resources become pod-private,
        # project resources project-private) — matching the scoped-visibility
        # intent rather than leaving everything org-wide.
        ("resources", "visibility", "VARCHAR"),
        # Review workflow (spec §3). Existing public resources are grandfathered in
        # as approved so nothing disappears from the marketplace on deploy.
        ("resources", "approval_status", "VARCHAR NOT NULL DEFAULT 'approved'"),
        ("resources", "review_note", "VARCHAR"),
        ("resources", "reviewed_by", "VARCHAR"),
        ("resources", "reviewed_at", "TIMESTAMP"),
        # Public feedback (spec §4): anonymous website submissions + moderation.
        ("feedback", "author_name", "VARCHAR"),
        ("feedback", "author_email", "VARCHAR"),
        ("feedback", "public_status", "VARCHAR NOT NULL DEFAULT 'pending'"),
        # Activity client source (spec §7): web | cli | mcp | api.
        ("activities", "source", "VARCHAR NOT NULL DEFAULT 'web'"),
    ]
    # One-off NOT NULL relaxations (Postgres only — SQLite dev DBs are rebuilt by
    # create_all). feedback.user_id must allow NULL for anonymous website feedback.
    relax_not_null = [("feedback", "user_id")]
    # Composite indexes for hot read paths (spec §8). CREATE INDEX IF NOT EXISTS
    # works on both SQLite and Postgres and is idempotent.
    indexes = [
        ("ix_resources_public_approval", "resources", "is_public, approval_status"),
        ("ix_activities_user_created", "activities", "user_id, created_at"),
        ("ix_activities_org_created", "activities", "org_id, created_at"),
        ("ix_notifications_user_read", "notifications", "user_id, read_at"),
    ]
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        is_postgres = engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            for table, column, ddl in additive:
                if table not in existing_tables:
                    continue  # create_all() just made it with the column already
                cols = {c["name"] for c in inspector.get_columns(table)}
                if column in cols:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                log.info("Added column %s.%s", table, column)
            if is_postgres:
                for table, column in relax_not_null:
                    if table not in existing_tables:
                        continue
                    col = next((c for c in inspector.get_columns(table) if c["name"] == column), None)
                    if col is not None and not col.get("nullable", True):
                        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL"))
                        log.info("Relaxed NOT NULL on %s.%s", table, column)
            for name, table, cols in indexes:
                if table in existing_tables:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))
    except Exception:
        log.exception("Additive column migration failed")


_ensure_additive_columns()


def _bootstrap_admin() -> None:
    """On production startup, create or promote an admin user from env vars.
    This is the bootstrap path for deployments that don't run the seed script."""
    log = logging.getLogger("app.bootstrap")
    if not settings.admin_email or not settings.admin_password:
        log.info("Admin bootstrap skipped: ADMIN_EMAIL or ADMIN_PASSWORD not set")
        return
    from .database import SessionLocal
    from .models import User
    from .security import hash_password

    db = SessionLocal()
    try:
        email = settings.admin_email.lower().strip()
        user = db.query(User).filter(User.email == email).first()
        if user:
            if not user.is_admin:
                user.is_admin = True
                db.commit()
                log.info("Admin bootstrap: promoted %s to admin", email)
        else:
            import re

            slug = re.sub(r"[^a-z0-9]+", "-", email.split("@")[0]).strip("-") or "admin"
            user = User(
                email=email,
                password_hash=hash_password(settings.admin_password),
                username=slug,
                display_name="Admin",
                is_admin=True,
            )
            db.add(user)
            db.commit()
            log.info("Admin bootstrap: created admin user %s", email)
    except Exception:
        log.exception("Admin bootstrap failed")
    finally:
        db.close()


_bootstrap_admin()
install_handlers(app)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,  # refresh-token cookie (§4.1)
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(pods.router)
app.include_router(members.router)
app.include_router(resources.router)
app.include_router(public.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(local_state.router)
app.include_router(feedback.router)
app.include_router(billing.router)
app.include_router(admin.router)

# Serve locally-stored uploads when STORAGE_BACKEND=local (no-op for S3, which
# serves files from the bucket/CDN). Files land here from POST /api/uploads.
if settings.storage_backend == "local":
    os.makedirs(settings.upload_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "skillshare-api",
        "env": settings.env,
        "admin_email_set": bool(settings.admin_email),
        "admin_password_set": bool(settings.admin_password),
    }
