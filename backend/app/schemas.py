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


class NotificationReadIn(BaseModel):
    """Mark notifications read: pass explicit ids, or all=true to clear the inbox."""

    ids: list[str] = []
    all: bool = False
