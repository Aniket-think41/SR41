"""3.1 Auth — signup, login, google, refresh, logout, me."""

import hashlib
import logging
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
    EmailVerification,
    Organization,
    OrgMember,
    PasswordResetOtp,
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
    PasswordResetVerifyIn,
    RefreshIn,
    ResendOtpIn,
    SignupIn,
    VerifyEmailIn,
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
from ..serialize import resource_out, resources_out, user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()
log = logging.getLogger("app.auth")


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
        "plan": user.plan or "FREE",
    }


def _session_payload(db: Session, response: Response, user: User) -> dict:
    refresh = issue_refresh_token(db, user)
    _set_refresh_cookie(response, refresh)
    return {"user": _me_out(user), "access_token": create_access_token(user), "refresh_token": refresh}


_OTP_ALPHABET = "0123456789"


def _gen_otp() -> str:
    return "".join(secrets.choice(_OTP_ALPHABET) for _ in range(max(4, settings.otp_length)))


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def _start_verification(db: Session, *, email: str, password: str, display_name: str) -> dict:
    """Create/replace the pending signup for `email`, email the OTP, and return the
    client payload. When email can't be sent (SES off) the code is surfaced in the
    response so signup still works — controlled by settings.otp_dev_return."""
    code = _gen_otp()
    # Replace any prior pending record for this email (re-signup / resend).
    db.query(EmailVerification).filter(EmailVerification.email == email).delete()
    rec = EmailVerification(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        code_hash=_hash_code(code),
        expires_at=now() + timedelta(minutes=settings.otp_ttl_minutes),
    )
    db.add(rec)
    db.commit()

    from ..email import send_otp_email

    sent = send_otp_email(
        to_email=email, code=code, display_name=display_name, ttl_minutes=settings.otp_ttl_minutes
    )
    if not sent:
        # No email delivery configured — log the code so it's recoverable in dev.
        log.info("Signup OTP for %s: %s (email delivery off)", email, code)
    out = {
        "pending": True,
        "email": email,
        "email_sent": sent,
        "expires_in": settings.otp_ttl_minutes * 60,
    }
    # Fallback so the flow is usable without SES; hidden once email works.
    if not sent and settings.otp_dev_return:
        out["dev_otp"] = code
    return out


@router.post("/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)):
    """Step 1 of signup: email a one-time code. The account is NOT created yet —
    the caller must confirm the code at POST /api/auth/verify-email. This proves
    the user controls the inbox before any `users` row exists."""
    email = body.email.lower()
    if db.query(User.id).filter(User.email == email).first():
        raise conflict("An account with this email already exists")
    return _start_verification(
        db, email=email, password=body.password, display_name=body.display_name
    )


@router.post("/signup/resend")
def resend_otp(body: ResendOtpIn, db: Session = Depends(get_db)):
    """Re-send the signup code for a pending verification (mints a fresh code and
    resets the attempt counter). Reuses the password/name captured at signup."""
    email = body.email.lower()
    rec = db.query(EmailVerification).filter(EmailVerification.email == email).first()
    if not rec:
        raise not_found("No pending signup for this email — start again")
    code = _gen_otp()
    rec.code_hash = _hash_code(code)
    rec.attempts = 0
    rec.expires_at = now() + timedelta(minutes=settings.otp_ttl_minutes)
    db.commit()

    from ..email import send_otp_email

    sent = send_otp_email(
        to_email=rec.email, code=code, display_name=rec.display_name,
        ttl_minutes=settings.otp_ttl_minutes,
    )
    if not sent:
        log.info("Signup OTP (resend) for %s: %s (email delivery off)", rec.email, code)
    out = {"pending": True, "email": rec.email, "email_sent": sent, "expires_in": settings.otp_ttl_minutes * 60}
    if not sent and settings.otp_dev_return:
        out["dev_otp"] = code
    return out


@router.post("/verify-email")
def verify_email(body: VerifyEmailIn, response: Response, db: Session = Depends(get_db)):
    """Step 2 of signup: confirm the emailed code, then create the account and
    return a session. The user owns the password they chose, so they are NOT
    forced through the change-password gate."""
    email = body.email.lower()
    rec = db.query(EmailVerification).filter(EmailVerification.email == email).first()
    if not rec:
        raise validation("No pending signup for this email — start again")
    if rec.expires_at.replace(tzinfo=now().tzinfo) < now():
        db.delete(rec)
        db.commit()
        raise validation("This code has expired — request a new one")
    if rec.attempts >= settings.otp_max_attempts:
        db.delete(rec)
        db.commit()
        raise validation("Too many incorrect attempts — start again")
    if _hash_code(body.code) != rec.code_hash:
        rec.attempts += 1
        db.commit()
        raise unauthorized("That code is incorrect")

    # Someone could have grabbed the email between start and verify.
    if db.query(User.id).filter(User.email == email).first():
        db.delete(rec)
        db.commit()
        raise conflict("An account with this email already exists")

    user = User(
        email=email,
        password_hash=rec.password_hash,  # already hashed at start
        username=_unique_username(db, rec.display_name or email.split("@")[0]),
        display_name=rec.display_name,
        # They verified via OTP and set their own password → no reset gate.
        must_change_password=False,
    )
    db.add(user)
    db.delete(rec)
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
            # OAuth accounts sign in with Google; they can set a password anytime
            # from the dashboard (email-verified reset) — no forced-reset gate.
            must_change_password=False,
        )
        db.add(user)
        db.commit()
    return _session_payload(db, response, user)


# Cache the Microsoft JWKS client per tenant so we don't refetch signing keys on
# every sign-in (PyJWKClient caches keys internally once constructed).
_MS_JWK_CLIENTS: dict[str, object] = {}


@router.post("/microsoft")
def microsoft(body: GoogleIn, response: Response, db: Session = Depends(get_db)):
    """Microsoft / Azure AD OAuth: the dashboard signs the user in with MSAL and
    sends the resulting id_token here; we verify it against Microsoft's JWKS and
    upsert the user. Disabled (clear 403) until MICROSOFT_CLIENT_ID is set."""
    import jwt
    from jwt import PyJWKClient

    if not settings.microsoft_client_id:
        raise forbidden("Microsoft sign-in is not configured (set MICROSOFT_CLIENT_ID)")
    tenant = settings.microsoft_tenant or "common"
    jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    client = _MS_JWK_CLIENTS.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url)
        _MS_JWK_CLIENTS[jwks_url] = client
    try:
        signing_key = client.get_signing_key_from_jwt(body.id_token)
        claims = jwt.decode(
            body.id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.microsoft_client_id,
            # "common" issues tokens whose issuer embeds the caller's tenant id, so
            # we verify signature + audience + expiry and skip strict issuer match.
            options={"verify_iss": False},
        )
    except Exception:
        raise unauthorized("Invalid Microsoft token")
    email = str(claims.get("email") or claims.get("preferred_username") or "").lower()
    if not email or "@" not in email:
        raise unauthorized("Microsoft account has no usable email")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        name = claims.get("name") or email.split("@")[0]
        user = User(
            email=email,
            password_hash="",
            username=_unique_username(db, name),
            display_name=name,
            must_change_password=False,  # OAuth account; can set a password later
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


@router.get("/me/entitlements")
def my_entitlements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Personal plan, quotas, usage, and MCP access for the current user (spec §2)."""
    from ..entitlements import user_entitlements

    return user_entitlements(db, user)


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
    # Candidate = everything homed anywhere in the orgs I belong to; then keep
    # only what my membership + the resource's audience (visibility) permit. This
    # correctly surfaces sibling-pod resources that were elevated to PROJECT/ORG,
    # and hides pod-private resources from pods I'm not in.
    from ..visibility import filter_visible

    org_ids = [r[0] for r in db.query(OrgMember.org_id).filter(OrgMember.user_id == user.id).all()]
    if not org_ids:
        return []
    project_ids = [r[0] for r in db.query(Project.id).filter(Project.org_id.in_(org_ids)).all()]
    pod_ids = (
        [r[0] for r in db.query(Pod.id).filter(Pod.project_id.in_(project_ids)).all()]
        if project_ids else []
    )
    clauses = [and_(Resource.scope_type == "ORG", Resource.scope_id.in_(org_ids))]
    if project_ids:
        clauses.append(and_(Resource.scope_type == "PROJECT", Resource.scope_id.in_(project_ids)))
    if pod_ids:
        clauses.append(and_(Resource.scope_type == "POD", Resource.scope_id.in_(pod_ids)))
    rows = db.query(Resource).filter(or_(*clauses)).order_by(Resource.updated_at.desc()).all()
    rows = filter_visible(db, rows, user)
    return resources_out(db, rows, user)


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


# ---- In-dashboard password reset via email OTP ----
# For a SIGNED-IN user who wants to reset their password with email verification
# (e.g. they forgot their current one). Distinct from change-password (which needs
# the current password) — here a code emailed to their own inbox is the proof.


@router.post("/password/reset-otp")
def start_password_reset(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Email the signed-in user a one-time code to authorize a password reset."""
    code = _gen_otp()
    db.query(PasswordResetOtp).filter(PasswordResetOtp.user_id == user.id).delete()
    rec = PasswordResetOtp(
        user_id=user.id,
        code_hash=_hash_code(code),
        expires_at=now() + timedelta(minutes=settings.otp_ttl_minutes),
    )
    db.add(rec)
    db.commit()

    from ..email import send_otp_email

    sent = send_otp_email(
        to_email=user.email, code=code, display_name=user.display_name,
        ttl_minutes=settings.otp_ttl_minutes, purpose="password_reset",
    )
    if not sent:
        log.info("Password-reset OTP for %s: %s (email delivery off)", user.email, code)
    out = {"pending": True, "email": user.email, "email_sent": sent, "expires_in": settings.otp_ttl_minutes * 60}
    if not sent and settings.otp_dev_return:
        out["dev_otp"] = code
    return out


@router.post("/password/reset-verify")
def verify_password_reset(
    body: PasswordResetVerifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Confirm the emailed code and set the new password."""
    rec = db.query(PasswordResetOtp).filter(PasswordResetOtp.user_id == user.id).first()
    if not rec:
        raise validation("Request a reset code first")
    if rec.expires_at.replace(tzinfo=now().tzinfo) < now():
        db.delete(rec)
        db.commit()
        raise validation("This code has expired — request a new one")
    if rec.attempts >= settings.otp_max_attempts:
        db.delete(rec)
        db.commit()
        raise validation("Too many incorrect attempts — request a new code")
    if _hash_code(body.code) != rec.code_hash:
        rec.attempts += 1
        db.commit()
        raise unauthorized("That code is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.delete(rec)
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
