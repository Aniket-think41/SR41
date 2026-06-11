"""3.4 Pods — nested under the project id."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import validation
from ..models import Pod, PodMember, Resource, ResourceStar, User
from ..permissions import pod_or_404, project_or_404, require_pod_access, require_project_access
from ..schemas import AddMemberIn, PodCreate, PodPatch
from ..security import get_current_user
from ..serialize import log_activity, member_out, pod_out

router = APIRouter(prefix="/api/projects/{project_id}/pods", tags=["pods"])


@router.get("")
def list_pods(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)
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
    require_pod_access(db, pod, user)
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
    require_pod_access(db, pod, user)
    return [member_out(m, "pod_id") for m in db.query(PodMember).filter(PodMember.pod_id == pod_id).all()]


@router.post("/{pod_id}/members")
def add_pod_member(
    project_id: str, pod_id: str, body: AddMemberIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_access(db, pod, user)
    m = PodMember(
        pod_id=pod_id, user_id=body.user_id,
        role=body.role if body.role in ("OWNER", "MEMBER") else "MEMBER",
    )
    db.add(m)
    db.commit()
    return member_out(m, "pod_id")
