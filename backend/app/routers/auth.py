"""3.1 Auth — signup, login, google, refresh, logout, me."""

import re
import secrets
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from .. import storage
from ..config import get_settings
from ..database import get_db
from ..errors import conflict, forbidden, not_found, unauthorized, validation
from ..models import (
    ApiToken,
    DeviceAuth,
    Organization,
    OrgMember,
    Pod,
    PodMember,
    Project,
    ProjectMember,
    Resource,
    User,
    now,
)
from ..schemas import (
    ChangePasswordIn,
    DeviceCodeIn,
    DeviceStartIn,
    DeviceUserCodeIn,
    GoogleIn,
    LoginIn,
    MePatch,
    RefreshIn,
    SignupIn,
)
from ..security import (
    REFRESH_COOKIE,
    create_access_token,
    get_current_user,
    hash_password,
    issue_refresh_token,
    mint_pat,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from ..serialize import resource_out, user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _slugify(s: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", s.lower()))


def _unique_username(db: Session, base: str) -> str:
    candidate = _slugify(base) or "user"
    n = 1
    username = candidate
    while db.query(User.id).filter(User.username == username).first():
        n += 1
        username = f"{candidate}-{n}"
    return username


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        path="/api/auth",
    )


def _me_out(user: User) -> dict:
    """Self payload — like user_out but includes is_admin, which is intentionally
    withheld from the public user serializer."""
    return {
        **user_out(user),
        "is_admin": user.is_admin,
        "must_change_password": user.must_change_password,
    }


def _session_payload(db: Session, response: Response, user: User) -> dict:
    refresh = issue_refresh_token(db, user)
    _set_refresh_cookie(response, refresh)
    return {"user": _me_out(user), "access_token": create_access_token(user), "refresh_token": refresh}


@router.post("/signup")
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User.id).filter(User.email == email).first():
        raise conflict("An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        username=_unique_username(db, body.display_name or email.split("@")[0]),
        display_name=body.display_name,
        # Every first-time account confirms a password of their own on first
        # entry — the dashboard gates on must_change_password until they do.
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    return _session_payload(db, response, user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise unauthorized("Invalid email or password")
    return _session_payload(db, response, user)


@router.post("/google")
async def google(body: GoogleIn, response: Response, db: Session = Depends(get_db)):
    """Google OAuth: the client sends the Google ID token; we verify it
    against Google's tokeninfo endpoint and upsert the user."""
    if not settings.google_client_id:
        raise forbidden("Google sign-in is not configured (set GOOGLE_CLIENT_ID)")
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.id_token})
    if res.status_code != 200:
        raise unauthorized("Invalid Google token")
    info = res.json()
    if info.get("aud") != settings.google_client_id:
        raise unauthorized("Google token issued for a different app")
    email = str(info.get("email", "")).lower()
    if not email or info.get("email_verified") not in ("true", True):
        raise unauthorized("Google account email is not verified")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        name = info.get("name") or email.split("@")[0]
        user = User(
            email=email,
            password_hash="",  # OAuth-only account — no password set yet
            username=_unique_username(db, name),
            display_name=name,
            avatar_url=info.get("picture"),
            # Google accounts have no password of their own; make them set one on
            # first entry so they can also sign in with email/password later.
            must_change_password=True,
        )
        db.add(user)
        db.commit()
    return _session_payload(db, response, user)


@router.post("/refresh")
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    # Browser clients send the rotating token as an HttpOnly cookie; the CLI/MCP
    # have no cookie, so they present it in the request body instead.
    raw = (body.refresh_token if body else None) or request.cookies.get(REFRESH_COOKIE) or ""
    if not raw:
        raise unauthorized("Missing refresh token")
    user, new_refresh = rotate_refresh_token(db, raw)
    _set_refresh_cookie(response, new_refresh)
    return {
        "user": user_out(user),
        "access_token": create_access_token(user),
        "refresh_token": new_refresh,
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_refresh_token(db, request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"ok": True}


# ---- Device-authorization login (CLI / MCP browser flow) ----

DEVICE_TTL_MINUTES = 15
DEVICE_INTERVAL = 5
# user_code alphabet: no 0/O/1/I/L to avoid hand-typing ambiguity
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_user_code() -> str:
    chunk = lambda: "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))  # noqa: E731
    return f"{chunk()}-{chunk()}"


@router.post("/device/start")
def device_start(body: DeviceStartIn, db: Session = Depends(get_db)):
    """Begin a device login. The client polls /device/token with device_code while
    the user approves user_code at verification_uri_complete."""
    # collision-safe user_code (the space is tiny per-code but the table is small)
    for _ in range(5):
        user_code = _gen_user_code()
        if not db.query(DeviceAuth.id).filter(DeviceAuth.user_code == user_code).first():
            break
    rec = DeviceAuth(
        device_code=secrets.token_urlsafe(32),
        user_code=user_code,
        client_name=body.client_name or "SkillShare CLI",
        interval=DEVICE_INTERVAL,
        expires_at=now() + timedelta(minutes=DEVICE_TTL_MINUTES),
    )
    db.add(rec)
    db.commit()
    base = settings.frontend_url.rstrip("/")
    return {
        "device_code": rec.device_code,
        "user_code": rec.user_code,
        "verification_uri": f"{base}/activate",
        "verification_uri_complete": f"{base}/activate?code={rec.user_code}",
        "expires_in": DEVICE_TTL_MINUTES * 60,
        "interval": rec.interval,
    }


def _device_expired(rec: DeviceAuth) -> bool:
    return rec.expires_at.replace(tzinfo=now().tzinfo) < now()


@router.post("/device/token")
def device_token(body: DeviceCodeIn, response: Response, db: Session = Depends(get_db)):
    """Poll for the result of a device login. Returns {status} until approved; on
    approval returns the access + refresh token pair exactly once."""
    rec = db.query(DeviceAuth).filter(DeviceAuth.device_code == body.device_code).first()
    if not rec:
        raise not_found("Device session")
    if rec.status == "denied":
        return {"status": "denied"}
    if rec.consumed or _device_expired(rec):
        return {"status": "expired"}
    if rec.status != "approved" or not rec.user_id:
        return {"status": "pending", "interval": rec.interval}
    user = db.get(User, rec.user_id)
    if not user:
        return {"status": "expired"}
    rec.consumed = True
    refresh = issue_refresh_token(db, user)  # commits
    _set_refresh_cookie(response, refresh)
    return {
        "status": "approved",
        "access_token": create_access_token(user),
        "refresh_token": refresh,
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": _me_out(user),
    }


def _device_by_user_code(db: Session, user_code: str) -> DeviceAuth:
    rec = db.query(DeviceAuth).filter(DeviceAuth.user_code == user_code.strip().upper()).first()
    if not rec:
        raise not_found("Device session")
    return rec


@router.get("/device/{user_code}")
def device_info(user_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the /activate page shows before the user approves: which client is
    asking, and whether the code is still valid."""
    rec = _device_by_user_code(db, user_code)
    return {
        "client_name": rec.client_name,
        "status": "expired" if (_device_expired(rec) and rec.status == "pending") else rec.status,
        "created_at": rec.created_at,
    }


@router.post("/device/approve")
def device_approve(body: DeviceUserCodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _device_by_user_code(db, body.user_code)
    if _device_expired(rec):
        raise validation("This code has expired — start a new login from your terminal")
    if rec.status == "denied" or rec.consumed:
        raise validation("This code is no longer valid")
    rec.status = "approved"
    rec.user_id = user.id
    db.commit()
    return {"ok": True, "client_name": rec.client_name}


@router.post("/device/deny")
def device_deny(body: DeviceUserCodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = _device_by_user_code(db, body.user_code)
    rec.status = "denied"
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _me_out(user)


@router.get("/me/stats")
def my_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Compact context counts for the CLI/MCP status line: how many resources are
    visible to me at each scope I belong to, plus my org's terminology so the
    line can say "Teams" instead of "Pods" where that org renamed them."""
    org_ids = [r[0] for r in db.query(OrgMember.org_id).filter(OrgMember.user_id == user.id).all()]
    project_ids = [r[0] for r in db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id).all()]
    pod_ids = [r[0] for r in db.query(PodMember.pod_id).filter(PodMember.user_id == user.id).all()]

    def _count(scope_type: str, ids: list[str]) -> int:
        if not ids:
            return 0
        return db.query(func.count(Resource.id)).filter(
            Resource.scope_type == scope_type, Resource.scope_id.in_(ids)).scalar() or 0

    term = {"org": "org", "project": "project", "pod": "pod"}
    if org_ids:
        org = db.get(Organization, org_ids[0])
        if org and org.terminology:
            term["project"] = org.terminology.get("project") or term["project"]
            term["pod"] = org.terminology.get("pod") or term["pod"]
    return {
        "resources": {
            "org": _count("ORG", org_ids),
            "project": _count("PROJECT", project_ids),
            "pod": _count("POD", pod_ids),
        },
        "memberships": {"orgs": len(org_ids), "projects": len(project_ids), "pods": len(pod_ids)},
        "terminology": term,
    }


@router.get("/me/resources")
def my_resources(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every resource visible to me across the scopes I belong to (org/project/
    pod), newest first. The CLI subtracts what's already installed locally to get
    the "available to install" set behind `skillshare available` and the panel."""
    org_ids = [r[0] for r in db.query(OrgMember.org_id).filter(OrgMember.user_id == user.id).all()]
    project_ids = [r[0] for r in db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id).all()]
    pod_ids = [r[0] for r in db.query(PodMember.pod_id).filter(PodMember.user_id == user.id).all()]
    clauses = []
    if org_ids:
        clauses.append(and_(Resource.scope_type == "ORG", Resource.scope_id.in_(org_ids)))
    if project_ids:
        clauses.append(and_(Resource.scope_type == "PROJECT", Resource.scope_id.in_(project_ids)))
    if pod_ids:
        clauses.append(and_(Resource.scope_type == "POD", Resource.scope_id.in_(pod_ids)))
    if not clauses:
        return []
    rows = db.query(Resource).filter(or_(*clauses)).order_by(Resource.updated_at.desc()).all()
    return [resource_out(db, r, user) for r in rows]


@router.patch("/me")
def update_me(body: MePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field in ("display_name", "bio", "location", "website", "is_publisher"):
        value = getattr(body, field)
        if value is not None:
            setattr(user, field, value)
    db.commit()
    return _me_out(user)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Set a new password. Required on first sign-in for invitees whose account
    was auto-provisioned with a temporary password (must_change_password).

    The current password is verified UNLESS the account is still flagged as
    needing a change — in that flow the user only knows the emailed temp password,
    which they already proved by logging in to obtain this access token."""
    if not user.must_change_password:
        if not user.password_hash or not verify_password(body.current_password or "", user.password_hash):
            raise unauthorized("Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    return _me_out(user)


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a profile picture. Stored via the configured backend — local disk
    by default (no AWS needed), S3/R2 when STORAGE_BACKEND=s3 — and the returned
    public URL is saved to the user's avatar_url. Returns the updated self."""
    if not storage.ext_allowed("image", file.filename or ""):
        allowed = ", ".join(sorted(storage.ALLOWED_EXT["image"]))
        raise validation(f"Avatar must be an image ({allowed})")
    data = await file.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise validation(f"Image exceeds the {settings.max_upload_mb} MB limit")
    if not data:
        raise validation("Empty file")
    user.avatar_url = storage.save_bytes(
        data, kind="image", username=user.username,
        filename=file.filename or "avatar.png", content_type=file.content_type,
    )
    db.commit()
    return _me_out(user)


@router.post("/become-publisher")
def become_publisher(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Opt in to publishing. Flips on the publisher flag so the user can push
    resources to the public marketplace. The Think41-verified badge is granted
    separately by a platform admin (POST /api/admin/publishers/{username}/verify)."""
    user.is_publisher = True
    db.commit()
    return _me_out(user)


# ---- Personal Access Tokens (CLI / MCP — BACKEND_SPEC §10) ----

class TokenCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)  # e.g. "CLI on work laptop"
    expires_days: int | None = Field(default=None, ge=1, le=365)


def _token_out(t: ApiToken) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "token_prefix": t.token_prefix,
        "created_at": t.created_at,
        "last_used_at": t.last_used_at,
        "expires_at": t.expires_at,
        "revoked": t.revoked,
    }


@router.post("/tokens")
def create_token(body: TokenCreateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mint a PAT. The full token is returned ONCE — store it client-side."""
    rec, raw = mint_pat(db, user, body.name, body.expires_days)
    return {**_token_out(rec), "token": raw}


@router.get("/tokens")
def list_tokens(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user.id, ApiToken.revoked.is_(False))
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return [_token_out(t) for t in rows]


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.user_id == user.id).first()
    if not rec:
        raise not_found("Token")
    rec.revoked = True
    db.commit()
    return {"ok": True}
