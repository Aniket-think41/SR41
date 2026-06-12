"""
SQLAlchemy models — mirror BACKEND_SPEC.md §2 and the client's
client/src/lib/types.ts field-for-field (wire format is snake_case).

Portability notes: tags/terminology use JSON columns so SQLite (dev) and
PostgreSQL (prod) both work; switch to ARRAY/JSONB via a migration if wanted.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("u"))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, default="")
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    is_publisher: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("org"))
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String, default="FREE")  # FREE | PREMIUM
    terminology: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {project, pod}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrgMember(Base):
    __tablename__ = "org_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("om"))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="MEMBER")  # ADMIN | MEMBER
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_active: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(lazy="joined")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("proj"))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String, default="ORG")  # ORG | PUBLIC
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectMember(Base):
    __tablename__ = "project_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("pm"))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="MEMBER")  # LEAD | MEMBER

    user: Mapped[User] = relationship(lazy="joined")


class Pod(Base):
    __tablename__ = "pods"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("pod"))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    purpose_tag: Mapped[str] = mapped_column(String, default="")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PodMember(Base):
    __tablename__ = "pod_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("pdm"))
    pod_id: Mapped[str] = mapped_column(String, ForeignKey("pods.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String, default="MEMBER")  # OWNER | MEMBER

    user: Mapped[User] = relationship(lazy="joined")


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("res"))
    type: Mapped[str] = mapped_column(String)  # SKILL | MCP | NOTE
    title: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    content_md: Mapped[str] = mapped_column(Text, default="")
    server_url: Mapped[str | None] = mapped_column(String, nullable=True)   # MCP
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)    # MCP
    file_url: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str] = mapped_column(String, default="0.1.0")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Typed media attached to any resource: list of
    # {kind: link|image|video|file, url, title?, caption?} (hybrid content model)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    scope_type: Mapped[str] = mapped_column(String, index=True)  # ORG | PROJECT | POD | PUBLIC
    scope_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    author_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    stars_count: Mapped[int] = mapped_column(Integer, default=0)
    installs_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    author: Mapped[User] = relationship(lazy="joined")


class ResourceStar(Base):
    __tablename__ = "resource_stars"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("st"))
    resource_id: Mapped[str] = mapped_column(String, ForeignKey("resources.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("inv"))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="MEMBER")
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("act"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    verb: Mapped[str] = mapped_column(String)  # created|updated|published|starred|joined|invited
    object_type: Mapped[str] = mapped_column(String)  # resource|project|pod|org|member
    object_id: Mapped[str] = mapped_column(String)
    object_title: Mapped[str] = mapped_column(String)
    meta: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped[User] = relationship(lazy="joined")


class OrgFeature(Base):
    """Per-org feature override (BACKEND_SPEC §2.12). Catalog lives in code."""

    __tablename__ = "org_features"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("of"))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("lic"))
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    license_key: Mapped[str] = mapped_column(String)
    plan: Mapped[str] = mapped_column(String, default="PREMIUM")
    activated_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiToken(Base):
    """Personal Access Token (PAT) — long-lived bearer credential for the
    CLI and MCP server (BACKEND_SPEC §10). Format `skst_<random>`; only the
    SHA-256 hash is stored. Sent as `Authorization: Bearer skst_…`."""

    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("pat"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String)  # e.g. "CLI on work laptop"
    token_prefix: Mapped[str] = mapped_column(String)  # first 12 chars, for display
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class RefreshToken(Base):
    """Server-side refresh tokens — rotated on every /auth/refresh (§4.1)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("rt"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
