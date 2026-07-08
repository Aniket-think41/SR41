"""
Super-admin dashboard — the default SQLAdmin CRUD UI mounted at /admin.

This is the internal ops console (distinct from the public dashboard client and
the /api/admin/* JSON endpoints): a browsable, editable view of every table for
platform operators. Only platform admins (User.is_admin) can sign in, using
their normal SkillShare email + password — no separate credential store.

Sign-in page:  <backend origin>/admin
"""

from __future__ import annotations

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from .config import get_settings
from .database import SessionLocal, engine
from .models import (
    Activity,
    ApiToken,
    BlogPost,
    ChangelogEntry,
    ContentPage,
    DeviceAuth,
    Feedback,
    Follow,
    Invitation,
    License,
    Notification,
    OrgFollow,
    OrgMember,
    Organization,
    Payment,
    Pod,
    PodMember,
    PodService,
    Project,
    ProjectMember,
    Resource,
    ResourcePin,
    ResourceStar,
    User,
)
from .security import verify_password

settings = get_settings()


# --------------------------------------------------------------------------- #
# Authentication — session-cookie login gated on User.is_admin
# --------------------------------------------------------------------------- #
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            if user and user.is_admin and verify_password(password, user.password_hash):
                request.session.update({"admin_uid": user.id})
                return True
            return False
        finally:
            db.close()

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        uid = request.session.get("admin_uid")
        if not uid:
            return False
        db = SessionLocal()
        try:
            user = db.get(User, uid)
            return bool(user and user.is_admin)
        finally:
            db.close()


# --------------------------------------------------------------------------- #
# Model views — one per table, grouped in the sidebar by category
# --------------------------------------------------------------------------- #
class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    category = "Accounts"
    icon = "fa-solid fa-user"
    column_list = [User.username, User.email, User.display_name, User.plan, User.is_admin, User.is_publisher, User.verified, User.created_at]
    column_searchable_list = [User.email, User.username, User.display_name]
    column_sortable_list = [User.created_at, User.plan, User.username]
    column_default_sort = ("created_at", True)
    form_excluded_columns = [User.password_hash]
    page_size = 50


class OrganizationAdmin(ModelView, model=Organization):
    name = "Organization"
    name_plural = "Organizations"
    category = "Accounts"
    icon = "fa-solid fa-building"
    column_list = [Organization.name, Organization.slug, Organization.plan, Organization.is_public, Organization.owner_id, Organization.created_at]
    column_searchable_list = [Organization.name, Organization.slug]
    column_sortable_list = [Organization.created_at, Organization.plan]
    column_default_sort = ("created_at", True)


class OrgMemberAdmin(ModelView, model=OrgMember):
    name_plural = "Org Members"
    category = "Accounts"
    column_list = [OrgMember.org_id, OrgMember.user_id, OrgMember.role, OrgMember.joined_at, OrgMember.last_active]


class ProjectAdmin(ModelView, model=Project):
    category = "Structure"
    icon = "fa-solid fa-diagram-project"
    column_list = [Project.name, Project.org_id, Project.visibility, Project.created_by, Project.created_at]
    column_searchable_list = [Project.name]


class ProjectMemberAdmin(ModelView, model=ProjectMember):
    name_plural = "Project Members"
    category = "Structure"
    column_list = [ProjectMember.project_id, ProjectMember.user_id, ProjectMember.role]


class PodAdmin(ModelView, model=Pod):
    category = "Structure"
    icon = "fa-solid fa-cubes"
    column_list = [Pod.name, Pod.project_id, Pod.purpose_tag, Pod.created_by, Pod.created_at]
    column_searchable_list = [Pod.name]


class PodMemberAdmin(ModelView, model=PodMember):
    name_plural = "Pod Members"
    category = "Structure"
    column_list = [PodMember.pod_id, PodMember.user_id, PodMember.role]


class PodServiceAdmin(ModelView, model=PodService):
    name_plural = "Pod Services"
    category = "Structure"
    column_list = [PodService.name, PodService.pod_id, PodService.kind, PodService.status, PodService.endpoint_url]


class ResourceAdmin(ModelView, model=Resource):
    category = "Content"
    icon = "fa-solid fa-cube"
    column_list = [Resource.title, Resource.type, Resource.scope_type, Resource.is_public, Resource.approval_status, Resource.author_id, Resource.stars_count, Resource.created_at]
    column_searchable_list = [Resource.title, Resource.type]
    column_sortable_list = [Resource.created_at, Resource.stars_count, Resource.approval_status]
    column_default_sort = ("created_at", True)
    page_size = 50


class ResourceStarAdmin(ModelView, model=ResourceStar):
    name_plural = "Resource Stars"
    category = "Content"
    column_list = [ResourceStar.resource_id, ResourceStar.user_id, ResourceStar.created_at]


class ResourcePinAdmin(ModelView, model=ResourcePin):
    name_plural = "Resource Pins"
    category = "Content"
    column_list = [ResourcePin.user_id, ResourcePin.resource_id, ResourcePin.position]


class FeedbackAdmin(ModelView, model=Feedback):
    category = "Content"
    icon = "fa-solid fa-comment-dots"
    column_list = [Feedback.rating, Feedback.category, Feedback.target_type, Feedback.status, Feedback.public_status, Feedback.source, Feedback.created_at]
    column_sortable_list = [Feedback.created_at, Feedback.status, Feedback.public_status]
    column_default_sort = ("created_at", True)


class PaymentAdmin(ModelView, model=Payment):
    category = "Billing"
    icon = "fa-solid fa-credit-card"
    column_list = [Payment.user_id, Payment.target_type, Payment.target_id, Payment.plan, Payment.amount, Payment.currency, Payment.status, Payment.created_at]
    column_sortable_list = [Payment.created_at, Payment.status]
    column_default_sort = ("created_at", True)


class LicenseAdmin(ModelView, model=License):
    category = "Billing"
    column_list = [License.org_id, License.plan, License.license_key, License.activated_at, License.expires_at]


class ActivityAdmin(ModelView, model=Activity):
    category = "Activity"
    icon = "fa-solid fa-wave-square"
    column_list = [Activity.verb, Activity.object_type, Activity.object_title, Activity.user_id, Activity.source, Activity.created_at]
    column_sortable_list = [Activity.created_at]
    column_default_sort = ("created_at", True)
    page_size = 50


class NotificationAdmin(ModelView, model=Notification):
    category = "Activity"
    column_list = [Notification.user_id, Notification.verb, Notification.object_title, Notification.read_at, Notification.created_at]
    column_default_sort = ("created_at", True)


class FollowAdmin(ModelView, model=Follow):
    name_plural = "Follows (user→publisher)"
    category = "Activity"
    column_list = [Follow.follower_id, Follow.publisher_id, Follow.created_at]


class OrgFollowAdmin(ModelView, model=OrgFollow):
    name_plural = "Follows (user→org)"
    category = "Activity"
    column_list = [OrgFollow.follower_id, OrgFollow.org_id, OrgFollow.created_at]


class InvitationAdmin(ModelView, model=Invitation):
    category = "Accounts"
    column_list = [Invitation.org_id, Invitation.email, Invitation.role, Invitation.expires_at, Invitation.accepted_at]


class ApiTokenAdmin(ModelView, model=ApiToken):
    name_plural = "API Tokens"
    category = "Accounts"
    column_list = [ApiToken.user_id, ApiToken.name, ApiToken.token_prefix, ApiToken.revoked, ApiToken.last_used_at, ApiToken.created_at]
    form_excluded_columns = [ApiToken.token_hash]


class DeviceAuthAdmin(ModelView, model=DeviceAuth):
    name_plural = "Device Logins"
    category = "Accounts"
    column_list = [DeviceAuth.user_code, DeviceAuth.client_name, DeviceAuth.status, DeviceAuth.user_id, DeviceAuth.created_at, DeviceAuth.expires_at]


class BlogPostAdmin(ModelView, model=BlogPost):
    category = "Marketing"
    icon = "fa-solid fa-newspaper"
    column_list = [BlogPost.title, BlogPost.slug, BlogPost.tag, BlogPost.status, BlogPost.featured, BlogPost.date]
    column_searchable_list = [BlogPost.title, BlogPost.slug]


class ChangelogEntryAdmin(ModelView, model=ChangelogEntry):
    name_plural = "Changelog"
    category = "Marketing"
    column_list = [ChangelogEntry.date, ChangelogEntry.tag, ChangelogEntry.title, ChangelogEntry.status]


class ContentPageAdmin(ModelView, model=ContentPage):
    name_plural = "Content Pages"
    category = "Marketing"
    column_list = [ContentPage.key, ContentPage.title, ContentPage.status, ContentPage.updated_label]


_VIEWS = [
    UserAdmin, OrganizationAdmin, OrgMemberAdmin, InvitationAdmin, ApiTokenAdmin, DeviceAuthAdmin,
    ProjectAdmin, ProjectMemberAdmin, PodAdmin, PodMemberAdmin, PodServiceAdmin,
    ResourceAdmin, ResourceStarAdmin, ResourcePinAdmin, FeedbackAdmin,
    PaymentAdmin, LicenseAdmin,
    ActivityAdmin, NotificationAdmin, FollowAdmin, OrgFollowAdmin,
    BlogPostAdmin, ChangelogEntryAdmin, ContentPageAdmin,
]


def mount_admin(app) -> Admin:
    """Attach the SQLAdmin dashboard to the FastAPI app at /admin."""
    authentication_backend = AdminAuth(secret_key=settings.jwt_secret)
    admin = Admin(
        app,
        engine,
        authentication_backend=authentication_backend,
        title="SkillShare Super Admin",
    )
    for view in _VIEWS:
        admin.add_view(view)
    return admin
