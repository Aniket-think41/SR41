"""Scope membership management (§4.5).

Id-addressed (not nested under org-slug) so the dashboard, CLI, and MCP server
all drive membership through one set of endpoints. Three things happen here that
the older nested add-routes didn't do:

  • add by email — an unknown email auto-provisions a brand-new account with a
    temporary password (must_change_password), same onboarding as an org invite;
  • cascade up — adding at a deeper level ensures the shallower levels exist,
    always as MEMBER (a pod ADMIN is still just an org/project MEMBER);
  • role management — PATCH to promote/demote (ADMIN | MEMBER) and DELETE to
    remove, guarded so only a scope admin (or org admin) can manage people.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..email import send_scope_add_email
from ..errors import not_found, validation
from ..models import Organization, PodMember, Project, ProjectMember, User
from ..permissions import (
    ensure_org_member,
    ensure_pod_member,
    ensure_project_member,
    normalize_role,
    pod_or_404,
    project_or_404,
    require_pod_admin,
    require_pod_read,
    require_project_admin,
    require_project_read,
    resolve_or_provision_user,
)
from ..schemas import AddMemberIn, MemberRolePatch
from ..security import get_current_user
from ..serialize import log_activity, member_out

router = APIRouter(prefix="/api", tags=["members"])


def _org_of_project(db: Session, project: Project) -> Organization | None:
    return db.get(Organization, project.org_id)


def _notify_added(
    *, target: User, temp_password: str | None, org: Organization | None,
    scope_label: str, scope_name: str, actor: User, role: str,
) -> None:
    """Best-effort email: always tells an existing user they were added; also
    carries sign-in credentials when the account was just provisioned."""
    if not org:
        return
    send_scope_add_email(
        to_email=target.email,
        org_name=org.name,
        scope_label=scope_label,
        scope_name=scope_name,
        inviter_name=actor.display_name,
        role=role,
        username=target.email if temp_password else None,
        temp_password=temp_password,
    )


# --- projects --------------------------------------------------------------

@router.get("/projects/{project_id}/members")
def list_project_members(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = project_or_404(db, project_id)
    require_project_read(db, project, user)
    rows = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return [member_out(m, "project_id") for m in rows]


@router.post("/projects/{project_id}/members")
def add_project_member(
    project_id: str, body: AddMemberIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project = project_or_404(db, project_id)
    require_project_admin(db, project, user)
    target, temp_password = resolve_or_provision_user(db, user_id=body.user_id, email=body.email)
    role = normalize_role(body.role, admin_aliases=("LEAD",))
    # Cascade: project membership implies org membership (as MEMBER).
    ensure_org_member(db, project.org_id, target.id)
    m = ensure_project_member(db, project.id, target.id, role=role)
    m.role = role  # honour an explicit role even if the row already existed
    org = _org_of_project(db, project)
    log_activity(
        db, user_id=user.id, org_id=project.org_id, verb="added",
        object_type="member", object_id=target.id, object_title=target.display_name,
    )
    db.commit()
    _notify_added(
        target=target, temp_password=temp_password, org=org,
        scope_label="project", scope_name=project.name, actor=user, role=role,
    )
    return member_out(m, "project_id")


@router.patch("/projects/{project_id}/members/{user_id}")
def set_project_member_role(
    project_id: str, user_id: str, body: MemberRolePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project = project_or_404(db, project_id)
    require_project_admin(db, project, user)
    m = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )
    if not m:
        raise not_found("Member")
    m.role = normalize_role(body.role, admin_aliases=("LEAD",))
    db.commit()
    return member_out(m, "project_id")


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: str, user_id: str,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project = project_or_404(db, project_id)
    require_project_admin(db, project, user)
    # Removing from a project also removes the user from that project's pods.
    _cascade_remove_project(db, project_id, user_id)
    db.commit()
    return {"ok": True}


def _cascade_remove_project(db: Session, project_id: str, user_id: str) -> None:
    from ..models import Pod

    pod_ids = [p.id for p in db.query(Pod).filter(Pod.project_id == project_id).all()]
    if pod_ids:
        db.query(PodMember).filter(
            PodMember.pod_id.in_(pod_ids), PodMember.user_id == user_id
        ).delete(synchronize_session=False)
    db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
    ).delete(synchronize_session=False)


# --- pods ------------------------------------------------------------------

@router.get("/pods/{pod_id}/members")
def list_pod_members(pod_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pod = pod_or_404(db, pod_id)
    require_pod_read(db, pod, user)
    return [member_out(m, "pod_id") for m in db.query(PodMember).filter(PodMember.pod_id == pod_id).all()]


@router.post("/pods/{pod_id}/members")
def add_pod_member(
    pod_id: str, body: AddMemberIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_admin(db, pod, user)
    project = project_or_404(db, pod.project_id)
    target, temp_password = resolve_or_provision_user(db, user_id=body.user_id, email=body.email)
    role = normalize_role(body.role, admin_aliases=("OWNER",))
    # Cascade: pod ⇒ project ⇒ org, each as MEMBER (only the pod row gets `role`).
    ensure_org_member(db, project.org_id, target.id)
    ensure_project_member(db, project.id, target.id)
    m = ensure_pod_member(db, pod.id, target.id, role=role)
    m.role = role
    org = _org_of_project(db, project)
    log_activity(
        db, user_id=user.id, org_id=project.org_id, verb="added",
        object_type="member", object_id=target.id, object_title=target.display_name,
    )
    db.commit()
    _notify_added(
        target=target, temp_password=temp_password, org=org,
        scope_label="pod", scope_name=pod.name, actor=user, role=role,
    )
    return member_out(m, "pod_id")


@router.patch("/pods/{pod_id}/members/{user_id}")
def set_pod_member_role(
    pod_id: str, user_id: str, body: MemberRolePatch,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_admin(db, pod, user)
    m = db.query(PodMember).filter(PodMember.pod_id == pod_id, PodMember.user_id == user_id).first()
    if not m:
        raise not_found("Member")
    m.role = normalize_role(body.role, admin_aliases=("OWNER",))
    db.commit()
    return member_out(m, "pod_id")


@router.delete("/pods/{pod_id}/members/{user_id}")
def remove_pod_member(
    pod_id: str, user_id: str,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    pod = pod_or_404(db, pod_id)
    require_pod_admin(db, pod, user)
    db.query(PodMember).filter(PodMember.pod_id == pod_id, PodMember.user_id == user_id).delete()
    db.commit()
    return {"ok": True}
