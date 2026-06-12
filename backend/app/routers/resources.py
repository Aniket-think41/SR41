"""3.5 Resources — CRUD, scoped lists, inheritance union (§5), publish/star,
uploads (§6), and marketplace import."""

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..errors import forbidden, not_found, validation
from ..features import feature_enabled
from ..models import Organization, Pod, Project, Resource, ResourceStar, User
from ..permissions import (
    org_by_slug,
    pod_or_404,
    project_or_404,
    require_org_member,
    require_pod_access,
    require_project_access,
    require_resource_read,
    require_resource_write,
    resource_or_404,
    scope_org,
)
from ..schemas import ImportIn, ResourceCreate, ResourcePatch, UploadIn
from ..security import get_current_user
from ..serialize import filter_resources, log_activity, resource_out, sort_resources

router = APIRouter(prefix="/api", tags=["resources"])
settings = get_settings()

VALID_TYPES = {"SKILL", "MCP", "NOTE"}
VALID_SCOPES = {"ORG", "PROJECT", "POD", "PUBLIC"}


def _require_scope_write(db: Session, scope_type: str, scope_id: str | None, user: User) -> None:
    """Creating into a scope requires membership at that level (§4.2)."""
    if scope_type == "ORG":
        org = db.get(Organization, scope_id)
        if not org:
            raise not_found("Organization")
        require_org_member(db, org, user)
    elif scope_type == "PROJECT":
        require_project_access(db, project_or_404(db, scope_id or ""), user)
    elif scope_type == "POD":
        require_pod_access(db, pod_or_404(db, scope_id or ""), user)


def _log_resource(db: Session, user: User, r: Resource, verb: str, meta: str | None = None) -> None:
    org = scope_org(db, r)
    if org:
        log_activity(
            db, user_id=user.id, org_id=org.id, verb=verb,
            object_type="resource", object_id=r.id, object_title=r.title, meta=meta,
        )


@router.post("/resources")
def create_resource(body: ResourceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.type not in VALID_TYPES:
        raise validation("type must be SKILL, MCP, or NOTE")
    if body.scope_type not in VALID_SCOPES:
        raise validation("scope_type must be ORG, PROJECT, POD, or PUBLIC")
    if not body.title.strip():
        raise validation("Title is required")
    _require_scope_write(db, body.scope_type, body.scope_id, user)
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
        scope_id=body.scope_id,
        author_id=user.id,
    )
    db.add(r)
    db.flush()
    _log_resource(db, user, r, "created")
    db.commit()
    return resource_out(db, r, user)


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
    for field, value in data.items():
        setattr(r, field, value)
    _log_resource(db, user, r, "updated", meta=f"v{r.version}")
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


@router.get("/orgs/{slug}/resources")
def org_resources(
    slug: str, params: dict = Depends(_list_params),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    rows = db.query(Resource).filter(Resource.scope_type == "ORG", Resource.scope_id == org.id).all()
    rows = sort_resources(filter_resources(rows, params["q"], params["type_"], params["tag"]), params["sort"])
    return [resource_out(db, r, user) for r in rows]


@router.get("/projects/{project_id}/resources")
def project_resources(
    project_id: str, params: dict = Depends(_list_params),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)
    rows = db.query(Resource).filter(Resource.scope_type == "PROJECT", Resource.scope_id == project.id).all()
    rows = sort_resources(filter_resources(rows, params["q"], params["type_"], params["tag"]), params["sort"])
    return [resource_out(db, r, user) for r in rows]


@router.get("/pods/{pod_id}/resources")
def pod_resources(
    pod_id: str,
    scope: str = Query(default="all"),
    params: dict = Depends(_list_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inheritance union (BACKEND_SPEC §5): pod + project + org, filtered by ?scope=."""
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    project = project_or_404(db, pod.project_id)
    scope = scope.lower()

    conditions = {
        "pod": (Resource.scope_type == "POD") & (Resource.scope_id == pod.id),
        "project": (Resource.scope_type == "PROJECT") & (Resource.scope_id == project.id),
        "org": (Resource.scope_type == "ORG") & (Resource.scope_id == project.org_id),
    }
    if scope in conditions:
        clause = conditions[scope]
    else:  # all
        clause = conditions["pod"] | conditions["project"] | conditions["org"]
    rows = db.query(Resource).filter(clause).all()
    rows = sort_resources(filter_resources(rows, params["q"], params["type_"], params["tag"]), params["sort"])
    return [resource_out(db, r, user) for r in rows]


# ---- publish / star ----

@router.post("/resources/{resource_id}/publish")
def publish(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    if not user.is_publisher:
        raise forbidden("Enable publisher mode in your profile to publish to the marketplace")
    if not feature_enabled(db, scope_org(db, r), "publishing"):
        raise forbidden("Marketplace publishing is disabled for this organization")
    r.is_public = True
    _log_resource(db, user, r, "published")
    db.commit()
    return resource_out(db, r, user)


@router.delete("/resources/{resource_id}/publish")
def unpublish(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = resource_or_404(db, resource_id)
    require_resource_write(db, r, user)
    r.is_public = False
    db.commit()
    return resource_out(db, r, user)


@router.post("/resources/{resource_id}/star")
def star(resource_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
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
        db.commit()
    return resource_out(db, r, user)


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


# ---- uploads (§6) ----

@router.post("/resources/upload")
def upload(body: UploadIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Presigned-PUT flow: returns upload_url (PUT the file there) + file_url
    (store on the resource). Without S3 config we return a deterministic
    placeholder so local dev works end-to-end."""
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", body.filename) or "package.skill"
    if not safe.endswith((".skill", ".zip")):
        raise validation("Only .skill / .zip packages are accepted")
    if body.size_bytes and body.size_bytes > settings.max_upload_mb * 1024 * 1024:
        raise validation(f"File exceeds the {settings.max_upload_mb} MB limit")

    key = f"packages/{user.username}/{safe}"
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


# ---- marketplace import (§8 #7) ----

@router.post("/resources/{resource_id}/import")
def import_resource(
    resource_id: str, body: ImportIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    src = db.get(Resource, resource_id)
    if not src or not src.is_public:
        raise not_found("Public resource")
    org = org_by_slug(db, body.org_slug)
    require_org_member(db, org, user)
    if not feature_enabled(db, org, "marketplace"):
        raise forbidden("The public marketplace is disabled for this organization")
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
    )
    db.add(copy)
    src.installs_count += 1
    db.flush()
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="created",
        object_type="resource", object_id=copy.id, object_title=copy.title,
        meta="imported from marketplace",
    )
    db.commit()
    return resource_out(db, copy, user)
