"""3.4 Pods — nested under the project id."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import not_found, validation
from ..models import Pod, PodMember, PodService, Resource, ResourceStar, User
from ..permissions import (
    ensure_org_member,
    ensure_pod_member,
    ensure_project_member,
    pod_or_404,
    project_or_404,
    require_pod_access,
    require_pod_read,
    require_project_access,
    require_project_read,
    resolve_user,
)
from ..schemas import AddMemberIn, PodCreate, PodPatch, PodServiceCreate, PodServicePatch
from ..security import get_current_user
from ..serialize import log_activity, member_out, pod_out, pod_service_out

router = APIRouter(prefix="/api/projects/{project_id}/pods", tags=["pods"])


@router.get("")
def list_pods(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = project_or_404(db, project_id)
    require_project_read(db, project, user)
    return [pod_out(db, p) for p in db.query(Pod).filter(Pod.project_id == project_id).all()]


@router.post("")
def create_pod(project_id: str, body: PodCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)
    if not body.name.strip():
        raise validation("Pod name is required")
    pod = Pod(
        project_id=project_id, name=body.name.strip(),
        description=body.description, purpose_tag=body.purpose_tag, created_by=user.id,
    )
    db.add(pod)
    db.flush()
    db.add(PodMember(pod_id=pod.id, user_id=user.id, role="OWNER"))
    log_activity(
        db, user_id=user.id, org_id=project.org_id, verb="created",
        object_type="pod", object_id=pod.id, object_title=pod.name,
    )
    db.commit()
    return pod_out(db, pod)


@router.get("/{pod_id}")
def get_pod(project_id: str, pod_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pod = pod_or_404(db, pod_id)
    require_pod_read(db, pod, user)
    return pod_out(db, pod)


@router.patch("/{pod_id}")
def update_pod(
    project_id: str, pod_id: str, body: PodPatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    if body.name is not None:
        pod.name = body.name
    if body.description is not None:
        pod.description = body.description
    if body.purpose_tag is not None:
        pod.purpose_tag = body.purpose_tag
    db.commit()
    return pod_out(db, pod)


@router.delete("/{pod_id}")
def delete_pod(project_id: str, pod_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    doomed_ids = [
        r.id for r in db.query(Resource).filter(Resource.scope_type == "POD", Resource.scope_id == pod_id).all()
    ]
    if doomed_ids:
        db.query(ResourceStar).filter(ResourceStar.resource_id.in_(doomed_ids)).delete(synchronize_session=False)
        db.query(Resource).filter(Resource.id.in_(doomed_ids)).delete(synchronize_session=False)
    db.query(PodMember).filter(PodMember.pod_id == pod_id).delete(synchronize_session=False)
    db.delete(pod)
    db.commit()
    return {"ok": True}


@router.get("/{pod_id}/members")
def pod_members(project_id: str, pod_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pod = pod_or_404(db, pod_id)
    require_pod_read(db, pod, user)
    return [member_out(m, "pod_id") for m in db.query(PodMember).filter(PodMember.pod_id == pod_id).all()]


@router.post("/{pod_id}/members")
def add_pod_member(
    project_id: str, pod_id: str, body: AddMemberIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    project = project_or_404(db, pod.project_id)
    target = resolve_user(db, user_id=body.user_id, email=body.email)
    role = body.role if body.role in ("OWNER", "MEMBER") else "MEMBER"
    # Cascade: pod ⇒ project ⇒ org (each created only if missing).
    ensure_org_member(db, project.org_id, target.id)
    ensure_project_member(db, project.id, target.id)
    m = ensure_pod_member(db, pod.id, target.id, role=role)
    db.commit()
    return member_out(m, "pod_id")


# ---- pod service registry (service management) ----
# A pod's operational surface: the MCP servers, deployed APIs, webhooks and DBs
# it runs or relies on. Viewing follows the org-wide read rule; creating/editing
# requires pod write access (pod member, project lead, or org admin).


def _service_or_404(db: Session, pod_id: str, service_id: str) -> PodService:
    s = db.get(PodService, service_id)
    if not s or s.pod_id != pod_id:
        raise not_found("Service")
    return s


@router.get("/{pod_id}/services")
def list_pod_services(project_id: str, pod_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pod = pod_or_404(db, pod_id)
    require_pod_read(db, pod, user)
    rows = db.query(PodService).filter(PodService.pod_id == pod_id).order_by(PodService.created_at).all()
    return [pod_service_out(s) for s in rows]


@router.post("/{pod_id}/services")
def create_pod_service(
    project_id: str, pod_id: str, body: PodServiceCreate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    if not body.name.strip():
        raise validation("Service name is required")
    s = PodService(
        pod_id=pod_id,
        name=body.name.strip(),
        kind=body.kind,
        description=body.description,
        endpoint_url=body.endpoint_url,
        health_url=body.health_url,
        config=body.config or {},
        secret_ref=body.secret_ref,
        status=body.status,
        created_by=user.id,
    )
    db.add(s)
    db.flush()
    project = project_or_404(db, pod.project_id)
    log_activity(
        db, user_id=user.id, org_id=project.org_id,
        verb="created", object_type="service", object_id=s.id, object_title=s.name,
    )
    db.commit()
    return pod_service_out(s)


@router.patch("/{pod_id}/services/{service_id}")
def update_pod_service(
    project_id: str, pod_id: str, service_id: str, body: PodServicePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    s = _service_or_404(db, pod_id, service_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    return pod_service_out(s)


@router.delete("/{pod_id}/services/{service_id}")
def delete_pod_service(
    project_id: str, pod_id: str, service_id: str,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    s = _service_or_404(db, pod_id, service_id)
    db.delete(s)
    db.commit()
    return {"ok": True}
