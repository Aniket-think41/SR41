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


class VerifyEmailIn(BaseModel):
    """Second step of signup: the emailed one-time code + the email it went to."""
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class ResendOtpIn(BaseModel):
    email: EmailStr


class PasswordResetVerifyIn(BaseModel):
    """In-dashboard reset: the emailed code + the new password to set."""
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    # current_password is optional: not required when the account is flagged
    # must_change_password (first sign-in for an invited user), required otherwise.
    current_password: str | None = None
    new_password: str = Field(min_length=8)


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
    is_public: bool | None = None  # opt in to a public org profile page (spec §6)


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
    """Add a member by user_id OR email. When the user already exists anywhere
    on the platform we resolve them and (cascading) ensure membership at every
    level up to this one; at least one of user_id/email is required."""

    user_id: str | None = None
    email: EmailStr | None = None
    role: str = "MEMBER"


PodServiceKind = Literal["MCP_SERVER", "DEPLOYED_API", "WEBHOOK", "DATABASE", "OTHER"]
PodServiceStatus = Literal["active", "paused", "error"]


class PodServiceCreate(BaseModel):
    """Register a service in a pod's service registry. `secret_ref` is the NAME
    of a secret (env var / secret-manager key), never the secret value."""

    name: str = Field(min_length=1, max_length=120)
    kind: PodServiceKind = "OTHER"
    description: str = ""
    endpoint_url: str | None = Field(default=None, max_length=2000)
    health_url: str | None = Field(default=None, max_length=2000)
    config: dict = {}
    secret_ref: str = Field(default="", max_length=200)
    status: PodServiceStatus = "active"


class PodServicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: PodServiceKind | None = None
    description: str | None = None
    endpoint_url: str | None = Field(default=None, max_length=2000)
    health_url: str | None = Field(default=None, max_length=2000)
    config: dict | None = None
    secret_ref: str | None = Field(default=None, max_length=200)
    status: PodServiceStatus | None = None


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
    # Audience (who can read): POD | PROJECT | ORG. Omit → defaults to the home
    # scope (pod resources are pod-only by default). Validated against scope_type.
    visibility: str | None = None
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
    visibility: str | None = None  # POD | PROJECT | ORG (validated against scope_type)


class ResourceMove(BaseModel):
    """Move a resource to a new home scope (pod⇆project⇆org). visibility is
    re-defaulted to the new scope unless explicitly provided."""

    scope_type: str  # ORG | PROJECT | POD
    scope_id: str | None = None
    visibility: str | None = None


class UploadIn(BaseModel):
    filename: str
    content_type: str = "application/zip"
    size_bytes: int | None = None


class ImportIn(BaseModel):
    org_slug: str


class ResourceReviewIn(BaseModel):
    """Approve or reject a resource submitted for public listing (spec §3)."""

    decision: str  # "approve" | "reject"
    note: str | None = None


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


# ---- Integrations (org Integrations section) ----


class IntegrationConnectIn(BaseModel):
    """Connect a provider by supplying credentials. For GitHub (auth_type=pat)
    this is a fine-grained/classic Personal Access Token; ``account`` optionally
    pins the org/user login the connection is scoped to. The token is validated
    against the provider, then encrypted at rest — it is never returned."""

    token: str = Field(min_length=10, max_length=500)
    account: str | None = Field(default=None, max_length=120)
    auth_method: str = Field(default="classic_pat", max_length=40)


class IntegrationConfigPatch(BaseModel):
    """Update the non-secret settings of a connection (e.g. default sync mode,
    selected repositories). Never carries credentials."""

    config: dict


class GithubPublishIn(BaseModel):
    """Publish a resource to GitHub (SkillShare → GitHub). Omit ``repo_full_name``
    to create a managed repo whose visibility mirrors the resource (public
    resource → public repo); give it to publish into an existing repo."""

    resource_id: str = Field(min_length=1, max_length=64)
    repo_full_name: str | None = Field(default=None, max_length=200)  # owner/repo
    path: str = Field(default="", max_length=200)


class GithubLinkIn(BaseModel):
    """Attach an existing repo to a resource without pushing (link only)."""

    resource_id: str = Field(min_length=1, max_length=64)
    repo_full_name: str = Field(min_length=3, max_length=200)
    path: str = Field(default="", max_length=200)


class GithubResourceRefIn(BaseModel):
    """Reference a resource for a push/pull sync action."""

    resource_id: str = Field(min_length=1, max_length=64)


class ScopeRepoLinkIn(BaseModel):
    """Attach a GitHub repo to a scope (org/team/pod). Provide an EXISTING repo
    via ``repo_full_name`` (chosen from the dropdown), OR create a new one via
    ``create_repo_name`` (+ ``create_private``). A scope may have many repos."""

    scope_type: str  # ORG | PROJECT | POD
    scope_id: str = Field(min_length=1, max_length=64)
    repo_full_name: str | None = Field(default=None, max_length=200)   # existing repo
    create_repo_name: str | None = Field(default=None, max_length=100)  # create a new repo instead
    create_private: bool = True                                        # visibility of the created repo
    visibility: Literal["all", "public", "private"] = "all"            # which resources route here
    sync_direction: Literal["off", "pull", "push", "both"] = "push"
    path_prefix: str = Field(default="", max_length=200)


class GithubBulkImportIn(BaseModel):
    """Import detected resources from several repos into a scope at once."""

    repos: list[str] = Field(default_factory=list, max_length=100)  # owner/repo names
    scope_type: str = "ORG"  # ORG | PROJECT | POD
    scope_id: str | None = None


class GithubPublishScopeIn(BaseModel):
    """Publish every resource in a scope to GitHub (bulk). Each resource gets its
    own managed repo whose visibility mirrors it."""

    scope_type: str = "ORG"  # ORG | PROJECT | POD
    scope_id: str | None = None


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


class PublicFeedbackIn(BaseModel):
    """Anonymous feedback from the marketing website (spec §4). Enters the
    moderation queue (public_status=pending) until an admin approves it."""

    message: str = Field(min_length=1, max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    category: FeedbackCategory = "general"
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    target_type: Literal["platform", "resource"] = "platform"
    target_id: str | None = None


class FeedbackModerateIn(BaseModel):
    """Admin decision on whether a feedback item shows publicly (spec §4)."""

    decision: Literal["approve", "reject"]


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


class SetPlanIn(BaseModel):
    """Admin plan grant (spec §2): FREE | PRO | ENTERPRISE (legacy PREMIUM accepted)."""

    plan: str


class BillingCheckoutIn(BaseModel):
    """Start a Razorpay checkout to upgrade a user or org to a paid plan (spec §5)."""

    plan: str  # PRO | ENTERPRISE
    target_type: Literal["user", "org"] = "user"
    org_slug: str | None = None


class AdminRowPatch(BaseModel):
    """Admin table-browser inline edit: a map of column → new value. Values are
    coerced to each column's type server-side; the primary key is never changed."""

    updates: dict
