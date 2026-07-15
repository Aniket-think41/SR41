"""Org Integrations — connectable third-party apps (GitHub first).

Routes live under ``/api/orgs/{slug}/integrations`` and are layered gates:
  * org membership (read) / org admin (write),
  * the org's ``integrations`` feature must be enabled (tier PRO+),
  * the specific provider must be available to the org (per-provider tier +
    optional feature flag).

Credentials are validated against the provider, then stored encrypted
(app/crypto.py) — the token is never returned to a client. GitHub repo
discovery/search reuses app/github.py with the stored token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import github
from ..database import get_db
from ..errors import forbidden, not_found, validation
from ..integrations import (
    INTEGRATIONS_FLAG,
    available_providers,
    connection_out,
    get_credentials,
    provider_available,
    provider_out,
    set_credentials,
)
from ..features import feature_enabled
from ..models import IntegrationProvider, OrgIntegration, User
from ..permissions import org_by_slug, require_org_admin, require_org_member
from ..schemas import IntegrationConfigPatch, IntegrationConnectIn
from ..security import get_current_user
from ..serialize import log_activity

router = APIRouter(prefix="/api/orgs/{slug}/integrations", tags=["integrations"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _require_section(db: Session, org, user: User, *, admin: bool = False):
    """Membership (or admin) + the integrations feature must be on for the org."""
    m = require_org_admin(db, org, user) if admin else require_org_member(db, org, user)
    if not feature_enabled(db, org, INTEGRATIONS_FLAG):
        raise forbidden("Integrations are a premium feature — upgrade this organization to Pro to connect apps")
    return m


def _get_available_provider(db: Session, org, key: str) -> IntegrationProvider:
    provider = db.query(IntegrationProvider).filter(IntegrationProvider.key == key).first()
    if not provider or not provider_available(db, org, provider):
        raise not_found(f'Integration "{key}"')
    return provider


def _connection(db: Session, org, key: str) -> OrgIntegration | None:
    return (
        db.query(OrgIntegration)
        .filter(OrgIntegration.org_id == org.id, OrgIntegration.provider_key == key)
        .first()
    )


def _github_token(db: Session, org, conn: OrgIntegration) -> str:
    token = get_credentials(conn).get("token")
    if not token:
        raise validation("This GitHub connection has no stored token — reconnect the integration")
    return token


# --------------------------------------------------------------------------- #
# Listing (read)
# --------------------------------------------------------------------------- #

@router.get("/providers")
def list_providers(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Integration cards available to this org, each annotated with whether it's
    already connected. Backs the Integrations card grid."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    out = []
    for provider in available_providers(db, org):
        out.append(provider_out(provider, _connection(db, org, provider.key)))
    return out


@router.get("")
def list_connections(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The org's active connections only."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    rows = db.query(OrgIntegration).filter(OrgIntegration.org_id == org.id).all()
    return [connection_out(c) for c in rows]


@router.get("/{provider_key}")
def get_provider(slug: str, provider_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Provider detail + this org's connection (drives the config page)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    provider = _get_available_provider(db, org, provider_key)
    return provider_out(provider, _connection(db, org, provider_key))


# --------------------------------------------------------------------------- #
# Connect / configure / disconnect (admin)
# --------------------------------------------------------------------------- #

@router.post("/{provider_key}/connect")
def connect(
    slug: str, provider_key: str, body: IntegrationConnectIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Validate credentials against the provider, then store them encrypted."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    provider = _get_available_provider(db, org, provider_key)

    token = body.token.strip()
    account_label: str | None = body.account
    creds: dict = {"token": token}

    if provider.key == "github":
        account = github.validate_token(token)  # raises on a bad token
        # If the admin named an account, keep it; else use the token's own login.
        account_label = (body.account or account["login"]).strip()
        creds["account"] = account_label
    else:  # pragma: no cover - only github ships today
        raise validation(f'Connecting "{provider.name}" is not supported yet')

    conn = _connection(db, org, provider_key)
    if conn is None:
        conn = OrgIntegration(org_id=org.id, provider_key=provider_key, connected_by=user.id)
        db.add(conn)
    set_credentials(conn, creds)
    conn.status = "connected"
    conn.account_label = account_label
    conn.token_hint = token[-4:]
    conn.last_error = None
    conn.connected_by = user.id
    db.flush()
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="connected",
        object_type="integration", object_id=conn.id, object_title=provider.name,
        meta=f"connected {provider.name}",
    )
    db.commit()
    return provider_out(provider, conn)


@router.patch("/{provider_key}")
def update_config(
    slug: str, provider_key: str, body: IntegrationConfigPatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Update the non-secret settings of a connection (e.g. default sync mode)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    provider = _get_available_provider(db, org, provider_key)
    conn = _connection(db, org, provider_key)
    if conn is None:
        raise not_found(f'{provider.name} connection')
    merged = {**(conn.config or {}), **(body.config or {})}
    conn.config = merged
    db.commit()
    return provider_out(provider, conn)


@router.delete("/{provider_key}")
def disconnect(slug: str, provider_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove a connection (deletes the stored credentials)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, provider_key)
    if conn is not None:
        db.delete(conn)
        db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# GitHub repo discovery / search (uses the stored token)
# --------------------------------------------------------------------------- #

def _require_github(db: Session, org, user: User) -> OrgIntegration:
    _require_section(db, org, user)
    _get_available_provider(db, org, "github")
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    return conn


@router.get("/github/repos")
def github_repos(
    slug: str, account: str = "", per_page: int = 50,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """List repositories visible to the org's connected GitHub account."""
    org = org_by_slug(db, slug)
    conn = _require_github(db, org, user)
    token = _github_token(db, org, conn)
    return github.list_repositories(token, account=account or conn.account_label, per_page=per_page)


@router.get("/github/search")
def github_search(
    slug: str, q: str = "", account: str = "", per_page: int = 30,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Search GitHub repositories, scoped to the connected account by default."""
    org = org_by_slug(db, slug)
    conn = _require_github(db, org, user)
    token = _github_token(db, org, conn)
    scope = account or conn.account_label
    return github.search_repositories(q, token=token, account=scope, per_page=per_page)
