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

from .. import ai, github
from ..database import get_db
from ..entitlements import enforce_can_add_resource
from ..errors import forbidden, not_found, validation
import re

from ..integrations import (
    INTEGRATIONS_FLAG,
    auth_methods_for,
    available_providers,
    compute_capabilities,
    connection_out,
    connection_token,
    get_credentials,
    has_capability,
    link_out,
    provider_available,
    provider_out,
    push_resource_to,
    resource_repo_files,
    scope_link_out,
    set_credentials,
    visibility_matches,
)
from ..entitlements import _resolve_owning_org
from ..features import feature_enabled
from ..models import IntegrationProvider, OrgIntegration, Resource, ResourceRepoLink, ScopeRepoLink, User
from ..permissions import org_by_slug, require_org_admin, require_org_member
from ..schemas import (
    GithubBulkImportIn,
    GithubLinkIn,
    GithubPublishIn,
    GithubPublishScopeIn,
    GithubResourceRefIn,
    IntegrationConfigPatch,
    IntegrationConnectIn,
    ScopeRepoLinkIn,
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
    creds = get_credentials(conn)
    # GitHub App installation tokens expire hourly — mint a fresh one each call
    # from the stored installation_id (the stored token is only a bootstrap).
    if conn.auth_method == "github_app":
        from ..config import get_settings as _gs

        s = _gs()
        iid = creds.get("installation_id")
        if not iid or not (s.github_app_id and s.github_app_private_key):
            raise validation("This GitHub App connection is missing its installation — reconnect it")
        return github.installation_token(s.github_app_id, s.github_app_private_key_pem, iid)["token"]
    token = creds.get("token")
    if not token:
        raise validation("This GitHub connection has no stored token — reconnect the integration")
    return token


def _valid_auth_method(provider_key: str, method: str) -> str:
    """Reject unknown / not-yet-available connection methods."""
    methods = {m["key"]: m for m in auth_methods_for(provider_key)}
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


def _ensure_repo_webhook(conn: OrgIntegration, token: str, full_name: str) -> None:
    """Best-effort: register a push/release webhook on a repo so live sync works.
    Skipped for GitHub App connections (the App delivers events org-wide via its
    own webhook) and when the connection lacks the webhooks capability or no
    webhook secret is configured."""
    if conn.auth_method == "github_app" or not has_capability(conn, "webhooks"):
        return
    from ..config import get_settings as _gs

    s = _gs()
    if not s.github_webhook_secret:
        return
    url = f"{s.integration_base_url.rstrip('/')}/api/integrations/github/webhook"
    github.register_webhook(token, full_name, url, s.github_webhook_secret)


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
    try:
        if conn.auth_method == "github_app":
            # App connection: re-read the installation account (no /user for App
            # tokens); permissions are fixed at install → keep the capability set.
            from ..config import get_settings as _gs
            from ..integrations import compute_capabilities as _cc2

            s = _gs()
            iid = get_credentials(conn).get("installation_id")
            acct = github.get_installation_account(s.github_app_id, s.github_app_private_key_pem, iid)
            conn.account_label = acct.get("login") or conn.account_label
            conn.account_type = acct.get("type")
            conn.account_url = acct.get("html_url")
            conn.account_avatar = acct.get("avatar_url")
            conn.capabilities = _cc2("github", ["repo", "read:org", "admin:repo_hook"])
            conn.status = "connected"
            conn.last_error = None
            conn.last_synced_at = datetime.now(timezone.utc)
        else:
            _apply_github_account(conn, _github_token(db, org, conn), conn.account_label)
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


def _do_publish(db: Session, org, conn: OrgIntegration, token: str, resource: Resource,
                repo_full_name: str | None, path: str, user: User) -> ResourceRepoLink:
    """Create/refresh a managed repo (visibility mirroring the resource) or push
    into an existing one, write the resource's files, and upsert the link."""
    private = not resource.is_public
    if repo_full_name:
        repo = github.get_repo(token, repo_full_name)
        if not repo:
            raise not_found(f'Repository "{repo_full_name}"')
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
        full_path = f"{path.rstrip('/')}/{p}" if path else p
        last_sha = github.put_file(token, repo["full_name"], full_path, content,
                                   f"skillshare: publish {resource.title}", branch)
    github.set_topics(token, repo["full_name"], resource.tags or [])
    _ensure_repo_webhook(conn, token, repo["full_name"])

    link = _upsert_link(db, org, resource, repo, path, managed, user)
    link.direction = "write"
    link.last_pushed_sha = last_sha
    link.last_pushed_at = datetime.now(timezone.utc)
    return link


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
    link = _do_publish(db, org, conn, token, resource, body.repo_full_name, body.path, user)
    db.flush()
    log_activity(db, user_id=user.id, org_id=org.id, verb="published",
                 object_type="resource", object_id=resource.id, object_title=resource.title,
                 meta=f"published to github:{link.repo_full_name}")
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
    _ensure_repo_webhook(conn, token, repo["full_name"])
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


# --------------------------------------------------------------------------- #
# Bulk: full-account scan, bulk import, scope publish, sync-all
# --------------------------------------------------------------------------- #

def _scope_resources(db: Session, org, scope_type: str, scope_id: str | None) -> list[Resource]:
    """Resources homed in a scope. ORG → the whole org subtree; PROJECT/POD →
    that scope only (after verifying it belongs to the org)."""
    from ..models import Pod, Project

    if scope_type == "ORG":
        pids = [r[0] for r in db.query(Project.id).filter(Project.org_id == org.id).all()]
        podids = [r[0] for r in db.query(Pod.id).join(Project, Pod.project_id == Project.id)
                  .filter(Project.org_id == org.id).all()]
        from sqlalchemy import and_, or_
        clauses = [and_(Resource.scope_type == "ORG", Resource.scope_id == org.id)]
        if pids:
            clauses.append(and_(Resource.scope_type == "PROJECT", Resource.scope_id.in_(pids)))
        if podids:
            clauses.append(and_(Resource.scope_type == "POD", Resource.scope_id.in_(podids)))
        return db.query(Resource).filter(or_(*clauses)).all()
    owning = _resolve_owning_org(db, scope_type, scope_id)
    if owning is None or owning.id != org.id:
        raise forbidden("That scope doesn't belong to this organization")
    return db.query(Resource).filter(Resource.scope_type == scope_type, Resource.scope_id == scope_id).all()


def _import_detected(db: Session, org, user: User, scope_type: str, scope_id: str | None, detected) -> list[Resource]:
    """Create resources from detected items, idempotent by source_fingerprint."""
    created: list[Resource] = []
    for d in detected:
        if d.fingerprint and db.query(Resource.id).filter(
            Resource.scope_type == scope_type, Resource.scope_id == scope_id,
            Resource.source_fingerprint == d.fingerprint,
        ).first():
            continue
        try:
            enforce_can_add_resource(db, user, scope_type, scope_id)
        except Exception:
            break  # quota hit — stop gracefully
        payload = d.to_create_payload(scope_type, scope_id)
        r = Resource(
            type=payload["type"], title=payload["title"], description=payload.get("description", ""),
            content_md=payload.get("content_md", ""), server_url=payload.get("server_url"),
            config_json=payload.get("config_json"), tags=payload.get("tags") or [],
            attachments=payload.get("attachments") or [], scope_type=scope_type, scope_id=scope_id,
            author_id=user.id, is_public=False, source_fingerprint=d.fingerprint,
        )
        db.add(r)
        db.flush()
        created.append(r)
    return created


@router.post("/github/scan")
def github_scan(
    slug: str, account: str = "", max_repos: int = 30, use_ai: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Scan the connected account's repositories and detect skills/MCPs/notes in
    each (dry run — nothing is created). Optionally AI-enrich the summary when
    ANTHROPIC_API_KEY is set."""
    org = org_by_slug(db, slug)
    conn = _require_github(db, org, user)
    token = _github_token(db, org, conn)
    repos = github.list_all_repos(token, account=account or conn.account_label)[:max(1, min(max_repos, 100))]
    out = []
    for repo in repos:
        try:
            _ref, found, _meta = github.detect_from_url(f"github.com/{repo['full_name']}", token=token)
        except Exception:
            found = []
        item = {"repo": repo, "detected": [d.preview() for d in found]}
        if use_ai and ai.enabled() and not repo.get("description"):
            meta = ai.generate_metadata(repo["full_name"], "repository", repo.get("description") or repo["name"])
            if meta:
                item["ai"] = meta
        out.append(item)
    return {"scanned": len(repos), "ai_enabled": ai.enabled(), "results": out}


@router.post("/github/bulk-import")
def github_bulk_import(
    slug: str, body: GithubBulkImportIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Import detected resources from several repos into a scope at once."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    token = _github_token(db, org, conn)
    if body.scope_type not in ("ORG", "PROJECT", "POD"):
        raise validation("scope_type must be ORG, PROJECT, or POD")
    if body.scope_type == "ORG":
        scope_id = org.id
    else:
        scope_id = body.scope_id
        owning = _resolve_owning_org(db, body.scope_type, scope_id)
        if owning is None or owning.id != org.id:
            raise forbidden("That scope doesn't belong to this organization")
    total = []
    for full in body.repos[:100]:
        try:
            _ref, found, _meta = github.detect_from_url(f"github.com/{full}", token=token)
        except Exception:
            continue
        total.extend(_import_detected(db, org, user, body.scope_type, scope_id, found))
    db.commit()
    return {"created": [resource_out(db, r, user) for r in total], "count": len(total)}


@router.post("/github/publish-scope")
def github_publish_scope(
    slug: str, body: GithubPublishScopeIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Publish every resource in a scope to GitHub — one managed repo per
    resource, visibility mirrored. The bulk counterpart of /github/publish."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    token = _github_token(db, org, conn)
    resources = _scope_resources(db, org, body.scope_type, body.scope_id)
    published = []
    for resource in resources:
        try:
            link = _do_publish(db, org, conn, token, resource, None, "", user)
            published.append(link_out(link, resource))
        except Exception:
            continue  # skip a resource that fails; keep going
    db.commit()
    return {"published": published, "count": len(published)}


@router.post("/github/sync-all")
def github_sync_all(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-push every linked resource in the org to its repo (bulk write sync)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    token = _github_token(db, org, conn)
    pushed = 0
    for link in db.query(ResourceRepoLink).filter(ResourceRepoLink.org_id == org.id).all():
        resource = db.get(Resource, link.resource_id)
        if resource is None:
            continue
        try:
            branch = (github.get_repo(token, link.repo_full_name) or {}).get("default_branch") or "main"
            for p, content in resource_repo_files(resource):
                full_path = f"{link.path.rstrip('/')}/{p}" if link.path else p
                link.last_pushed_sha = github.put_file(token, link.repo_full_name, full_path, content,
                                                       f"skillshare: sync {resource.title}", branch)
            link.last_pushed_at = datetime.now(timezone.utc)
            pushed += 1
        except Exception:
            continue
    db.commit()
    return {"pushed": pushed}


# --------------------------------------------------------------------------- #
# Scope↔repo links: attach a repo to an org / team / pod (many per scope),
# auto-sync on resource add, org public/private pairing
# --------------------------------------------------------------------------- #

def _verify_scope(db: Session, org, scope_type: str, scope_id: str) -> None:
    if scope_type not in ("ORG", "PROJECT", "POD"):
        raise validation("scope_type must be ORG, PROJECT, or POD")
    if scope_type == "ORG":
        if scope_id != org.id:
            raise forbidden("That scope doesn't belong to this organization")
        return
    owning = _resolve_owning_org(db, scope_type, scope_id)
    if owning is None or owning.id != org.id:
        raise forbidden("That scope doesn't belong to this organization")


@router.get("/github/scope-links")
def github_scope_links(
    slug: str, scope_type: str = "", scope_id: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Repos attached to the org's scopes (org / team / pod). Filter by a scope."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    q = db.query(ScopeRepoLink).filter(ScopeRepoLink.org_id == org.id)
    if scope_type:
        q = q.filter(ScopeRepoLink.scope_type == scope_type)
    if scope_id:
        q = q.filter(ScopeRepoLink.scope_id == scope_id)
    return [scope_link_out(l) for l in q.order_by(ScopeRepoLink.created_at.desc()).all()]


@router.post("/github/scope-links")
def github_attach_scope(
    slug: str, body: ScopeRepoLinkIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Attach a repo to a scope. Resources in the scope whose visibility matches
    auto-sync to it. Attach a public repo (visibility=public) + a private repo
    (visibility=private) at ORG scope for the public/private pairing."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    _verify_scope(db, org, body.scope_type, body.scope_id)
    token = _github_token(db, org, conn)
    repo = github.get_repo(token, body.repo_full_name)
    if not repo:
        raise not_found(f'Repository "{body.repo_full_name}"')
    existing = (
        db.query(ScopeRepoLink)
        .filter(ScopeRepoLink.org_id == org.id, ScopeRepoLink.scope_type == body.scope_type,
                ScopeRepoLink.scope_id == body.scope_id, ScopeRepoLink.repo_full_name == body.repo_full_name)
        .first()
    )
    link = existing or ScopeRepoLink(org_id=org.id, scope_type=body.scope_type, scope_id=body.scope_id,
                                     created_by=user.id)
    link.repo_full_name = repo["full_name"]
    link.repo_url = repo.get("html_url")
    link.visibility = body.visibility
    link.auto_sync = body.auto_sync
    link.path_prefix = body.path_prefix
    if existing is None:
        db.add(link)
    _ensure_repo_webhook(conn, token, repo["full_name"])
    db.commit()
    return scope_link_out(link)


@router.delete("/github/scope-links/{link_id}")
def github_detach_scope(slug: str, link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detach a repo from a scope (does not delete the repo)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    db.query(ScopeRepoLink).filter(ScopeRepoLink.id == link_id, ScopeRepoLink.org_id == org.id).delete()
    db.commit()
    return {"ok": True}


@router.post("/github/scope-links/{link_id}/sync")
def github_scope_sync(slug: str, link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Push every matching resource currently in the scope to the attached repo."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    link = db.query(ScopeRepoLink).filter(ScopeRepoLink.id == link_id, ScopeRepoLink.org_id == org.id).first()
    if link is None:
        raise not_found("Scope link")
    token = _github_token(db, org, conn)
    pushed = 0
    for resource in _scope_resources(db, org, link.scope_type, link.scope_id):
        if not visibility_matches(link.visibility, resource.is_public):
            continue
        try:
            push_resource_to(token, link.repo_full_name, resource, link.path_prefix)
            pushed += 1
        except Exception:
            continue
    link.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return {"pushed": pushed}


# --------------------------------------------------------------------------- #
# OAuth App / GitHub App connect flow, webhooks, cron sync (config-gated)
# --------------------------------------------------------------------------- #

from fastapi import Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from itsdangerous import BadSignature, URLSafeTimedSerializer  # noqa: E402

from ..config import get_settings  # noqa: E402

_settings = get_settings()
public_router = APIRouter(prefix="/api/integrations", tags=["integrations"])
cron_router = APIRouter(prefix="/api/cron", tags=["integrations"])


def _state_serializer() -> URLSafeTimedSerializer:
    from ..config import get_settings as _gs
    return URLSafeTimedSerializer(_gs().jwt_secret, salt="gh-connect")


def _callback_url() -> str:
    return f"{get_settings().integration_base_url.rstrip('/')}/api/integrations/github/oauth/callback"


def _store_flow_connection(db: Session, org, user: User, token: str, method: str, installation_id: str | None = None):
    """Create/update the org's GitHub connection from an OAuth/App flow token."""
    from ..integrations import compute_capabilities as _cc

    conn = _connection(db, org, "github")
    if conn is None:
        conn = OrgIntegration(org_id=org.id, provider_key="github", connected_by=user.id)
        db.add(conn)
    conn.auth_method = method
    conn.connected_by = user.id
    conn.token_hint = token[-4:]
    creds = {"token": token}
    if installation_id:
        creds["installation_id"] = installation_id
    set_credentials(conn, creds)
    if method == "github_app":
        # Installation tokens can't call /user — read the account from the
        # installation, and trust the App's configured read/write permissions
        # (they aren't reported as X-OAuth scopes).
        s = get_settings()
        acct = github.get_installation_account(s.github_app_id, s.github_app_private_key_pem, installation_id)
        conn.account_label = acct.get("login")
        conn.account_type = acct.get("type")
        conn.account_url = acct.get("html_url")
        conn.account_avatar = acct.get("avatar_url")
        conn.scopes = []
        conn.capabilities = _cc("github", ["repo", "read:org", "admin:repo_hook"])
        conn.status = "connected"
        conn.last_error = None
        conn.last_synced_at = datetime.now(timezone.utc)
    else:  # oauth — a real user token, /user works
        _apply_github_account(conn, token, None)
    db.flush()
    db.commit()
    return conn


@router.post("/github/oauth/start")
def github_oauth_start(slug: str, method: str = "oauth", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Begin a browser connect flow. Returns the GitHub URL to open: an OAuth
    authorize URL (method=oauth) or the App install URL (method=github_app)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    _valid_auth_method("github", method)
    s = get_settings()
    state = _state_serializer().dumps({"org_id": org.id, "user_id": user.id, "method": method})
    if method == "oauth":
        url = (
            "https://github.com/login/oauth/authorize"
            f"?client_id={s.github_oauth_client_id}&redirect_uri={_callback_url()}"
            f"&scope=repo%20read:org%20read:user&state={state}"
        )
    else:  # github_app install
        url = f"https://github.com/apps/{s.github_app_slug}/installations/new?state={state}"
    return {"authorize_url": url}


@public_router.get("/github/oauth/callback")
def github_oauth_callback(request: Request, db: Session = Depends(get_db)):
    """Public callback for both OAuth (code) and App install (installation_id)."""
    s = get_settings()
    params = request.query_params
    state = params.get("state", "")
    try:
        data = _state_serializer().loads(state, max_age=1800)
    except BadSignature:
        raise validation("Invalid or expired connect state")
    org = db.get(__import__("app.models", fromlist=["Organization"]).Organization, data["org_id"])
    user = db.get(User, data["user_id"])
    if not org or not user:
        raise not_found("Organization")

    if params.get("code"):  # OAuth App
        if not (s.github_oauth_client_id and s.github_oauth_client_secret):
            raise validation("GitHub OAuth is not configured")
        res = github.oauth_exchange_code(s.github_oauth_client_id, s.github_oauth_client_secret, params["code"], _callback_url())
        _store_flow_connection(db, org, user, res["access_token"], "oauth")
    elif params.get("installation_id"):  # GitHub App install
        if not (s.github_app_id and s.github_app_private_key):
            raise validation("GitHub App is not configured")
        tok = github.installation_token(s.github_app_id, s.github_app_private_key_pem, params["installation_id"])
        _store_flow_connection(db, org, user, tok["token"], "github_app", installation_id=params["installation_id"])
    else:
        raise validation("Missing code/installation_id")
    return RedirectResponse(f"{s.frontend_url.rstrip('/')}/dashboard/org/integrations/github")


@public_router.post("/github/webhook")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """Live GitHub → SkillShare sync. Verifies the HMAC signature, then on a
    push/release pulls every linked resource for that repo. 503 until
    GITHUB_WEBHOOK_SECRET is configured."""
    s = get_settings()
    if not s.github_webhook_secret:
        raise validation("Webhooks are not configured")
    body = await request.body()
    if not github.verify_webhook_signature(s.github_webhook_secret, body, request.headers.get("X-Hub-Signature-256")):
        raise forbidden("Invalid webhook signature")
    import json as _json
    payload = _json.loads(body or b"{}")
    full = (payload.get("repository") or {}).get("full_name")
    if not full:
        return {"ok": True, "ignored": "no repository"}
    updated = 0
    for link in db.query(ResourceRepoLink).filter(ResourceRepoLink.repo_full_name == full).all():
        org = db.get(__import__("app.models", fromlist=["Organization"]).Organization, link.org_id)
        conn = _connection(db, org, "github") if org else None
        resource = db.get(Resource, link.resource_id)
        if not (org and conn and resource):
            continue
        try:
            token = get_credentials(conn).get("token")
            _ref, found, _meta = github.detect_from_url(f"github.com/{full}", token=token)
            kind = resource.type.lower()
            match = next((d for d in found if d.kind == kind), found[0] if found else None)
            if match:
                if match.description:
                    resource.description = match.description
                if match.content_md:
                    resource.content_md = match.content_md
                if match.config_json:
                    resource.config_json = match.config_json
                link.last_pulled_at = datetime.now(timezone.utc)
                updated += 1
        except Exception:
            continue
    db.commit()
    return {"ok": True, "updated": updated}


@cron_router.post("/integrations/sync")
def cron_sync(request: Request, db: Session = Depends(get_db)):
    """Scheduled sync entrypoint (call from Cloud Scheduler with X-Cron-Secret).
    Pushes linked resources for connections whose sync_mode writes. 403 until
    CRON_SECRET is set."""
    s = get_settings()
    if not s.cron_secret or request.headers.get("X-Cron-Secret") != s.cron_secret:
        raise forbidden("Cron access denied")
    pushed = 0
    for conn in db.query(OrgIntegration).filter(OrgIntegration.provider_key == "github",
                                                OrgIntegration.status == "connected").all():
        mode = (conn.config or {}).get("sync_mode", "manual")
        if mode not in ("write_only", "bidirectional") or "write" not in (conn.capabilities or []):
            continue
        token = get_credentials(conn).get("token")
        if not token:
            continue
        for link in db.query(ResourceRepoLink).filter(ResourceRepoLink.org_id == conn.org_id).all():
            resource = db.get(Resource, link.resource_id)
            if resource is None:
                continue
            try:
                branch = (github.get_repo(token, link.repo_full_name) or {}).get("default_branch") or "main"
                for p, content in resource_repo_files(resource):
                    fp = f"{link.path.rstrip('/')}/{p}" if link.path else p
                    link.last_pushed_sha = github.put_file(token, link.repo_full_name, fp, content,
                                                           f"skillshare: scheduled sync {resource.title}", branch)
                link.last_pushed_at = datetime.now(timezone.utc)
                pushed += 1
            except Exception:
                continue
    db.commit()
    return {"pushed": pushed}
