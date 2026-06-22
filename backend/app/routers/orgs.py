"""3.2 Organizations + §3.7 features/licensing + activity + ⌘K search."""

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from .. import storage
from ..config import get_settings
from ..database import get_db
from ..errors import conflict, forbidden, not_found, validation
from ..features import CATALOG, feature_enabled, resolve_features
from ..email import send_invite_email
from ..models import (
    Invitation,
    License,
    Organization,
    OrgFeature,
    OrgFollow,
    OrgMember,
    Pod,
    Project,
    Resource,
    User,
)
from ..permissions import org_by_slug, require_org_admin, require_org_member
from ..schemas import FeaturePatch, InviteIn, LicenseIn, MemberRolePatch, OrgCreate, OrgPatch
from ..security import generate_temp_password, get_current_user, hash_password
from ..serialize import (
    activity_out,
    invitation_out,
    log_activity,
    org_member_out,
    org_out,
    pod_out,
    project_out,
    resource_out,
    user_out,
)
from ..models import Activity

router = APIRouter(prefix="/api/orgs", tags=["orgs"])
settings = get_settings()


def _slugify(s: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


@router.get("")
def my_orgs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memberships = db.query(OrgMember).filter(OrgMember.user_id == user.id).all()
    out = []
    for m in memberships:
        org = db.get(Organization, m.org_id)
        if org:
            out.append(org_out(org, m.role))
    return out


@router.post("")
def create_org(body: OrgCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    slug = _slugify(body.slug or body.name)
    if not body.name.strip() or not slug:
        raise validation("Organization name is required")
    if db.query(Organization.id).filter(Organization.slug == slug).first():
        raise conflict(f'Slug "{slug}" is taken')
    org = Organization(name=body.name.strip(), slug=slug, description=body.description, owner_id=user.id)
    db.add(org)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, role="ADMIN", last_active=datetime.now(timezone.utc)))
    db.commit()
    return org_out(org)


def _org_follow_state(db: Session, org: Organization, user: User) -> dict:
    return {
        "followers_count": db.query(OrgFollow).filter(OrgFollow.org_id == org.id).count(),
        "following": bool(
            db.query(OrgFollow.id)
            .filter(OrgFollow.org_id == org.id, OrgFollow.follower_id == user.id)
            .first()
        ),
    }


@router.get("/{slug}")
def get_org(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    m = require_org_member(db, org, user)
    return {**org_out(org, m.role), **_org_follow_state(db, org, user)}


@router.post("/{slug}/follow")
def follow_org(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Follow (watch) an org — get notified when it publishes to the marketplace.
    Distinct from membership; members already get publish notifications."""
    org = org_by_slug(db, slug)
    if not db.query(OrgFollow).filter(OrgFollow.org_id == org.id, OrgFollow.follower_id == user.id).first():
        db.add(OrgFollow(follower_id=user.id, org_id=org.id))
        db.commit()
    return {"following": True, "followers_count": db.query(OrgFollow).filter(OrgFollow.org_id == org.id).count()}


@router.delete("/{slug}/follow")
def unfollow_org(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    db.query(OrgFollow).filter(OrgFollow.org_id == org.id, OrgFollow.follower_id == user.id).delete()
    db.commit()
    return {"following": False, "followers_count": db.query(OrgFollow).filter(OrgFollow.org_id == org.id).count()}


@router.patch("/{slug}")
def update_org(slug: str, body: OrgPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    if body.terminology is not None and not feature_enabled(db, org, "custom-terminology"):
        raise forbidden("Custom terminology is a premium feature — activate a license to rename Projects and Pods")
    if body.name is not None:
        org.name = body.name
    if body.description is not None:
        org.description = body.description
    if body.logo_url is not None:
        org.logo_url = body.logo_url
    if body.terminology is not None:
        org.terminology = body.terminology.model_dump()
    db.commit()
    return org_out(org)


@router.post("/{slug}/logo")
async def upload_logo(
    slug: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an organization logo (admins only). Stored via the configured
    backend — local disk by default, S3/R2 when configured — and saved to the
    org's logo_url. Returns the updated org."""
    org = org_by_slug(db, slug)
    m = require_org_admin(db, org, user)
    if not storage.ext_allowed("image", file.filename or ""):
        allowed = ", ".join(sorted(storage.ALLOWED_EXT["image"]))
        raise validation(f"Logo must be an image ({allowed})")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise validation(f"Image exceeds the {settings.max_upload_mb} MB limit")
    if not data:
        raise validation("Empty file")
    org.logo_url = storage.save_bytes(
        data, kind="image", username=f"org-{org.slug}",
        filename=file.filename or "logo.png", content_type=file.content_type,
    )
    db.commit()
    return org_out(org, m.role)


# ---- members & invitations ----

@router.get("/{slug}/members")
def members(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    return [org_member_out(m) for m in db.query(OrgMember).filter(OrgMember.org_id == org.id).all()]


def _unique_username(db: Session, base: str) -> str:
    candidate = re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", base.lower())) or "user"
    username = candidate
    n = 1
    while db.query(User.id).filter(User.username == username).first():
        n += 1
        username = f"{candidate}-{n}"
    return username


@router.post("/{slug}/invite")
def invite(slug: str, body: InviteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    email = body.email.lower()
    inv = Invitation(
        org_id=org.id,
        email=email,
        role=body.role if body.role in ("ADMIN", "MEMBER") else "MEMBER",
        token=secrets.token_urlsafe(24),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(inv)
    db.flush()  # assign inv.id before logging

    # If the invitee has no account yet, provision one with a temporary password
    # so the email can carry sign-in details. They're forced to change it on
    # first login (must_change_password). Existing users just get the accept link.
    temp_password: str | None = None
    if not db.query(User.id).filter(User.email == email).first():
        temp_password = generate_temp_password()
        new_user = User(
            email=email,
            password_hash=hash_password(temp_password),
            username=_unique_username(db, email.split("@")[0]),
            display_name=email.split("@")[0],
            must_change_password=True,
        )
        db.add(new_user)
        db.flush()

    # Best-effort email via SES. Never block the response on email delivery.
    send_invite_email(
        to_email=inv.email,
        org_name=org.name,
        org_slug=org.slug,
        inviter_name=user.display_name,
        role=inv.role,
        invite_token=inv.token,
        username=email if temp_password else None,
        temp_password=temp_password,
    )
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="invited",
        object_type="member", object_id=inv.id, object_title=inv.email,
    )
    db.commit()
    return invitation_out(inv)


@router.get("/{slug}/invitations")
def invitations(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    rows = db.query(Invitation).filter(Invitation.org_id == org.id, Invitation.accepted_at.is_(None)).all()
    return [invitation_out(i) for i in rows]


@router.delete("/{slug}/invitations/{inv_id}")
def cancel_invitation(slug: str, inv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    db.query(Invitation).filter(Invitation.id == inv_id, Invitation.org_id == org.id).delete()
    db.commit()
    return {"ok": True}


@router.post("/{slug}/join/{token}")
def join(slug: str, token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    inv = (
        db.query(Invitation)
        .filter(Invitation.org_id == org.id, Invitation.token == token, Invitation.accepted_at.is_(None))
        .first()
    )
    if not inv or inv.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise not_found("Invitation")
    inv.accepted_at = datetime.now(timezone.utc)
    if not db.query(OrgMember.id).filter(OrgMember.org_id == org.id, OrgMember.user_id == user.id).first():
        db.add(OrgMember(org_id=org.id, user_id=user.id, role=inv.role, last_active=datetime.now(timezone.utc)))
        log_activity(
            db, user_id=user.id, org_id=org.id, verb="joined",
            object_type="org", object_id=org.id, object_title=org.name,
        )
    db.commit()
    return {"ok": True, "must_change_password": user.must_change_password}


@router.delete("/{slug}/members/{user_id}")
def remove_member(slug: str, user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    if user_id == org.owner_id:
        raise forbidden("The org owner cannot be removed")
    db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.user_id == user_id).delete()
    db.commit()
    return {"ok": True}


@router.patch("/{slug}/members/{user_id}")
def set_member_role(
    slug: str, user_id: str, body: MemberRolePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org = org_by_slug(db, slug)
    require_org_admin(db, org, user)
    m = db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.user_id == user_id).first()
    if not m:
        raise not_found("Member")
    if body.role not in ("ADMIN", "MEMBER"):
        raise validation("role must be ADMIN or MEMBER")
    m.role = body.role
    db.commit()
    return org_member_out(m)


# ---- published resources (org public page) ----

@router.get("/{slug}/published")
def published(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resources this org has published to the public marketplace — its whole
    library (org / project / pod scopes) filtered to is_public. Backs the
    org page reachable from a member's profile. Members only."""
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    project_ids = [p.id for p in db.query(Project).filter(Project.org_id == org.id).all()]
    pod_ids = [p.id for p in db.query(Pod).filter(Pod.project_id.in_(project_ids or [""])).all()]
    rows = (
        db.query(Resource)
        .filter(
            Resource.is_public.is_(True),
            ((Resource.scope_type == "ORG") & (Resource.scope_id == org.id))
            | ((Resource.scope_type == "PROJECT") & Resource.scope_id.in_(project_ids or [""]))
            | ((Resource.scope_type == "POD") & Resource.scope_id.in_(pod_ids or [""])),
        )
        .all()
    )
    rows.sort(key=lambda r: r.stars_count, reverse=True)
    return [resource_out(db, r, user) for r in rows]


# ---- activity & search ----

@router.get("/{slug}/activity")
def activity(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    rows = (
        db.query(Activity)
        .filter(Activity.org_id == org.id)
        .order_by(Activity.created_at.desc())
        .limit(20)
        .all()
    )
    return [activity_out(a) for a in rows]


@router.get("/{slug}/search")
def search(slug: str, q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    needle = q.lower().strip()

    projects = db.query(Project).filter(Project.org_id == org.id).all()
    project_ids = [p.id for p in projects]
    pods = db.query(Pod).filter(Pod.project_id.in_(project_ids)).all() if project_ids else []
    pod_ids = [p.id for p in pods]
    resources = (
        db.query(Resource)
        .filter(
            ((Resource.scope_type == "ORG") & (Resource.scope_id == org.id))
            | ((Resource.scope_type == "PROJECT") & Resource.scope_id.in_(project_ids or [""]))
            | ((Resource.scope_type == "POD") & Resource.scope_id.in_(pod_ids or [""]))
        )
        .all()
    )
    member_users = [m.user for m in db.query(OrgMember).filter(OrgMember.org_id == org.id).all() if m.user]

    def match(s: str) -> bool:
        return needle in s.lower()

    if not needle:
        return {
            "resources": [resource_out(db, r, user) for r in resources[:5]],
            "projects": [project_out(db, p) for p in projects[:3]],
            "pods": [pod_out(db, p) for p in pods[:3]],
            "members": [],
        }
    return {
        "resources": [
            resource_out(db, r, user)
            for r in resources
            if match(r.title) or any(match(t) for t in (r.tags or []))
        ][:6],
        "projects": [project_out(db, p) for p in projects if match(p.name)][:4],
        "pods": [pod_out(db, p) for p in pods if match(p.name)][:4],
        "members": [user_out(u) for u in member_users if match(u.display_name) or match(u.username)][:4],
    }


# ---- feature flags & licensing (§3.7) ----

@router.get("/{slug}/features")
def features(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    return resolve_features(db, org)


@router.patch("/{slug}/features/{key}")
def set_feature(
    slug: str, key: str, body: FeaturePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org = org_by_slug(db, slug)
    m = require_org_member(db, org, user)
    if m.role != "ADMIN":
        raise forbidden("Only org admins can change features")
    flag = next((f for f in CATALOG if f["key"] == key), None)
    if not flag:
        raise not_found(f'Feature "{key}"')
    if flag["premium"] and org.plan != "PREMIUM":
        raise forbidden(f'"{flag["name"]}" is a premium feature — activate a license first')
    existing = db.query(OrgFeature).filter(OrgFeature.org_id == org.id, OrgFeature.key == key).first()
    if existing:
        existing.enabled = body.enabled
    else:
        db.add(OrgFeature(org_id=org.id, key=key, enabled=body.enabled))
    db.commit()
    return next(f for f in resolve_features(db, org) if f["key"] == key)


@router.post("/{slug}/license")
def activate_license(slug: str, body: LicenseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    m = require_org_member(db, org, user)
    if m.role != "ADMIN":
        raise forbidden("Only org admins can activate a license")
    key = body.license_key.strip().upper()
    if not re.match(settings.license_key_pattern, key):
        raise validation("Invalid license key (format: T41-PREM-XXXX)")
    org.plan = "PREMIUM"
    db.add(License(org_id=org.id, license_key=key, plan="PREMIUM", activated_by=user.id))
    db.commit()
    return {"plan": org.plan, "features": resolve_features(db, org)}
