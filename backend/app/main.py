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
    feedback,
    local_state,
    notifications,
    orgs,
    pods,
    projects,
    public,
    resources,
    users,
)

settings = get_settings()

app = FastAPI(
    title="SkillShare API",
    version="1.0.0",
    description="Skill & MCP registry — orgs, projects, pods, resources, marketplace.",
)

# v1: create tables on boot. Move to Alembic migrations before real prod data.
Base.metadata.create_all(bind=engine)

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
app.include_router(resources.router)
app.include_router(public.router)
app.include_router(users.router)
app.include_router(notifications.router)
app.include_router(local_state.router)
app.include_router(feedback.router)
app.include_router(admin.router)

# Serve locally-stored uploads when STORAGE_BACKEND=local (no-op for S3, which
# serves files from the bucket/CDN). Files land here from POST /api/uploads.
if settings.storage_backend == "local":
    os.makedirs(settings.upload_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "skillshare-api", "env": settings.env}
