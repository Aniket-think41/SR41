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
    # Platform admin (not org admin): may manage marketing content — blog posts,
    # changelog, legal pages — and verify publishers. Set in seed; never exposed
    # on the public user payload.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set when an account is auto-provisioned by an org invitation with a
    # temporary password emailed to the user. The frontend forces a password
    # change on first sign-in; cleared by POST /api/auth/change-password.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
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


class PodService(Base):
    """A service a pod operates or depends on — an MCP server, a deployed API,
    a webhook, a database, etc. This is the pod's service-management registry:
    a place to record what's running, where it lives, and how it's wired, so a
    pod's operational surface is discoverable alongside its skills/MCPs/notes.

    Secrets are NEVER stored inline — `secret_ref` holds the *name* of an env
    var / secret-manager key the deploy resolves at runtime, not the value.
    Managing a pod's services requires pod write access; any org member can view
    them (read transparency, §4.2)."""

    __tablename__ = "pod_services"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("svc"))
    pod_id: Mapped[str] = mapped_column(String, ForeignKey("pods.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    # MCP_SERVER | DEPLOYED_API | WEBHOOK | DATABASE | OTHER
    kind: Mapped[str] = mapped_column(String, default="OTHER", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    health_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Free-form wiring (region, transport, headers map, etc.) — no secret values.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Reference (NOT value) to a secret: env var name / secret-manager key.
    secret_ref: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="active")  # active | paused | error
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


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
    # Set when a resource was pushed from a local artifact (F2). Lets us detect
    # "this already exists on the platform" across machines → link, not duplicate.
    source_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
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


class ResourcePin(Base):
    """A resource a user has pinned to the top of their profile (GitHub-style).
    Ordered by `position`; capped in the router (resources §). Distinct from a
    star: a star is endorsement, a pin is curation of your own profile."""

    __tablename__ = "resource_pins"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("pin"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    resource_id: Mapped[str] = mapped_column(String, ForeignKey("resources.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
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


class Follow(Base):
    """A user following a publisher. When the publisher ships something to the
    marketplace, each follower gets a notification (see resources.publish)."""

    __tablename__ = "follows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("fol"))
    follower_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    publisher_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrgFollow(Base):
    """A user following an organization (a "watch"). Non-member followers get a
    notification when the org publishes to the marketplace; members already get
    the membership notification, so they're excluded from the follower fan-out."""

    __tablename__ = "org_follows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("ofl"))
    follower_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    org_id: Mapped[str] = mapped_column(String, ForeignKey("organizations.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    """Per-recipient notification, fanned out from an Activity to the members of
    the scope it happened in (F1), or to a publisher's followers on a marketplace
    publish. One row per recipient; `read_at` tracks unread state. The actor is
    never a recipient of their own action."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("ntf"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)  # recipient
    actor_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    # Nullable: follower notifications about a PUBLIC-scoped resource have no org.
    org_id: Mapped[str | None] = mapped_column(String, ForeignKey("organizations.id"), index=True, nullable=True)
    scope_type: Mapped[str] = mapped_column(String)  # ORG | PROJECT | POD | PUBLIC
    scope_id: Mapped[str | None] = mapped_column(String, nullable=True)
    verb: Mapped[str] = mapped_column(String)  # created | published
    object_type: Mapped[str] = mapped_column(String)  # resource | …
    object_id: Mapped[str] = mapped_column(String)
    object_title: Mapped[str] = mapped_column(String)
    meta: Mapped[str | None] = mapped_column(String, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    actor: Mapped[User] = relationship(lazy="joined", foreign_keys=[actor_id])


class LocalArtifactState(Base):
    """Per-user provenance/dismissal memory for local artifacts (F2). Keyed by a
    content fingerprint so a changed file re-surfaces while an identical one stays
    silent. Synced server-side so a 'pushed'/'dismissed' decision carries across
    machines. status: pushed (we created resource_id) | dismissed (user said no)."""

    __tablename__ = "local_artifact_states"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("las"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # skill | mcp | note
    source: Mapped[str] = mapped_column(String, default="")  # claude-code | cursor | codex | …
    status: Mapped[str] = mapped_column(String)  # pushed | dismissed
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Feedback(Base):
    """User-submitted product feedback — a star rating + free-text message, with
    an optional category, collected from wherever the user is working: the
    dashboard, the CLI, or the MCP server (`source`). Feedback can be about the
    platform in general (`target_type="platform"`) or a specific resource
    (`target_type="resource"`, `target_id=<resource id>`). `context` carries
    free-form client hints (page, app version). Admins triage via
    /api/admin/feedback, flipping `status` open → reviewed."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("fb"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String, default="platform", index=True)  # platform | resource
    target_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # resource id when resource-scoped
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5, optional
    category: Mapped[str] = mapped_column(String, default="general")  # bug | idea | praise | question | other | general
    message: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String, default="dashboard")  # dashboard | cli | mcp
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {page, app_version, …}
    status: Mapped[str] = mapped_column(String, default="open", index=True)  # open | reviewed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

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


class DeviceAuth(Base):
    """OAuth device-authorization session — backs the browser login flow for the
    CLI and MCP server (`skillshare login` / the MCP login tool). The client polls
    /api/auth/device/token with the secret device_code; the user approves the short
    user_code on the dashboard's /activate page. On approval the client is handed a
    fresh access + refresh token pair (exactly once)."""

    __tablename__ = "device_auths"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("dev"))
    device_code: Mapped[str] = mapped_column(String, unique=True, index=True)  # secret, client-held
    user_code: Mapped[str] = mapped_column(String, unique=True, index=True)    # short, human-entered
    client_name: Mapped[str] = mapped_column(String, default="")               # e.g. "SkillShare CLI on host"
    status: Mapped[str] = mapped_column(String, default="pending", index=True)  # pending | approved | denied
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    interval: Mapped[int] = mapped_column(Integer, default=5)                   # client poll interval (s)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)             # token issued already?
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Marketing content — blog, changelog, legal pages. Authored/managed by a
# platform admin (User.is_admin) and read by the public marketing site
# (/api/public/*). Blog posts carry a draft|published status so old posts can
# be hidden and new ones staged before going live.
# ---------------------------------------------------------------------------


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("blog"))
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    # YYYY-MM-DD display/sort date (matches the marketing site's BlogPost.date).
    date: Mapped[str] = mapped_column(String, index=True)
    tag: Mapped[str] = mapped_column(String, default="Story")  # Release | Feature | Guide | Story
    excerpt: Mapped[str] = mapped_column(Text, default="")
    standfirst: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ordered content blocks: [{type: p|h2|ul|quote, text?|items?}]
    body: Mapped[list] = mapped_column(JSON, default=list)
    author_name: Mapped[str] = mapped_column(String, default="")
    author_role: Mapped[str] = mapped_column(String, default="")
    reading_minutes: Mapped[int] = mapped_column(Integer, default=3)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="draft", index=True)  # draft | published
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("chg"))
    date: Mapped[str] = mapped_column(String, index=True)  # YYYY-MM-DD
    tag: Mapped[str] = mapped_column(String, default="Release")
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="published", index=True)  # draft | published
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ContentPage(Base):
    """A static legal/marketing page (privacy, terms) — structured so the site
    renders it through the shared LegalPage layout with no code change."""

    __tablename__ = "content_pages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: make_id("page"))
    key: Mapped[str] = mapped_column(String, unique=True, index=True)  # privacy | terms
    kicker: Mapped[str] = mapped_column(String, default="Legal")
    title: Mapped[str] = mapped_column(String)
    intro: Mapped[str] = mapped_column(Text, default="")
    # Display string shown as "Last updated …", e.g. "June 15, 2026".
    updated_label: Mapped[str] = mapped_column(String, default="")
    # [{heading, paragraphs?: [...], bullets?: [...]}]
    sections: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="published", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
