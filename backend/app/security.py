"""
Auth plumbing (BACKEND_SPEC §4.1 / §10):
- pbkdf2_sha256 password hashing (pure-python, no native deps)
- JWT access tokens — HS256 by default, RS256 when a keypair is configured
- DB-backed refresh tokens with rotation, delivered as an HttpOnly cookie
- Personal Access Tokens (`skst_…`) for the CLI / MCP integrations,
  accepted on the same `Authorization: Bearer` header
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .errors import unauthorized
from .models import ApiToken, RefreshToken, User

settings = get_settings()
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

REFRESH_COOKIE = "skillshare_refresh"


def hash_password(plain: str) -> str:
    return pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd.verify(plain, hashed)
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)


def issue_refresh_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return token


def rotate_refresh_token(db: Session, raw: str) -> tuple[User, str]:
    """Validate + revoke the presented token, issue a fresh one (§4.1 rotation)."""
    rec = db.query(RefreshToken).filter(RefreshToken.token == raw, RefreshToken.revoked.is_(False)).first()
    if not rec or rec.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized("Invalid or expired refresh token")
    user = db.get(User, rec.user_id)
    if not user:
        raise unauthorized("Invalid refresh token")
    rec.revoked = True
    new_token = issue_refresh_token(db, user)
    return user, new_token


def revoke_refresh_token(db: Session, raw: str | None) -> None:
    if not raw:
        return
    db.query(RefreshToken).filter(RefreshToken.token == raw).update({"revoked": True})
    db.commit()


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_verify_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Access token expired")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid access token")


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None


# ---- Personal Access Tokens (CLI / MCP — BACKEND_SPEC §10) ----

PAT_PREFIX = "skst_"


def hash_pat(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def mint_pat(db: Session, user: User, name: str, expires_days: int | None = None) -> tuple[ApiToken, str]:
    """Create a PAT. The raw token is returned exactly once — only its hash is stored."""
    raw = PAT_PREFIX + secrets.token_urlsafe(32)
    rec = ApiToken(
        user_id=user.id,
        name=name,
        token_prefix=raw[:12],
        token_hash=hash_pat(raw),
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days else None
        ),
    )
    db.add(rec)
    db.commit()
    return rec, raw


def _user_from_pat(db: Session, raw: str) -> User:
    rec = (
        db.query(ApiToken)
        .filter(ApiToken.token_hash == hash_pat(raw), ApiToken.revoked.is_(False))
        .first()
    )
    if not rec:
        raise unauthorized("Invalid or revoked API token")
    if rec.expires_at and rec.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise unauthorized("API token expired")
    rec.last_used_at = datetime.now(timezone.utc)
    db.commit()
    user = db.get(User, rec.user_id)
    if not user:
        raise unauthorized("User no longer exists")
    return user


def _resolve_user(db: Session, token: str) -> User:
    if token.startswith(PAT_PREFIX):
        return _user_from_pat(db, token)
    payload = _decode(token)
    user = db.get(User, payload.get("sub"))
    if not user:
        raise unauthorized("User no longer exists")
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if not token:
        raise unauthorized()
    return _resolve_user(db, token)


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _bearer(request)
    if not token:
        return None
    try:
        return _resolve_user(db, token)
    except Exception:
        return None
