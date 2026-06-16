"""3.1 Auth — signup, login, google, refresh, logout, me."""

import re

import httpx
from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from pydantic import BaseModel, Field

from .. import storage
from ..config import get_settings
from ..database import get_db
from ..errors import conflict, forbidden, not_found, unauthorized, validation
from ..models import ApiToken, User
from ..schemas import GoogleIn, LoginIn, MePatch, SignupIn
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
from ..serialize import user_out

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
    return {**user_out(user), "is_admin": user.is_admin}


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
            password_hash="",  # OAuth-only account
            username=_unique_username(db, name),
            display_name=name,
            avatar_url=info.get("picture"),
        )
        db.add(user)
        db.commit()
    return _session_payload(db, response, user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE) or ""
    if not raw:
        raise unauthorized("Missing refresh token")
    user, new_refresh = rotate_refresh_token(db, raw)
    _set_refresh_cookie(response, new_refresh)
    return {"user": user_out(user), "access_token": create_access_token(user), "refresh_token": new_refresh}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_refresh_token(db, request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _me_out(user)


@router.patch("/me")
def update_me(body: MePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field in ("display_name", "bio", "location", "website", "is_publisher"):
        value = getattr(body, field)
        if value is not None:
            setattr(user, field, value)
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
