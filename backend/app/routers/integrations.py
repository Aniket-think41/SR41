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

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import github
from ..database import get_db
from ..errors import forbidden, not_found, validation
import re

from ..integrations import (
    AUTH_METHODS,
    INTEGRATIONS_FLAG,
    available_providers,
    compute_capabilities,
    connection_out,
    get_credentials,
    has_capability,
    link_out,
    provider_available,
    provider_out,
    resource_repo_files,
    set_credentials,
)
from ..entitlements import _resolve_owning_org
from ..features import feature_enabled
from ..models import IntegrationProvider, OrgIntegration, Resource, ResourceRepoLink, User
from ..permissions import org_by_slug, require_org_admin, require_org_member
from ..schemas import (
    GithubLinkIn,
    GithubPublishIn,
    GithubResourceRefIn,
    IntegrationConfigPatch,
    IntegrationConnectIn,
)
from ..security import get_current_user
from ..serialize import log_activity, resource_out

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


def _valid_auth_method(provider_key: str, method: str) -> str:
    """Reject unknown / not-yet-available connection methods."""
    methods = {m["key"]: m for m in AUTH_METHODS.get(provider_key, [])}
    m = methods.get(method)
    if not m:
        raise validation(f"Unknown connection method '{method}'")
    if not m.get("available", False):
        raise validation(f"{m['name']} isn't available yet")
    return method


def _apply_github_account(conn: OrgIntegration, token: str, account_override: str | None) -> None:
    """Validate the token against GitHub and refresh account metadata + the
    detected scopes/capabilities on the connection. Shared by connect and sync."""
    account = github.validate_token(token)  # raises on a bad token
    conn.account_label = (account_override or account["login"] or "").strip() or account["login"]
    conn.account_type = account.get("type")
    conn.account_url = account.get("html_url")
    conn.account_avatar = account.get("avatar_url")
    conn.scopes = account.get("scopes", [])
    conn.capabilities = compute_capabilities("github", conn.scopes)
    conn.status = "connected"
    conn.last_error = None
    conn.last_synced_at = datetime.now(timezone.utc)


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
    method = _valid_auth_method(provider.key, body.auth_method)
    if provider.key != "github":  # pragma: no cover - only github ships today
        raise validation(f'Connecting "{provider.name}" is not supported yet')

    conn = _connection(db, org, provider_key)
    if conn is None:
        conn = OrgIntegration(org_id=org.id, provider_key=provider_key, connected_by=user.id)
        db.add(conn)
    conn.auth_method = method
    conn.token_hint = token[-4:]
    conn.connected_by = user.id
    set_credentials(conn, {"token": token})
    _apply_github_account(conn, token, body.account)  # validates + detects scopes/caps
    db.flush()
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="connected",
        object_type="integration", object_id=conn.id, object_title=provider.name,
        meta=f"connected {provider.name}",
    )
    db.commit()
    return provider_out(provider, conn)


@router.post("/{provider_key}/sync")
def sync(slug: str, provider_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-check the stored credential and refresh account metadata + detected
    scopes/capabilities. This is how newly-granted permissions get picked up:
    edit the token's scopes on GitHub, then Sync to unlock the gated features —
    no need to paste the token again."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    provider = _get_available_provider(db, org, provider_key)
    conn = _connection(db, org, provider_key)
    if conn is None:
        raise not_found(f'{provider.name} connection')
    token = _github_token(db, org, conn)
    try:
        _apply_github_account(conn, token, conn.account_label)
    except Exception as e:  # surface the failure on the connection instead of 500-ing
        conn.status = "error"
        conn.last_error = str(getattr(e, "detail", None) or e)
        db.commit()
        raise
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
    slug: str, q: str = "", account: str = "", per_page: int = 30, page: int = 1,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Search GitHub repositories, scoped to the connected account by default."""
    org = org_by_slug(db, slug)
    conn = _require_github(db, org, user)
    token = _github_token(db, org, conn)
    scope = account or conn.account_label
    return github.search_repositories(q, token=token, account=scope, per_page=per_page, page=page)


# --------------------------------------------------------------------------- #
# Publish / attach / sync (SkillShare → GitHub, and pull back)
# --------------------------------------------------------------------------- #

def _org_resource(db: Session, org, resource_id: str) -> Resource:
    """Fetch a resource and verify it belongs to this org's scope subtree."""
    r = db.get(Resource, resource_id)
    if r is None:
        raise not_found("Resource")
    owning = _resolve_owning_org(db, r.scope_type, r.scope_id)
    if owning is None or owning.id != org.id:
        raise forbidden("That resource doesn't belong to this organization")
    return r


def _require_write(db: Session, org, conn: OrgIntegration) -> None:
    if not has_capability(conn, "write"):
        raise forbidden("This connection can't write to GitHub — grant the 'repo' scope on your token and press Sync")


def _repo_slug(resource: Resource) -> str:
    base = re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", (resource.title or "resource").lower())) or "resource"
    return base[:80]


def _upsert_link(db: Session, org, resource: Resource, repo: dict, path: str, managed: bool, user: User) -> ResourceRepoLink:
    link = (
        db.query(ResourceRepoLink)
        .filter(ResourceRepoLink.resource_id == resource.id, ResourceRepoLink.repo_full_name == repo["full_name"])
        .first()
    )
    if link is None:
        link = ResourceRepoLink(org_id=org.id, resource_id=resource.id, created_by=user.id)
        db.add(link)
    link.repo_full_name = repo["full_name"]
    link.repo_url = repo.get("html_url")
    link.path = path or ""
    link.visibility = "private" if repo.get("private") else "public"
    link.managed = managed
    return link


@router.get("/github/links")
def github_links(
    slug: str, resource_id: str = "", repo: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Resource⇄repo links for the org. Filter by ``resource_id`` (a resource's
    repos) or ``repo`` (a repo's resources — the reverse mapping)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    q = db.query(ResourceRepoLink).filter(ResourceRepoLink.org_id == org.id)
    if resource_id:
        q = q.filter(ResourceRepoLink.resource_id == resource_id)
    if repo:
        q = q.filter(ResourceRepoLink.repo_full_name == repo)
    out = []
    for link in q.order_by(ResourceRepoLink.created_at.desc()).all():
        out.append(link_out(link, db.get(Resource, link.resource_id)))
    return out


@router.post("/github/publish")
def github_publish(
    slug: str, body: GithubPublishIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Publish a resource to GitHub. No repo → create a managed repo whose
    visibility MIRRORS the resource (public resource → public repo, private →
    private). Repo given → publish into it. Records/refreshes the link."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    _get_available_provider(db, org, "github")
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    token = _github_token(db, org, conn)
    resource = _org_resource(db, org, body.resource_id)
    private = not resource.is_public

    if body.repo_full_name:
        repo = github.get_repo(token, body.repo_full_name)
        if not repo:
            raise not_found(f'Repository "{body.repo_full_name}"')
        managed = False
    else:
        target_org = conn.account_label if (conn.account_type == "Organization") else None
        name = _repo_slug(resource)
        try:
            repo = github.create_repo(token, name, private=private, description=resource.description or "", org=target_org)
        except Exception:
            repo = github.create_repo(token, f"{name}-{resource.id[-6:]}", private=private,
                                      description=resource.description or "", org=target_org)
        managed = True

    branch = repo.get("default_branch") or "main"
    last_sha = None
    for p, content in resource_repo_files(resource):
        full_path = f"{body.path.rstrip('/')}/{p}" if body.path else p
        last_sha = github.put_file(token, repo["full_name"], full_path, content,
                                   f"skillshare: publish {resource.title}", branch)
    github.set_topics(token, repo["full_name"], resource.tags or [])

    link = _upsert_link(db, org, resource, repo, body.path, managed, user)
    link.direction = "write"
    link.last_pushed_sha = last_sha
    link.last_pushed_at = datetime.now(timezone.utc)
    db.flush()
    log_activity(db, user_id=user.id, org_id=org.id, verb="published",
                 object_type="resource", object_id=resource.id, object_title=resource.title,
                 meta=f"published to github:{repo['full_name']}")
    db.commit()
    return link_out(link, resource)


@router.post("/github/push")
def github_push(
    slug: str, body: GithubResourceRefIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Re-push a linked resource's current content to its GitHub repo (write sync)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    token = _github_token(db, org, conn)
    resource = _org_resource(db, org, body.resource_id)
    link = (
        db.query(ResourceRepoLink)
        .filter(ResourceRepoLink.org_id == org.id, ResourceRepoLink.resource_id == resource.id)
        .first()
    )
    if link is None:
        raise not_found("Repository link")
    branch = (github.get_repo(token, link.repo_full_name) or {}).get("default_branch") or "main"
    last_sha = None
    for p, content in resource_repo_files(resource):
        full_path = f"{link.path.rstrip('/')}/{p}" if link.path else p
        last_sha = github.put_file(token, link.repo_full_name, full_path, content,
                                   f"skillshare: sync {resource.title}", branch)
    link.last_pushed_sha = last_sha
    link.last_pushed_at = datetime.now(timezone.utc)
    db.commit()
    return link_out(link, resource)


@router.post("/github/pull")
def github_pull(
    slug: str, body: GithubResourceRefIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Pull the linked repo's content back into the resource (read sync,
    GitHub → SkillShare) by re-running detection over the repo."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    token = _github_token(db, org, conn)
    resource = _org_resource(db, org, body.resource_id)
    link = (
        db.query(ResourceRepoLink)
        .filter(ResourceRepoLink.org_id == org.id, ResourceRepoLink.resource_id == resource.id)
        .first()
    )
    if link is None:
        raise not_found("Repository link")
    url = f"github.com/{link.repo_full_name}"
    if link.path:
        url += f"/tree/{(github.get_repo(token, link.repo_full_name) or {}).get('default_branch') or 'main'}/{link.path}"
    _ref, found, _meta = github.detect_from_url(url, token=token)
    kind = resource.type.lower()
    match = next((d for d in found if d.kind == kind), found[0] if found else None)
    if match is None:
        raise validation("Nothing detected in the linked repository to pull")
    if match.description:
        resource.description = match.description
    if match.content_md:
        resource.content_md = match.content_md
    if match.config_json:
        resource.config_json = match.config_json
    if match.server_url:
        resource.server_url = match.server_url
    link.last_pulled_at = datetime.now(timezone.utc)
    db.flush()
    log_activity(db, user_id=user.id, org_id=org.id, verb="updated",
                 object_type="resource", object_id=resource.id, object_title=resource.title,
                 meta=f"pulled from github:{link.repo_full_name}")
    db.commit()
    return resource_out(db, resource, user)


@router.post("/github/link")
def github_link(
    slug: str, body: GithubLinkIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Attach an existing repo to a resource without pushing (link only)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    token = _github_token(db, org, conn)
    resource = _org_resource(db, org, body.resource_id)
    repo = github.get_repo(token, body.repo_full_name)
    if not repo:
        raise not_found(f'Repository "{body.repo_full_name}"')
    link = _upsert_link(db, org, resource, repo, body.path, managed=False, user=user)
    link.direction = "both"
    db.commit()
    return link_out(link, resource)


@router.delete("/github/links/{link_id}")
def github_unlink(slug: str, link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove a resource⇄repo link (does not delete the GitHub repo)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    db.query(ResourceRepoLink).filter(ResourceRepoLink.id == link_id, ResourceRepoLink.org_id == org.id).delete()
    db.commit()
    return {"ok": True}
