"""Request bodies — names match what the client sends (lib/api/index.ts)."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class Attachment(BaseModel):
    """A typed media item attached to a resource (hybrid content model).
    content_md stays the canonical prose; attachments add structured media."""

    kind: Literal["link", "image", "video", "file"]
    url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, max_length=500)


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleIn(BaseModel):
    id_token: str


class MePatch(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    location: str | None = None
    website: str | None = None
    is_publisher: bool | None = None


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    slug: str | None = None
    description: str = ""


class Terminology(BaseModel):
    project: str = Field(min_length=1, max_length=24)
    pod: str = Field(min_length=1, max_length=24)


class OrgPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    logo_url: str | None = None
    terminology: Terminology | None = None


class InviteIn(BaseModel):
    email: EmailStr
    role: str = "MEMBER"  # ADMIN | MEMBER


class MemberRolePatch(BaseModel):
    role: str  # ADMIN | MEMBER


class FeaturePatch(BaseModel):
    enabled: bool


class LicenseIn(BaseModel):
    license_key: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    tags: list[str] = []


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    visibility: str | None = None


class PodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    purpose_tag: str = ""


class PodPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    purpose_tag: str | None = None


class AddMemberIn(BaseModel):
    user_id: str
    role: str = "MEMBER"


class ResourceCreate(BaseModel):
    type: str  # SKILL | MCP | NOTE
    title: str = Field(min_length=1, max_length=120)
    description: str = ""
    content_md: str = ""
    server_url: str | None = None
    config_json: str | None = None
    file_url: str | None = None
    version: str = "0.1.0"
    tags: list[str] = []
    attachments: list[Attachment] = []
    scope_type: str  # ORG | PROJECT | POD | PUBLIC
    scope_id: str | None = None
    source_fingerprint: str | None = None  # set when pushed from a local artifact (F2)


class ResourcePatch(BaseModel):
    title: str | None = None
    description: str | None = None
    content_md: str | None = None
    server_url: str | None = None
    config_json: str | None = None
    file_url: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    attachments: list[Attachment] | None = None
    scope_type: str | None = None
    scope_id: str | None = None


class UploadIn(BaseModel):
    filename: str
    content_type: str = "application/zip"
    size_bytes: int | None = None


class ImportIn(BaseModel):
    org_slug: str


class GithubPreviewIn(BaseModel):
    """Detect (without creating) the skill(s)/MCP(s)/note(s) inside a public repo."""

    url: str = Field(min_length=1, max_length=400)


class GithubImportIn(BaseModel):
    """Import detected resources from a GitHub URL into a scope.
    `select` is a list of fingerprints to import; empty = import everything found."""

    url: str = Field(min_length=1, max_length=400)
    scope_type: str  # ORG | PROJECT | POD | PUBLIC
    scope_id: str | None = None
    select: list[str] = []


# ---- Device-authorization login (CLI / MCP browser login) ----


class DeviceStartIn(BaseModel):
    client_name: str = Field(default="", max_length=120)


class DeviceCodeIn(BaseModel):
    device_code: str = Field(min_length=8, max_length=128)


class DeviceUserCodeIn(BaseModel):
    user_code: str = Field(min_length=4, max_length=20)


class RefreshIn(BaseModel):
    """Refresh token presented by a non-browser client (CLI/MCP have no cookie)."""

    refresh_token: str | None = None


class NotificationReadIn(BaseModel):
    """Mark notifications read: pass explicit ids, or all=true to clear the inbox."""

    ids: list[str] = []
    all: bool = False


class LocalStateIn(BaseModel):
    """Upsert provenance/dismissal for a local artifact (F2), keyed by fingerprint."""

    fingerprint: str = Field(min_length=4, max_length=128)
    kind: Literal["skill", "mcp", "note"]
    status: Literal["pushed", "dismissed"]
    source: str = ""
    resource_id: str | None = None
    name: str = ""


# ---- Feedback ----

FeedbackCategory = Literal["bug", "idea", "praise", "question", "other", "general"]


class FeedbackIn(BaseModel):
    """Submit product feedback. `message` is required; everything else is
    optional so a quick "👍 5 stars" or a detailed bug report both work.
    `target_type="resource"` + `target_id` attaches it to a specific resource."""

    message: str = Field(min_length=1, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    category: FeedbackCategory = "general"
    target_type: Literal["platform", "resource"] = "platform"
    target_id: str | None = None
    source: Literal["dashboard", "cli", "mcp"] = "dashboard"
    context: dict | None = None


class FeedbackStatusIn(BaseModel):
    """Admin triage: flip an item open ⇄ reviewed."""

    status: Literal["open", "reviewed"] = "reviewed"


# ---- Marketing content (admin-managed) ----

BlogTag = Literal["Release", "Feature", "Guide", "Story"]
ContentStatus = Literal["draft", "published"]


class BlogBlock(BaseModel):
    """One content block in a post body. `text` for p/h2/quote, `items` for ul."""

    type: Literal["p", "h2", "ul", "quote"]
    text: str | None = None
    items: list[str] | None = None


class BlogPostCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    date: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD
    tag: BlogTag = "Story"
    excerpt: str = ""
    standfirst: str | None = None
    body: list[BlogBlock] = []
    author_name: str = ""
    author_role: str = ""
    reading_minutes: int = Field(default=3, ge=1, le=60)
    featured: bool = False
    status: ContentStatus = "draft"


class BlogPostPatch(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    date: str | None = Field(default=None, min_length=10, max_length=10)
    tag: BlogTag | None = None
    excerpt: str | None = None
    standfirst: str | None = None
    body: list[BlogBlock] | None = None
    author_name: str | None = None
    author_role: str | None = None
    reading_minutes: int | None = Field(default=None, ge=1, le=60)
    featured: bool | None = None
    status: ContentStatus | None = None


class ChangelogCreate(BaseModel):
    date: str = Field(min_length=10, max_length=10)
    tag: BlogTag = "Release"
    title: str = Field(min_length=1, max_length=160)
    body: str = ""
    status: ContentStatus = "published"


class ChangelogPatch(BaseModel):
    date: str | None = Field(default=None, min_length=10, max_length=10)
    tag: BlogTag | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    body: str | None = None
    status: ContentStatus | None = None


class PageSection(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    paragraphs: list[str] | None = None
    bullets: list[str] | None = None


class ContentPagePatch(BaseModel):
    kicker: str | None = None
    title: str | None = None
    intro: str | None = None
    updated_label: str | None = None
    sections: list[PageSection] | None = None
    status: ContentStatus | None = None


class VerifyPublisherIn(BaseModel):
    verified: bool = True
