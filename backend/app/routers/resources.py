"""3.5 Resources — CRUD, scoped lists, inheritance union (§5), publish/star,
uploads (§6), and marketplace import."""

import re

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..errors import ApiError, forbidden, not_found, validation
from ..features import feature_enabled
from ..models import (
    Follow,
    Notification,
    Organization,
    OrgFollow,
    OrgMember,
    Pod,
    Project,
    Resource,
    ResourcePin,
    ResourceStar,
    User,
)
from .. import github, storage
from ..permissions import (
    org_by_slug,
    pod_or_404,
    project_or_404,
    require_org_member,
    require_pod_access,
    require_pod_read,
    require_project_access,
    require_project_read,
    require_resource_read,
    require_resource_write,
    resource_or_404,
    scope_org,
)
from ..schemas import (
    GithubImportIn,
    GithubPreviewIn,
    ImportIn,
    ResourceCreate,
    ResourceMove,
    ResourcePatch,
    ResourceReviewIn,
    UploadIn,
)
from ..security import client_source, get_current_user
from ..serialize import log_activity, resource_out, resources_out, search_rank
from ..visibility import filter_visible, normalize_visibility
from ..entitlements import enforce_can_add_resource
from ..review import approve, can_review, is_publicly_visible, reject, submit_for_review

router = APIRouter(prefix="/api", tags=["resources"])
settings = get_settings()

VALID_TYPES = {"SKILL", "MCP", "NOTE"}
VALID_SCOPES = {"ORG", "PROJECT", "POD", "PUBLIC"}
MAX_PINS = 6  # GitHub-style: a small, curated set on the profile


def _require_scope_write(db: Session, scope_type: str, scope_id: str | None, user: User) -> None:
    """Creating into a scope requires membership at that level (§4.2). The PUBLIC
    scope is the publisher's own marketplace shelf — no org needed, but you must
    be a registered publisher (this is what "add as a publisher" writes to)."""
    if scope_type == "ORG":
        org = db.get(Organization, scope_id)
        if not org:
            raise not_found("Organization")
        require_org_member(db, org, user)
    elif scope_type == "PROJECT":
        require_project_access(db, project_or_404(db, scope_id or ""), user)
    elif scope_type == "POD":
        require_pod_access(db, pod_or_404(db, scope_id or ""), user)
    elif scope_type == "PUBLIC":
        if not user.is_publisher:
            raise forbidden(
                "Become a publisher first (POST /api/auth/become-publisher) to add resources to the marketplace"
            )


def _log_resource(
    db: Session, user: User, r: Resource, verb: str, meta: str | None = None,
    notify_scope: str | None = None, source: str = "web",
) -> None:
    org = scope_org(db, r)
    if not org:
        return
    # Notify the resource's AUDIENCE (its visibility), not just its home scope —
    # a pod resource elevated to PROJECT notifies project members, ORG notifies
    # the whole org. Publish overrides to ORG via notify_scope.
    from ..visibility import home_ids, normalize_visibility

    audience = notify_scope or normalize_visibility(r.scope_type, r.visibility)
    org_id, project_id, pod_id = home_ids(db, r)
    audience_id = {"POD": pod_id, "PROJECT": project_id, "ORG": org.id}.get(audience, org.id)
    log_activity(
        db, user_id=user.id, org_id=org.id, verb=verb,
        object_type="resource", object_id=r.id, object_title=r.title, meta=meta,
        scope_type=audience, scope_id=audience_id, source=source,
    )


@router.post("/resources")
def create_resource(
    body: ResourceCreate, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), source: str = Depends(client_source),
):
    if body.type not in VALID_TYPES:
        raise validation("type must be SKILL, MCP, or NOTE")
    if body.scope_type not in VALID_SCOPES:
        raise validation("scope_type must be ORG, PROJECT, POD, or PUBLIC")
    if not body.title.strip():
        raise validation("Title is required")
    # PUBLIC (publisher) resources carry no scope_id — they live on the author's
    # personal marketplace shelf.
    scope_id = None if body.scope_type == "PUBLIC" else body.scope_id
    _require_scope_write(db, body.scope_type, scope_id, user)
    enforce_can_add_resource(db, user, body.scope_type, scope_id)  # plan/quota gate (spec §2)
    r = Resource(
        type=body.type,
        title=body.title.strip(),
        description=body.description,
        content_md=body.content_md,
        server_url=body.server_url,
        config_json=body.config_json,
        file_url=body.file_url,
        version=body.version or "0.1.0",
        tags=body.tags,
        attachments=[a.model_dump() for a in body.attachments],
        scope_type=body.scope_type,
        scope_id=scope_id,
        # Audience: defaults to the home scope (pod resources are pod-only) unless
        # the author widens it. See app/visibility.py.
        visibility=normalize_visibility(body.scope_type, body.visibility),
        author_id=user.id,
        # Everything is created UNPUBLISHED — a private draft its author owns. A
        # publisher explicitly publishes to the marketplace afterwards (POST
        # /resources/{id}/publish); org content is published + reviewed there too.
        is_public=False,
        source_fingerprint=body.source_fingerprint,
    )
    db.add(r)
    db.flush()
    _log_resource(db, user, r, "created", source=source)
    db.commit()
    return resource_out(db, r, user)


# ---- GitHub-URL ingestion ----
# NOTE: these literal-path routes are declared BEFORE the dynamic
# /resources/{resource_id}/... routes so "github" isn't captured as a resource id.

@router.post("/resources/github/preview")
def github_preview(body: GithubPreviewIn, user: User = Depends(get_current_user)):
    """Detect (without creating anything) the skill(s)/MCP(s)/note(s) inside a
    public GitHub repo. Powers the dashboard 'what did we find?' step and the
    CLI/MCP dry-run."""
    ref, found, meta = github.detect_from_url(body.url)
    return {
        "repo": {
            "owner": ref.owner,
            "repo": ref.repo,
            "ref": ref.ref,
            "description": meta.get("description", ""),
            "html_url": meta.get("html_url", ""),
        },
        "detected": [d.preview() for d in found],
    }


@router.post("/resources/github/import")
def github_import(
    body: GithubImportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Import detected resources from a GitHub URL into a scope. `select` (a list
    of fingerprints) narrows what's imported; empty imports everything found.
    Re-importing is idempotent: items already present in the scope (matched by
    source_fingerprint) are skipped, not duplicated."""
    if body.scope_type not in VALID_SCOPES:
        raise validation("scope_type must be ORG, PROJECT, POD, or PUBLIC")
    _require_scope_write(db, body.scope_type, body.scope_id, user)

    ref, found, _meta = github.detect_from_url(body.url)
    if body.select:
        wanted = set(body.select)
        found = [d for d in found if d.fingerprint in wanted]
    if not found:
        raise validation("No skills, MCP servers, or notes were detected in that repository")

    created: list[Resource] = []
    skipped: list[dict] = []
    for d in found:
        existing = (
            db.query(Resource)
            .filter(
                Resource.source_fingerprint == d.fingerprint,
                Resource.scope_type == body.scope_type,
                Resource.scope_id == body.scope_id,
            )
            .first()
        )
        if existing:
            skipped.append(
                {"title": d.title, "fingerprint": d.fingerprint,
                 "reason": "already imported", "resource_id": existing.id}
            )
            continue
        # Stop importing (gracefully) once the owning entity hits its quota,
        # rather than failing the whole batch (spec §2).
        try:
            enforce_can_add_resource(db, user, body.scope_type, body.scope_id)
        except ApiError as exc:
            skipped.append(
                {"title": d.title, "fingerprint": d.fingerprint, "reason": exc.message}
            )
            continue
        p = d.to_create_payload(body.scope_type, body.scope_id)
        r = Resource(
            type=p["type"],
            title=(p["title"].strip() or ref.repo)[:120],
            description=p["description"],
            content_md=p["content_md"],
            server_url=p["server_url"],
            config_json=p["config_json"],
            version="0.1.0",
            tags=p["tags"],
            attachments=p["attachments"],
            scope_type=p["scope_type"],
            scope_id=p["scope_id"],
            author_id=user.id,
            source_fingerprint=p["source_fingerprint"],
        )
        db.add(r)
        db.flush()
        _log_resource(db, user, r, "created", meta="imported from GitHub")
        created.append(r)
    db.commit()
    return {
        "created": [resource_out(db, r, user) for r in created],
        "skipped": skipped,
        "repo": {"owner": ref.owner, "repo": ref.repo},
    }


@router.get("/resources/{resource_id}")
def get_resource(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    require_resource_read(db, r, user)
    return resource_out(db, r, user)


@router.patch("/resources/{resource_id}")
def update_resource(
    resource_id: str, body: ResourcePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    data = body.model_dump(exclude_unset=True)
    if "scope_type" in data and data["scope_type"] not in VALID_SCOPES:
        raise validation("scope_type must be ORG, PROJECT, POD, or PUBLIC")
    if "scope_type" in data or "scope_id" in data:
        _require_scope_write(db, data.get("scope_type", r.scope_type), data.get("scope_id", r.scope_id), user)
    requested_vis = data.pop("visibility", "__keep__")
    for field, value in data.items():
        setattr(r, field, value)
    # Re-validate the audience against the (possibly new) home scope. If the
    # scope moved and no visibility was given, re-default to the new scope.
    if requested_vis != "__keep__":
        r.visibility = normalize_visibility(r.scope_type, requested_vis)
    else:
        r.visibility = normalize_visibility(r.scope_type, r.visibility)
    # Editing a rejected-but-still-public resource resubmits it for review (§3).
    if r.is_public and r.approval_status == "rejected":
        submit_for_review(db, r, user)
    _log_resource(db, user, r, "updated", meta=f"v{r.version}")
    db.commit()
    return resource_out(db, r, user)


@router.post("/resources/{resource_id}/move")
def move_resource(
    resource_id: str, body: ResourceMove,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Move a resource to a new home scope (pod ⇆ project ⇆ org). Requires write
    on the resource (author or org admin) AND membership at the destination. The
    audience re-defaults to the new scope unless `visibility` is supplied."""
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    if body.scope_type not in ("ORG", "PROJECT", "POD"):
        raise validation("scope_type must be ORG, PROJECT, or POD")
    if not body.scope_id:
        raise validation("scope_id (the destination pod/project/org id) is required")
    _require_scope_write(db, body.scope_type, body.scope_id, user)
    r.scope_type = body.scope_type
    r.scope_id = body.scope_id
    r.visibility = normalize_visibility(body.scope_type, body.visibility)
    _log_resource(db, user, r, "updated", meta="moved")
    db.commit()
    return resource_out(db, r, user)


@router.delete("/resources/{resource_id}")
def delete_resource(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    db.query(ResourceStar).filter(ResourceStar.resource_id == r.id).delete()
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---- scoped lists ----

def _list_params(
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    sort: str | None = Query(default=None),
):
    return {"q": q, "type_": type, "tag": tag, "sort": sort}


# These listings are audience-aware (Resource.visibility). Each fetches the
# candidate rows whose HOME is in the requested subtree, then filter_visible()
# drops anything the viewer can't read. "Elevated" pod/project resources
# (visibility widened to PROJECT/ORG) surface in the broader views so other
# pods / the whole org can find them.

def _org_subtree_ids(db: Session, org_id: str) -> tuple[list[str], list[str]]:
    project_ids = [p.id for p in db.query(Project.id).filter(Project.org_id == org_id)]
    pod_ids = (
        [p.id for p in db.query(Pod.id).filter(Pod.project_id.in_(project_ids))]
        if project_ids else []
    )
    return project_ids, pod_ids


def _org_view_rows(db: Session, org_id: str) -> list[Resource]:
    """Org-level shelf: org-scoped resources + anything below elevated to ORG."""
    project_ids, pod_ids = _org_subtree_ids(db, org_id)
    clause = (Resource.scope_type == "ORG") & (Resource.scope_id == org_id)
    if project_ids:
        clause = clause | ((Resource.scope_type == "PROJECT") & Resource.scope_id.in_(project_ids) & (Resource.visibility == "ORG"))
    if pod_ids:
        clause = clause | ((Resource.scope_type == "POD") & Resource.scope_id.in_(pod_ids) & (Resource.visibility == "ORG"))
    return db.query(Resource).filter(clause).all()


def _project_view_rows(db: Session, project_id: str) -> list[Resource]:
    """Project view: project-scoped resources + pod resources in this project
    elevated to PROJECT/ORG (so other pods and project members see them)."""
    pod_ids = [p.id for p in db.query(Pod.id).filter(Pod.project_id == project_id)]
    clause = (Resource.scope_type == "PROJECT") & (Resource.scope_id == project_id)
    if pod_ids:
        clause = clause | ((Resource.scope_type == "POD") & Resource.scope_id.in_(pod_ids) & Resource.visibility.in_(("PROJECT", "ORG")))
    return db.query(Resource).filter(clause).all()


@router.get("/orgs/{slug}/resources")
def org_resources(
    slug: str, params: dict = Depends(_list_params),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    rows = filter_visible(db, _org_view_rows(db, org.id), user)
    rows = search_rank(rows, params["q"], params["type_"], params["tag"], params["sort"])
    return resources_out(db, rows, user)


@router.get("/projects/{project_id}/resources")
def project_resources(
    project_id: str, params: dict = Depends(_list_params),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project = project_or_404(db, project_id)
    require_project_read(db, project, user)
    rows = filter_visible(db, _project_view_rows(db, project.id), user)
    rows = search_rank(rows, params["q"], params["type_"], params["tag"], params["sort"])
    return resources_out(db, rows, user)


@router.get("/pods/{pod_id}/resources")
def pod_resources(
    pod_id: str,
    scope: str = Query(default="all"),
    params: dict = Depends(_list_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inheritance union (BACKEND_SPEC §5): pod + project + org, filtered by ?scope=
    and by audience (visibility). The pod tab shows this pod's own resources; the
    project/org tabs show what's shared up to those levels."""
    pod = pod_or_404(db, pod_id)
    require_pod_read(db, pod, user)
    project = project_or_404(db, pod.project_id)
    scope = scope.lower()

    if scope == "pod":
        rows = db.query(Resource).filter(Resource.scope_type == "POD", Resource.scope_id == pod.id).all()
    elif scope == "project":
        rows = _project_view_rows(db, project.id)
    elif scope == "org":
        rows = _org_view_rows(db, project.org_id)
    else:  # all — union, deduped by id
        pod_own = db.query(Resource).filter(Resource.scope_type == "POD", Resource.scope_id == pod.id).all()
        merged = {r.id: r for r in pod_own}
        for r in _project_view_rows(db, project.id) + _org_view_rows(db, project.org_id):
            merged.setdefault(r.id, r)
        rows = list(merged.values())

    rows = filter_visible(db, rows, user)
    rows = search_rank(rows, params["q"], params["type_"], params["tag"], params["sort"])
    return resources_out(db, rows, user)


# ---- publish / star ----

def _notify_followers(db: Session, publisher: User, r: Resource) -> None:
    """Tell followers a new resource shipped to the marketplace — both the
    publisher's followers and (for org-scoped resources) the org's followers.
    Org members are excluded: they already get the membership notification.
    org_id may be None (PUBLIC-scoped) — hence Notification.org_id is nullable."""
    org = scope_org(db, r)
    recipients: set[str] = {
        f.follower_id for f in db.query(Follow).filter(Follow.publisher_id == publisher.id).all()
    }
    if org:
        recipients |= {
            f.follower_id for f in db.query(OrgFollow).filter(OrgFollow.org_id == org.id).all()
        }
        # Members were already notified by the membership fan-out — don't double up.
        member_ids = {m.user_id for m in db.query(OrgMember).filter(OrgMember.org_id == org.id).all()}
        recipients -= member_ids
    recipients.discard(publisher.id)
    for uid in recipients:
        db.add(
            Notification(
                user_id=uid,
                actor_id=publisher.id,
                org_id=org.id if org else None,
                scope_type="PUBLIC",
                scope_id=None,
                verb="published",
                object_type="resource",
                object_id=r.id,
                object_title=r.title,
                meta="from a publisher you follow",
            )
        )


@router.post("/resources/{resource_id}/publish")
def publish(
    resource_id: str, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), source: str = Depends(client_source),
):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    if not user.is_publisher:
        raise forbidden("Become a publisher first (POST /api/auth/become-publisher) to publish to the marketplace")
    # A publisher can always publish a resource they authored. The premium
    # "publishing" feature gates publishing *other people's* org resources
    # (an admin pushing a teammate's work), not your own.
    if r.author_id != user.id and not feature_enabled(db, scope_org(db, r), "publishing"):
        raise forbidden("Marketplace publishing is disabled for this organization")
    was_visible = is_publicly_visible(r)
    r.is_public = True
    # Submit to review (spec §3): org content → org admin, publisher content →
    # platform admin. Auto-approved when the publisher is already its reviewer.
    submit_for_review(db, r, user)
    _log_resource(db, user, r, "published", notify_scope="ORG", source=source)
    # Notify the author's followers only on the transition to publicly visible.
    if is_publicly_visible(r) and not was_visible:
        _notify_followers(db, db.get(User, r.author_id) or user, r)
    db.commit()
    return resource_out(db, r, user)


@router.delete("/resources/{resource_id}/publish")
def unpublish(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    r.is_public = False
    db.commit()
    return resource_out(db, r, user)


@router.post("/resources/{resource_id}/review")
def review_resource(
    resource_id: str, body: ResourceReviewIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Approve or reject a resource submitted for public listing (spec §3).
    Authority: platform admins for anything, org admins for their org's content."""
    r = resource_or_404(db, resource_id)
    if not can_review(db, r, user):
        raise forbidden("You don't have review authority over this resource")
    decision = (body.decision or "").strip().lower()
    if decision == "approve":
        approve(db, r, user)
    elif decision == "reject":
        reject(db, r, user, (body.note or "").strip() or None)
    else:
        raise validation('decision must be "approve" or "reject"')
    db.commit()
    return resource_out(db, r, user)


@router.post("/resources/{resource_id}/star")
def star(
    resource_id: str, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), source: str = Depends(client_source),
):
    r = resource_or_404(db, resource_id)
    require_resource_read(db, r, user)
    exists = (
        db.query(ResourceStar.id)
        .filter(ResourceStar.resource_id == r.id, ResourceStar.user_id == user.id)
        .first()
    )
    if not exists:
        db.add(ResourceStar(resource_id=r.id, user_id=user.id))
        r.stars_count += 1
        # Log to the activity timeline (previously "starred" was documented but
        # never recorded — spec §7 fix).
        _log_resource(db, user, r, "starred", source=source)
        db.commit()
    return resource_out(db, r, user)


@router.post("/resources/{resource_id}/use")
def track_use(
    resource_id: str, user: User = Depends(get_current_user),
    db: Session = Depends(get_db), source: str = Depends(client_source),
):
    """Record that a resource was used/installed (spec §7). The CLI (`use`/`pull`/
    `install`) and MCP (`use_resource`) call this so client usage shows on the
    activity timeline. Bumps installs_count when the client actually installs."""
    r = resource_or_404(db, resource_id)
    require_resource_read(db, r, user)
    if source in ("cli", "mcp"):
        r.installs_count += 1
    _log_resource(db, user, r, "used", source=source)
    db.commit()
    return {"ok": True, "installs_count": r.installs_count}


@router.delete("/resources/{resource_id}/star")
def unstar(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    deleted = (
        db.query(ResourceStar)
        .filter(ResourceStar.resource_id == r.id, ResourceStar.user_id == user.id)
        .delete()
    )
    if deleted:
        r.stars_count = max(0, r.stars_count - 1)
    db.commit()
    return resource_out(db, r, user)


# ---- pins (profile curation) ----

@router.post("/resources/{resource_id}/pin")
def pin(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pin a resource to your profile. You can pin anything you can see; the set
    is capped at MAX_PINS and ordered by pin time (position)."""
    r = resource_or_404(db, resource_id)
    require_resource_read(db, r, user)
    exists = (
        db.query(ResourcePin)
        .filter(ResourcePin.resource_id == r.id, ResourcePin.user_id == user.id)
        .first()
    )
    if not exists:
        count = db.query(ResourcePin).filter(ResourcePin.user_id == user.id).count()
        if count >= MAX_PINS:
            raise validation(f"You can pin up to {MAX_PINS} resources — unpin one first")
        db.add(ResourcePin(user_id=user.id, resource_id=r.id, position=count))
        db.commit()
    return resource_out(db, r, user)


@router.delete("/resources/{resource_id}/pin")
def unpin(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    db.query(ResourcePin).filter(
        ResourcePin.resource_id == r.id, ResourcePin.user_id == user.id
    ).delete()
    db.commit()
    return resource_out(db, r, user)


# ---- uploads (§6) ----

@router.post("/resources/upload")
def upload(body: UploadIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Presigned-PUT flow: returns upload_url (PUT the file there) + file_url
    (store on the resource). Prefers GCS (default cloud), then S3; without
    cloud config we return a deterministic placeholder so local dev works
    end-to-end."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", body.filename) or "package.skill"
    if not safe.endswith((".skill", ".zip")):
        raise validation("Only .skill / .zip packages are accepted")
    if body.size_bytes and body.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise validation(f"File exceeds the {settings.max_upload_mb} MB limit")

    key = f"packages/{user.username}/{safe}"
    if settings.gcs_bucket:
        from google.cloud import storage as gcs  # optional, only when GCS configured

        if settings.gcs_credentials_file:
            client = gcs.Client.from_service_account_json(
                settings.gcs_credentials_file, project=settings.gcs_project or None
            )
        else:
            client = gcs.Client(project=settings.gcs_project or None)
        blob = client.bucket(settings.gcs_bucket).blob(key)
        # v4 signed URLs require a service-account private key (set GCS_CREDENTIALS_FILE).
        upload_url = blob.generate_signed_url(
            version="v4", method="PUT", expiration=600, content_type=body.content_type
        )
        base = settings.gcs_public_base_url.rstrip("/") or f"https://storage.googleapis.com/{settings.gcs_bucket}"
        return {"upload_url": upload_url, "file_url": f"{base}/{key}"}

    if settings.s3_bucket:
        import boto3  # optional dependency, only needed when S3 is configured

        s3 = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": body.content_type},
            ExpiresIn=600,
        )
        base = settings.s3_public_base_url.rstrip("/") or f"https://{settings.s3_bucket}.s3.amazonaws.com"
        return {"upload_url": upload_url, "file_url": f"{base}/{key}"}

    # local-dev fallback — no real storage, but the contract holds
    return {"upload_url": None, "file_url": f"https://cdn.skillshare.think41.com/{key}"}


@router.post("/uploads")
async def upload_binary(
    file: UploadFile = File(...),
    kind: str = Form("file"),  # image | video | file (diagrams use image)
    user: User = Depends(get_current_user),
):
    """Direct multipart upload — stores the bytes via the configured storage
    backend (local disk by default, GCS/S3 in prod) and returns the public
    file_url to attach to a resource. Same contract regardless of backend."""
    if kind not in storage.ALLOWED_EXT:
        raise validation("kind must be image, video, or file")
    if not storage.ext_allowed(kind, file.filename or ""):
        allowed = ", ".join(sorted(storage.ALLOWED_EXT[kind]))
        raise validation(f"Unsupported file type for {kind}. Allowed: {allowed}")

    data = await file.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise validation(f"File exceeds the {settings.max_upload_mb} MB limit")
    if not data:
        raise validation("Empty file")

    file_url = storage.save_bytes(
        data, kind=kind, username=user.username, filename=file.filename or "upload", content_type=file.content_type
    )
    return {
        "file_url": file_url,
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(data),
    }


# ---- marketplace import (§8 #7) ----

@router.post("/resources/{resource_id}/import")
def import_resource(
    resource_id: str, body: ImportIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    source: str = Depends(client_source),
):
    src = db.get(Resource, resource_id)
    if not src or not is_publicly_visible(src):
        raise not_found("Public resource")
    org = org_by_slug(db, body.org_slug)
    require_org_member(db, org, user)
    if not feature_enabled(db, org, "marketplace"):
        raise forbidden("The public marketplace is disabled for this organization")

    # Don't let an org import a resource it already owns — that's how duplicates
    # of your own published resource appear. If the source is already homed in
    # this org, there's nothing to add.
    home = scope_org(db, src)
    if home and home.id == org.id:
        raise validation("This resource already belongs to your organization")

    # Idempotent re-import: if this org already imported this source, return the
    # existing copy instead of making another duplicate.
    marker = f"marketplace:{src.id}"
    existing = (
        db.query(Resource)
        .filter(
            Resource.scope_type == "ORG",
            Resource.scope_id == org.id,
            Resource.source_fingerprint == marker,
        )
        .first()
    )
    if existing:
        return resource_out(db, existing, user)

    copy = Resource(
        type=src.type,
        title=src.title,
        description=src.description,
        content_md=src.content_md,
        server_url=src.server_url,
        config_json=src.config_json,
        file_url=src.file_url,
        version=src.version,
        tags=list(src.tags or []),
        attachments=list(src.attachments or []),
        scope_type="ORG",
        scope_id=org.id,
        author_id=user.id,
        is_public=False,
        # Link the copy back to its marketplace source so re-imports dedupe.
        source_fingerprint=marker,
    )
    db.add(copy)
    src.installs_count += 1
    db.flush()
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="created",
        object_type="resource", object_id=copy.id, object_title=copy.title,
        meta="imported from marketplace", source=source,
    )
    # Also record the install against the source resource so its author sees the
    # adoption on their activity timeline (spec §7).
    _log_resource(db, user, copy, "installed", meta=f"imported “{src.title}”", source=source)
    db.commit()
    return resource_out(db, copy, user)
