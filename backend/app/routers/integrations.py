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

from .. import ai, github, hive
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
    hive_client,
    hive_tenant,
    link_out,
    provider_available,
    provider_out,
    push_allowed,
    push_resource_to,
    resource_repo_files,
    scope_link_out,
    set_credentials,
    visibility_matches,
)
from ..entitlements import _resolve_owning_org
from ..features import feature_enabled
from ..models import (
    HiveLink,
    HiveStagedEntity,
    IntegrationProvider,
    OrgIntegration,
    Organization,
    Pod,
    Project,
    Resource,
    ResourceRepoLink,
    ScopeRepoLink,
    User,
)
from ..permissions import (
    ensure_org_member,
    ensure_pod_member,
    ensure_project_member,
    org_by_slug,
    require_org_admin,
    require_org_member,
    resolve_or_provision_user,
)
from ..schemas import (
    GithubBulkImportIn,
    GithubLinkIn,
    GithubPublishIn,
    GithubPublishScopeIn,
    GithubResourceRefIn,
    HiveApplyIn,
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
    if provider.key not in ("github", "hive"):  # pragma: no cover - providers ship incrementally
        raise validation(f'Connecting "{provider.name}" is not supported yet')

    conn = _connection(db, org, provider_key)
    if conn is None:
        conn = OrgIntegration(org_id=org.id, provider_key=provider_key, connected_by=user.id)
        db.add(conn)
    conn.auth_method = method
    conn.token_hint = token[-4:]
    conn.connected_by = user.id
    if provider.key == "hive":
        # Paste-token ("service_token") path. The OAuth popup path lives in
        # /hive/oauth/*. `account` carries the Hive tenant code here.
        _connect_hive_token(db, conn, token, body.account)
    else:
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
    if provider.key == "hive":
        # Re-validate the stored token (refreshing it if expired) so a stale
        # connection surfaces as an error; staging/import is /hive/fetch + apply.
        try:
            client = hive_client(db, conn)
            client.t.call_tool("list_employees", {"limit": 1})
            conn.status = "connected"
            conn.last_error = None
            conn.last_synced_at = datetime.now(timezone.utc)
        except Exception as e:
            conn.status = "error"
            conn.last_error = str(getattr(e, "detail", None) or e)
            db.commit()
            raise
        db.commit()
        return provider_out(provider, conn)
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


def _require_scope_admin(db: Session, org, scope_type: str, scope_id: str, user: User) -> None:
    """Manage rights for a scope's repos: org admin for ORG; project admin (or
    org admin) for PROJECT; pod admin (or project/org admin) for POD. Honors the
    org⊃project⊃pod cascade."""
    from ..models import Pod, Project
    from ..permissions import require_org_admin as _roa, require_pod_admin as _rpa, require_project_admin as _rpra

    if scope_type == "ORG":
        _roa(db, org, user)
    elif scope_type == "PROJECT":
        proj = db.get(Project, scope_id)
        if proj is None or proj.org_id != org.id:
            raise forbidden("That team doesn't belong to this organization")
        _rpra(db, proj, user)
    elif scope_type == "POD":
        pod = db.get(Pod, scope_id)
        proj = db.get(Project, pod.project_id) if pod else None
        if pod is None or proj is None or proj.org_id != org.id:
            raise forbidden("That pod doesn't belong to this organization")
        _rpa(db, pod, user)
    else:
        raise validation("scope_type must be ORG, PROJECT, or POD")


@router.get("/github/scope-links")
def github_scope_links(
    slug: str, scope_type: str = "", scope_id: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Repos attached to the org's scopes (org / team / pod). Filter by a scope.
    Any org member may view."""
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
    """Attach a repo to a scope — an EXISTING repo (repo_full_name, from the
    dropdown) or a NEW one (create_repo_name + create_private). Enforces the
    safety rule: a public repo can only route public resources. Managed by the
    scope's admin (org/project/pod)."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)  # feature + membership
    _verify_scope(db, org, body.scope_type, body.scope_id)
    _require_scope_admin(db, org, body.scope_type, body.scope_id, user)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    _require_write(db, org, conn)
    token = _github_token(db, org, conn)

    wants_private_content = body.visibility in ("all", "private")

    if body.create_repo_name:
        # Creating a repo to hold private content → it MUST be private.
        private = body.create_private or wants_private_content
        target_org = conn.account_label if (conn.account_type == "Organization") else None
        repo = github.create_repo(token, body.create_repo_name, private=private,
                                  description=f"SkillShare {body.scope_type.lower()} resources", org=target_org)
    else:
        if not body.repo_full_name:
            raise validation("Pick an existing repository or provide a name to create one")
        repo = github.get_repo(token, body.repo_full_name)
        if not repo:
            raise not_found(f'Repository "{body.repo_full_name}"')

    # Safety: a PUBLIC repo may only ever receive PUBLIC resources.
    if not repo.get("private") and wants_private_content:
        raise validation(
            "A public repository can only hold public resources. Attach a private repo, "
            "or set the route to \"Public only\"."
        )

    existing = (
        db.query(ScopeRepoLink)
        .filter(ScopeRepoLink.org_id == org.id, ScopeRepoLink.scope_type == body.scope_type,
                ScopeRepoLink.scope_id == body.scope_id, ScopeRepoLink.repo_full_name == repo["full_name"])
        .first()
    )
    link = existing or ScopeRepoLink(org_id=org.id, scope_type=body.scope_type, scope_id=body.scope_id,
                                     created_by=user.id)
    link.repo_full_name = repo["full_name"]
    link.repo_url = repo.get("html_url")
    link.repo_private = bool(repo.get("private"))
    link.visibility = body.visibility
    link.sync_direction = body.sync_direction
    link.auto_sync = body.sync_direction in ("push", "both")
    link.path_prefix = body.path_prefix
    if existing is None:
        db.add(link)
    _ensure_repo_webhook(conn, token, repo["full_name"])
    db.commit()
    return scope_link_out(link)


@router.delete("/github/scope-links/{link_id}")
def github_detach_scope(slug: str, link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Detach a repo from a scope (does not delete the repo). Scope admin only."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    link = db.query(ScopeRepoLink).filter(ScopeRepoLink.id == link_id, ScopeRepoLink.org_id == org.id).first()
    if link is not None:
        _require_scope_admin(db, org, link.scope_type, link.scope_id, user)
        db.delete(link)
        db.commit()
    return {"ok": True}


@router.post("/github/scope-links/{link_id}/sync")
def github_scope_sync(slug: str, link_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run the link's sync now. push/both → push matching resources to the repo;
    pull/both → import the repo's resources into the scope. Scope admin only."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user)
    link = db.query(ScopeRepoLink).filter(ScopeRepoLink.id == link_id, ScopeRepoLink.org_id == org.id).first()
    if link is None:
        raise not_found("Scope link")
    _require_scope_admin(db, org, link.scope_type, link.scope_id, user)
    conn = _connection(db, org, "github")
    if conn is None or conn.status != "connected":
        raise validation("Connect GitHub first")
    token = _github_token(db, org, conn)

    pushed = imported = 0
    if link.sync_direction in ("push", "both"):
        _require_write(db, org, conn)
        for resource in _scope_resources(db, org, link.scope_type, link.scope_id):
            if not push_allowed(link, resource):
                continue
            try:
                push_resource_to(token, link.repo_full_name, resource, link.path_prefix)
                pushed += 1
            except Exception:
                continue
    if link.sync_direction in ("pull", "both"):
        scope_id = org.id if link.scope_type == "ORG" else link.scope_id
        try:
            _ref, found, _meta = github.detect_from_url(f"github.com/{link.repo_full_name}", token=token)
            imported = len(_import_detected(db, org, user, link.scope_type, scope_id, found))
        except Exception:
            imported = 0
    link.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return {"pushed": pushed, "imported": imported}


# --------------------------------------------------------------------------- #
# OAuth App / GitHub App connect flow, webhooks, cron sync (config-gated)
# --------------------------------------------------------------------------- #

from fastapi import Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from itsdangerous import BadSignature, URLSafeTimedSerializer  # noqa: E402

from ..config import get_settings  # noqa: E402

_settings = get_settings()
# --------------------------------------------------------------------------- #
# Hive (HR / directory) — connect, fetch-to-staging, review, selective apply
# --------------------------------------------------------------------------- #

def _connect_hive_token(db: Session, conn: OrgIntegration, token: str, tenant: str | None) -> None:
    """Store a pasted Hive access token + tenant (the service_token method).
    Validates against Hive best-effort; a bad token surfaces as status=error but
    the credential is still stored so the admin can retry Sync."""
    from ..integrations import compute_capabilities as _cc

    tenant = (tenant or "").strip()
    if not tenant:
        raise validation("A Hive tenant code is required — pass it in the 'account' field")
    set_credentials(conn, {"access_token": token, "client_id": "", "client_secret": None})
    conn.config = {**(conn.config or {}), "tenant": tenant}
    conn.account_label = tenant
    conn.account_type = "Tenant"
    conn.account_url = f"{get_settings().hive_base_url.rstrip('/')}/"
    conn.scopes = []
    conn.capabilities = _cc("hive", [])
    try:
        hive.validate_connection({"access_token": token}, tenant)
        conn.status = "connected"
        conn.last_error = None
    except Exception as e:
        conn.status = "error"
        conn.last_error = str(getattr(e, "detail", None) or e)


def _require_hive(db: Session, org, user: User, *, admin: bool = False) -> OrgIntegration:
    _require_section(db, org, user, admin=admin)
    _get_available_provider(db, org, "hive")
    conn = _connection(db, org, "hive")
    if conn is None or conn.status not in ("connected", "error"):
        raise validation("Connect Hive first")
    return conn


def _hive_state_serializer() -> URLSafeTimedSerializer:
    from ..config import get_settings as _gs

    return URLSafeTimedSerializer(_gs().jwt_secret, salt="hive-connect")


def _hive_callback_url() -> str:
    return f"{get_settings().integration_base_url.rstrip('/')}/api/integrations/hive/oauth/callback"


def _hive_find_link(db: Session, org, kind: str, external_ref: str) -> HiveLink | None:
    return (
        db.query(HiveLink)
        .filter(HiveLink.org_id == org.id, HiveLink.kind == kind, HiveLink.external_ref == external_ref)
        .first()
    )


def _hive_record_link(db: Session, org, kind: str, external_ref: str, local_id: str) -> HiveLink:
    link = _hive_find_link(db, org, kind, external_ref)
    if link:
        if link.local_id != local_id:
            link.local_id = local_id
        return link
    link = HiveLink(org_id=org.id, kind=kind, external_ref=external_ref, local_id=local_id)
    db.add(link)
    db.flush()
    return link


def _hive_upsert_staged(db: Session, org, kind: str, external_ref: str, *, email, display_name, payload, status):
    row = (
        db.query(HiveStagedEntity)
        .filter(
            HiveStagedEntity.org_id == org.id,
            HiveStagedEntity.kind == kind,
            HiveStagedEntity.external_ref == external_ref,
        )
        .first()
    )
    if row is None:
        row = HiveStagedEntity(org_id=org.id, kind=kind, external_ref=external_ref)
        db.add(row)
    row.email = email
    row.display_name = display_name or ""
    row.payload = payload
    # Preserve an admin's explicit "skipped" decision across re-fetches.
    if row.status != "skipped":
        row.status = status
    row.fetched_at = datetime.now(timezone.utc)
    return row


def _hive_stage(db: Session, org, conn: OrgIntegration) -> dict:
    """Pull the Hive directory and refresh the staging tables with a diff. Never
    writes members/projects/pods — that is /hive/apply. Returns a summary."""
    client = hive_client(db, conn)
    members = client.list_members()
    projects = client.list_projects()
    allocations = client.list_allocations()
    groups = client.list_groups()

    # employee_ref → [project_ref] (active allocations) and project_ref → [member_ref]
    emp_to_projects: dict[str, list[str]] = {}
    proj_to_members: dict[str, list[str]] = {}
    for a in allocations:
        if not a.is_active:
            continue
        emp_to_projects.setdefault(a.employee_ref, []).append(a.project_ref)
        proj_to_members.setdefault(a.project_ref, []).append(a.employee_ref)

    seen = {"employee": set(), "project": set(), "group": set()}
    counts = {"pending": 0, "applied": 0, "removed": 0}

    def _bump(status: str):
        if status in counts:
            counts[status] += 1

    for m in members:
        seen["employee"].add(m.external_ref)
        linked = _hive_find_link(db, org, "org_member", m.external_ref) is not None
        if m.is_active:
            status = "applied" if linked else "pending"
        else:
            if not linked:
                continue  # never imported + inactive → not our concern
            status = "removed"
        _bump(status)
        _hive_upsert_staged(
            db, org, "employee", m.external_ref,
            email=m.email, display_name=m.display_name,
            payload={
                "email": m.email, "display_name": m.display_name, "is_active": m.is_active,
                "status": m.status, "department": m.department, "designation": m.designation,
                "manager_ref": m.manager_ref, "project_refs": emp_to_projects.get(m.external_ref, []),
            },
            status=status,
        )

    for p in projects:
        seen["project"].add(p.external_ref)
        linked = _hive_find_link(db, org, "project", p.external_ref) is not None
        status = "applied" if linked else "pending"
        _bump(status)
        _hive_upsert_staged(
            db, org, "project", p.external_ref,
            email=None, display_name=p.name,
            payload={
                "name": p.name, "code": p.code, "status": p.status, "account_name": p.account_name,
                "tech_stack": p.tech_stack, "pm_name": p.pm_name,
                "member_refs": proj_to_members.get(p.external_ref, []),
            },
            status=status,
        )

    for g in groups:
        seen["group"].add(g.external_ref)
        linked = _hive_find_link(db, org, "pod", g.external_ref) is not None
        status = "applied" if linked else "pending"
        _bump(status)
        _hive_upsert_staged(
            db, org, "group", g.external_ref,
            email=None, display_name=g.name,
            payload={"name": g.name, "description": g.description, "is_active": g.is_active,
                     "member_refs": g.member_refs},
            status=status,
        )

    # Anything we imported before but Hive no longer returns → mark removed
    # (offboard candidate). Only staged rows that were applied.
    for kind, model_kind in (("employee", "org_member"), ("project", "project"), ("group", "pod")):
        for row in db.query(HiveStagedEntity).filter(
            HiveStagedEntity.org_id == org.id, HiveStagedEntity.kind == kind
        ).all():
            if row.external_ref not in seen[kind] and _hive_find_link(db, org, model_kind, row.external_ref):
                if row.status != "removed":
                    row.status = "removed"
                    counts["removed"] += 1

    conn.last_synced_at = datetime.now(timezone.utc)
    conn.status = "connected"
    conn.last_error = None
    return {
        "members": len(members), "projects": len(projects), "groups": len(groups),
        "allocations": len(allocations), **{f"{k}_count": v for k, v in counts.items()},
    }


def _staged_out(row: HiveStagedEntity) -> dict:
    return {
        "id": row.id, "kind": row.kind, "external_ref": row.external_ref,
        "email": row.email, "display_name": row.display_name,
        "status": row.status, "payload": row.payload,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
    }


@router.post("/hive/oauth/start")
def hive_oauth_start(
    slug: str, tenant: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Begin the Hive OAuth popup flow. Returns the authorize URL to open in a
    new tab; on success Hive redirects to our callback which stores the token.
    ``tenant`` is the Hive tenant code (e.g. 'think41')."""
    org = org_by_slug(db, slug)
    _require_section(db, org, user, admin=True)
    _get_available_provider(db, org, "hive")
    tenant = (tenant or "").strip()
    if not tenant:
        raise validation("A Hive tenant code is required to connect")
    redirect_uri = _hive_callback_url()
    client = hive.register_client(redirect_uri)
    verifier, challenge = hive.pkce_pair()
    import uuid as _uuid

    nonce = _uuid.uuid4().hex
    conn = _connection(db, org, "hive")
    if conn is None:
        conn = OrgIntegration(org_id=org.id, provider_key="hive", connected_by=user.id, status="disconnected")
        db.add(conn)
    conn.auth_method = "oauth"
    conn.connected_by = user.id
    conn.config = {
        **(conn.config or {}),
        "tenant": tenant,
        "pending_oauth": {
            "client_id": client["client_id"],
            "client_secret": client.get("client_secret"),
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "nonce": nonce,
        },
    }
    db.commit()
    state = _hive_state_serializer().dumps({"org_id": org.id, "user_id": user.id, "nonce": nonce})
    return {"authorize_url": hive.authorize_url(client["client_id"], redirect_uri, state, challenge)}


@router.post("/hive/fetch")
def hive_fetch(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pull the Hive directory into staging for review. Adds NO members and sends
    NO mail — the admin reviews /hive/staged and then calls /hive/apply."""
    org = org_by_slug(db, slug)
    conn = _require_hive(db, org, user, admin=True)
    summary = _hive_stage(db, org, conn)
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="fetched",
        object_type="integration", object_id=conn.id, object_title="Hive",
        meta=f"fetched Hive directory: {summary['members']} people, {summary['projects']} projects",
    )
    db.commit()
    return summary


@router.get("/hive/staged")
def hive_staged(
    slug: str, kind: str = "", status: str = "",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The staged Hive entities with their diff status (pending/applied/removed/
    skipped), grouped for the review screen. Any org member may view."""
    org = org_by_slug(db, slug)
    _require_hive(db, org, user)
    q = db.query(HiveStagedEntity).filter(HiveStagedEntity.org_id == org.id)
    if kind:
        q = q.filter(HiveStagedEntity.kind == kind)
    if status:
        q = q.filter(HiveStagedEntity.status == status)
    rows = q.order_by(HiveStagedEntity.kind, HiveStagedEntity.display_name).all()
    grouped: dict[str, list] = {"employee": [], "project": [], "group": []}
    for r in rows:
        grouped.setdefault(r.kind, []).append(_staged_out(r))
    counts = {
        s: db.query(HiveStagedEntity).filter(
            HiveStagedEntity.org_id == org.id, HiveStagedEntity.status == s
        ).count()
        for s in ("pending", "applied", "removed", "skipped")
    }
    return {"groups": grouped, "counts": counts}


@router.post("/hive/apply")
def hive_apply(
    slug: str, body: HiveApplyIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Import the selected staged entities into the organization (the explicit,
    admin-driven step). Honors scope (all / members / projects / groups) and an
    optional ref allow-list; creates Projects/Pods when ``create_structure``;
    provisions users silently (no mail); optionally offboards leavers."""
    org = org_by_slug(db, slug)
    conn = _require_hive(db, org, user, admin=True)
    result = _hive_apply_staged(db, org, body)
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="imported",
        object_type="integration", object_id=conn.id, object_title="Hive",
        meta=f"imported from Hive: +{result['members_added']} members, "
             f"{result['projects_created']} projects, {result['pods_created']} pods",
    )
    db.commit()
    return result


def _hive_user_for_ref(db: Session, org, member_ref: str) -> User | None:
    """Resolve (or provision) the SkillShare user for a Hive employee ref, using
    the staged employee's email. Records the user + org_member provenance links.
    Returns None if we can't (no email on file)."""
    staged = (
        db.query(HiveStagedEntity)
        .filter(HiveStagedEntity.org_id == org.id, HiveStagedEntity.kind == "employee",
                HiveStagedEntity.external_ref == member_ref)
        .first()
    )
    if staged is None or not staged.email:
        return None
    u, _temp = resolve_or_provision_user(db, email=staged.email)
    ensure_org_member(db, org.id, u.id, "MEMBER")
    _hive_record_link(db, org, "user", member_ref, u.id)
    _hive_record_link(db, org, "org_member", member_ref, u.id)
    if staged.status == "pending":
        staged.status = "applied"
        staged.applied_at = datetime.now(timezone.utc)
    return u


def _hive_teams_project(db: Session, org, user_id: str) -> Project:
    """The auto-created parent Project that Hive groups (teams) become Pods under
    (Pods require a parent Project). Deduped via a HiveLink sentinel ref."""
    link = _hive_find_link(db, org, "project", "__hive_teams__")
    if link:
        proj = db.get(Project, link.local_id)
        if proj:
            return proj
    proj = Project(org_id=org.id, name="Teams (from Hive)",
                   description="Teams synced from Hive.", created_by=user_id)
    db.add(proj)
    db.flush()
    _hive_record_link(db, org, "project", "__hive_teams__", proj.id)
    return proj


def _hive_apply_staged(db: Session, org, body: HiveApplyIn) -> dict:
    res = {"members_added": 0, "projects_created": 0, "pods_created": 0,
           "memberships_added": 0, "offboarded": 0}
    ref_filter = set(body.refs) if body.refs else None
    do = lambda k: body.scope in ("all", k)  # noqa: E731
    owner_id = org.owner_id

    # 1) Members → org members
    if do("members"):
        q = db.query(HiveStagedEntity).filter(
            HiveStagedEntity.org_id == org.id, HiveStagedEntity.kind == "employee",
            HiveStagedEntity.status == "pending")
        for row in q.all():
            if ref_filter and row.external_ref not in ref_filter:
                continue
            if _hive_user_for_ref(db, org, row.external_ref):
                res["members_added"] += 1

    # 2) Projects → SkillShare Projects (+ allocated members)
    if do("projects") and body.create_structure:
        q = db.query(HiveStagedEntity).filter(
            HiveStagedEntity.org_id == org.id, HiveStagedEntity.kind == "project",
            HiveStagedEntity.status == "pending")
        for row in q.all():
            if ref_filter and row.external_ref not in ref_filter:
                continue
            link = _hive_find_link(db, org, "project", row.external_ref)
            if link and db.get(Project, link.local_id):
                proj = db.get(Project, link.local_id)
            else:
                proj = Project(org_id=org.id, name=row.display_name or "Project",
                               description=(row.payload or {}).get("account_name", ""),
                               tags=(row.payload or {}).get("tech_stack", []) or [],
                               created_by=owner_id)
                db.add(proj)
                db.flush()
                _hive_record_link(db, org, "project", row.external_ref, proj.id)
                res["projects_created"] += 1
            for mref in (row.payload or {}).get("member_refs", []):
                u = _hive_user_for_ref(db, org, mref)
                if u is None:
                    continue
                ensure_project_member(db, proj.id, u.id, "MEMBER")
                if not _hive_find_link(db, org, "project_member", f"{row.external_ref}:{mref}"):
                    _hive_record_link(db, org, "project_member", f"{row.external_ref}:{mref}", u.id)
                    res["memberships_added"] += 1
            row.status = "applied"
            row.applied_at = datetime.now(timezone.utc)

    # 3) Groups → Pods under the "Teams (from Hive)" project (+ members)
    if do("groups") and body.create_structure:
        q = db.query(HiveStagedEntity).filter(
            HiveStagedEntity.org_id == org.id, HiveStagedEntity.kind == "group",
            HiveStagedEntity.status == "pending")
        rows = [r for r in q.all() if not ref_filter or r.external_ref in ref_filter]
        if rows:
            teams = _hive_teams_project(db, org, owner_id)
            for row in rows:
                link = _hive_find_link(db, org, "pod", row.external_ref)
                if link and db.get(Pod, link.local_id):
                    pod = db.get(Pod, link.local_id)
                else:
                    pod = Pod(project_id=teams.id, name=row.display_name or "Team",
                              description=(row.payload or {}).get("description", ""),
                              created_by=owner_id)
                    db.add(pod)
                    db.flush()
                    _hive_record_link(db, org, "pod", row.external_ref, pod.id)
                    res["pods_created"] += 1
                for mref in (row.payload or {}).get("member_refs", []):
                    u = _hive_user_for_ref(db, org, mref)
                    if u is None:
                        continue
                    ensure_project_member(db, teams.id, u.id, "MEMBER")
                    ensure_pod_member(db, pod.id, u.id, "MEMBER")
                    if not _hive_find_link(db, org, "pod_member", f"{row.external_ref}:{mref}"):
                        _hive_record_link(db, org, "pod_member", f"{row.external_ref}:{mref}", u.id)
                        res["memberships_added"] += 1
                row.status = "applied"
                row.applied_at = datetime.now(timezone.utc)

    # 4) Offboard — remove ONLY rows the sync created for entities gone from Hive
    if body.offboard:
        res["offboarded"] += _hive_offboard(db, org)
    return res


def _hive_offboard(db: Session, org) -> int:
    """Remove members/pods the sync created for staged entities now 'removed'
    (leavers / deleted teams). Never touches rows without a HiveLink, so an
    admin's manual additions are safe (the don't-clobber rule)."""
    from ..models import OrgMember, PodMember, ProjectMember

    removed = 0
    for row in db.query(HiveStagedEntity).filter(
        HiveStagedEntity.org_id == org.id, HiveStagedEntity.status == "removed"
    ).all():
        if row.kind == "employee":
            link = _hive_find_link(db, org, "org_member", row.external_ref)
            if not link:
                continue
            uid = link.local_id
            # Drop project/pod memberships the sync created for this user, then org.
            for pl in db.query(HiveLink).filter(
                HiveLink.org_id == org.id, HiveLink.local_id == uid,
                HiveLink.kind.in_(("project_member", "pod_member"))
            ).all():
                db.delete(pl)
            db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.user_id == uid).delete()
            for proj in db.query(Project).filter(Project.org_id == org.id).all():
                db.query(ProjectMember).filter(
                    ProjectMember.project_id == proj.id, ProjectMember.user_id == uid).delete()
                for pod in db.query(Pod).filter(Pod.project_id == proj.id).all():
                    db.query(PodMember).filter(
                        PodMember.pod_id == pod.id, PodMember.user_id == uid).delete()
            for ul in db.query(HiveLink).filter(
                HiveLink.org_id == org.id, HiveLink.external_ref == row.external_ref,
                HiveLink.kind.in_(("user", "org_member"))
            ).all():
                db.delete(ul)
            removed += 1
        row.status = "skipped"  # processed; won't re-offboard
    return removed


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


@public_router.get("/hive/oauth/callback")
def hive_oauth_callback(request: Request, db: Session = Depends(get_db)):
    """Public callback for the Hive OAuth popup. Exchanges the code for a token
    set (access + refresh once Hive issues it), stores it encrypted, and marks
    the connection connected. No members are imported here — that is /hive/apply."""
    s = get_settings()
    params = request.query_params
    try:
        data = _hive_state_serializer().loads(params.get("state", ""), max_age=1800)
    except BadSignature:
        raise validation("Invalid or expired connect state")
    org = db.get(Organization, data["org_id"])
    user = db.get(User, data["user_id"])
    if not org or not user:
        raise not_found("Organization")
    conn = _connection(db, org, "hive")
    pending = (conn.config or {}).get("pending_oauth") if conn else None
    if not conn or not pending or pending.get("nonce") != data.get("nonce"):
        raise validation("No pending Hive connect flow — start again")
    if params.get("error"):
        conn.status = "error"
        conn.last_error = params.get("error_description") or params["error"]
        db.commit()
        return RedirectResponse(f"{s.frontend_url.rstrip('/')}/dashboard/org/integrations/hive?error=1")
    code = params.get("code")
    if not code:
        raise validation("Missing authorization code")
    from ..integrations import compute_capabilities as _cc

    creds = hive.exchange_code(
        code, pending["redirect_uri"], pending["code_verifier"],
        pending["client_id"], pending.get("client_secret"),
    )
    set_credentials(conn, creds)
    tenant = (conn.config or {}).get("tenant") or ""
    conn.auth_method = "oauth"
    conn.token_hint = (creds.get("access_token") or "")[-4:]
    conn.account_label = tenant
    conn.account_type = "Tenant"
    conn.account_url = f"{s.hive_base_url.rstrip('/')}/"
    conn.scopes = []
    conn.capabilities = _cc("hive", [])
    cfg = {**(conn.config or {})}
    cfg.pop("pending_oauth", None)
    conn.config = cfg
    try:
        hive.validate_connection({"access_token": creds["access_token"]}, tenant)
        conn.status = "connected"
        conn.last_error = None
    except Exception as e:
        conn.status = "error"
        conn.last_error = str(getattr(e, "detail", None) or e)
    db.commit()
    return RedirectResponse(f"{s.frontend_url.rstrip('/')}/dashboard/org/integrations/hive")


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

    # Scope links on this repo with a pull direction → import the repo's
    # resources into the scope (GitHub → SkillShare).
    imported = 0
    for slink in db.query(ScopeRepoLink).filter(
        ScopeRepoLink.repo_full_name == full, ScopeRepoLink.provider_key == "github"
    ).all():
        if slink.sync_direction not in ("pull", "both"):
            continue
        org = db.get(__import__("app.models", fromlist=["Organization"]).Organization, slink.org_id)
        conn = _connection(db, org, "github") if org else None
        actor = db.get(User, slink.created_by)
        if not (org and conn and actor):
            continue
        try:
            token = connection_token(conn)
            _ref, found, _meta = github.detect_from_url(f"github.com/{full}", token=token)
            scope_id = org.id if slink.scope_type == "ORG" else slink.scope_id
            imported += len(_import_detected(db, org, actor, slink.scope_type, scope_id, found))
            slink.last_synced_at = datetime.now(timezone.utc)
        except Exception:
            continue

    db.commit()
    return {"ok": True, "updated": updated, "imported": imported}


def run_github_sync_batch(db: Session) -> dict:
    """Push linked resources for every GitHub connection whose sync_mode writes.
    Shared by the cron endpoint and the Celery ``github_sync`` task."""
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


@cron_router.post("/integrations/sync")
def cron_sync(request: Request, db: Session = Depends(get_db)):
    """Scheduled GitHub push-sync (Cloud Scheduler → X-Cron-Secret). Enqueues the
    work to the Celery worker when a broker is configured, else runs it inline.
    403 until CRON_SECRET is set."""
    s = get_settings()
    if not s.cron_secret or request.headers.get("X-Cron-Secret") != s.cron_secret:
        raise forbidden("Cron access denied")
    from ..tasks import enqueue_or_run

    return enqueue_or_run("github_sync", inline=lambda: run_github_sync_batch(db))


def run_hive_sync_batch(db: Session, scope: str = "all") -> dict:
    """Re-fetch every connected Hive org into staging and, for connections that
    opted into hands-off sync (``config.auto_apply`` / ``auto_offboard``), import
    the new/removed entities. Shared by the cron endpoint and the Celery task so
    both paths behave identically. Each connection is isolated — one failure
    doesn't abort the batch. Caller need not commit (this commits per org)."""
    apply_scope = "members" if scope == "members" else "all"
    synced, applied, errors = 0, 0, 0
    for conn in db.query(OrgIntegration).filter(
        OrgIntegration.provider_key == "hive", OrgIntegration.status.in_(("connected", "error"))
    ).all():
        org = db.get(Organization, conn.org_id)
        if org is None:
            continue
        try:
            _hive_stage(db, org, conn)
            synced += 1
            cfg = conn.config or {}
            if cfg.get("auto_apply"):
                body = HiveApplyIn(scope=apply_scope, create_structure=True, notify=False,
                                   offboard=bool(cfg.get("auto_offboard")))
                r = _hive_apply_staged(db, org, body)
                applied += r["members_added"] + r["projects_created"] + r["pods_created"]
            db.commit()
        except Exception as e:  # isolate a bad connection from the batch
            conn.status = "error"
            conn.last_error = str(getattr(e, "detail", None) or e)
            db.commit()
            errors += 1
    return {"synced": synced, "applied": applied, "errors": errors}


@cron_router.post("/hive/sync")
def cron_hive_sync(request: Request, db: Session = Depends(get_db)):
    """Scheduled Hive directory sync (Cloud Scheduler → X-Cron-Secret).

    Recommended cadence (HIVE_INTEGRATION.md §4): daily for people/offboarding,
    weekly for full structure. When a Celery broker is configured the work is
    ENQUEUED to the background worker and this returns immediately; otherwise it
    runs INLINE (graceful fallback). A connection opts into hands-off keeping-in
    -sync via config ``auto_apply`` / ``auto_offboard``; without them the cron
    only refreshes staging for admin review. 403 until CRON_SECRET is set."""
    s = get_settings()
    if not s.cron_secret or request.headers.get("X-Cron-Secret") != s.cron_secret:
        raise forbidden("Cron access denied")
    scope = (request.query_params.get("scope") or "all").strip()  # all | members
    from ..tasks import enqueue_or_run

    return enqueue_or_run("hive_sync", scope, inline=lambda: run_hive_sync_batch(db, scope))
