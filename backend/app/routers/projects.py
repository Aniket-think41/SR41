"""3.3 Projects — nested under the org slug."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import validation
from ..models import Pod, PodMember, Project, ProjectMember, Resource, User
from ..permissions import (
    org_by_slug,
    project_or_404,
    require_org_member,
    require_project_access,
)
from ..schemas import AddMemberIn, ProjectCreate, ProjectPatch
from ..security import get_current_user
from ..serialize import log_activity, member_out, project_out
from ..models import ResourceStar

router = APIRouter(prefix="/api/orgs/{slug}/projects", tags=["projects"])


@router.get("")
def list_projects(slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    return [project_out(db, p) for p in db.query(Project).filter(Project.org_id == org.id).all()]


@router.post("")
def create_project(slug: str, body: ProjectCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    if not body.name.strip():
        raise validation("Project name is required")
    project = Project(
        org_id=org.id, name=body.name.strip(), description=body.description,
        tags=body.tags, created_by=user.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="LEAD"))
    log_activity(
        db, user_id=user.id, org_id=org.id, verb="created",
        object_type="project", object_id=project.id, object_title=project.name,
    )
    db.commit()
    return project_out(db, project)


@router.get("/{project_id}")
def get_project(slug: str, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    return project_out(db, project_or_404(db, project_id))


@router.patch("/{project_id}")
def update_project(
    slug: str, project_id: str, body: ProjectPatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org_by_slug(db, slug)
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.tags is not None:
        project.tags = body.tags
    if body.visibility is not None:
        project.visibility = body.visibility
    db.commit()
    return project_out(db, project)


@router.delete("/{project_id}")
def delete_project(slug: str, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org_by_slug(db, slug)
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)

    pod_ids = [p.id for p in db.query(Pod).filter(Pod.project_id == project.id).all()]
    # cascade: pod members, pod/project-scoped resources (+ their stars), pods, members
    doomed = db.query(Resource).filter(
        ((Resource.scope_type == "PROJECT") & (Resource.scope_id == project.id))
        | ((Resource.scope_type == "POD") & Resource.scope_id.in_(pod_ids or [""]))
    )
    doomed_ids = [r.id for r in doomed.all()]
    if doomed_ids:
        db.query(ResourceStar).filter(ResourceStar.resource_id.in_(doomed_ids)).delete(synchronize_session=False)
        db.query(Resource).filter(Resource.id.in_(doomed_ids)).delete(synchronize_session=False)
    if pod_ids:
        db.query(PodMember).filter(PodMember.pod_id.in_(pod_ids)).delete(synchronize_session=False)
        db.query(Pod).filter(Pod.id.in_(pod_ids)).delete(synchronize_session=False)
    db.query(ProjectMember).filter(ProjectMember.project_id == project.id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/members")
def project_members(slug: str, project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = org_by_slug(db, slug)
    require_org_member(db, org, user)
    project_or_404(db, project_id)
    rows = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return [member_out(m, "project_id") for m in rows]


@router.post("/{project_id}/members")
def add_project_member(
    slug: str, project_id: str, body: AddMemberIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    org_by_slug(db, slug)
    project = project_or_404(db, project_id)
    require_project_access(db, project, user)
    m = ProjectMember(
        project_id=project_id, user_id=body.user_id,
        role=body.role if body.role in ("LEAD", "MEMBER") else "MEMBER",
    )
    db.add(m)
    db.commit()
    return member_out(m, "project_id")
