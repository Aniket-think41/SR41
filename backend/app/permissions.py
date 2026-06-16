"""
Scope-based access checks (BACKEND_SPEC §4.2).
"""

from sqlalchemy.orm import Session

from .errors import forbidden, not_found
from .models import Organization, OrgMember, Pod, PodMember, Project, ProjectMember, Resource, User


def require_admin(user: User) -> User:
    """Platform admin (User.is_admin) — manages marketing content + publishers.
    Distinct from org ADMIN, which is scoped to a single organization."""
    if not user.is_admin:
        raise forbidden("Platform admin access required")
    return user


def org_by_slug(db: Session, slug: str) -> Organization:
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if not org:
        raise not_found(f'Organization "{slug}"')
    return org


def org_membership(db: Session, org: Organization, user: User) -> OrgMember | None:
    return db.query(OrgMember).filter(OrgMember.org_id == org.id, OrgMember.user_id == user.id).first()


def require_org_member(db: Session, org: Organization, user: User) -> OrgMember:
    m = org_membership(db, org, user)
    if not m:
        raise forbidden("You are not a member of this organization")
    return m


def require_org_admin(db: Session, org: Organization, user: User) -> OrgMember:
    m = require_org_member(db, org, user)
    if m.role != "ADMIN":
        raise forbidden("Only org admins can do this")
    return m


def project_or_404(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise not_found("Project")
    return p


def pod_or_404(db: Session, pod_id: str) -> Pod:
    p = db.get(Pod, pod_id)
    if not p:
        raise not_found("Pod")
    return p


def resource_or_404(db: Session, resource_id: str) -> Resource:
    r = db.get(Resource, resource_id)
    if not r:
        raise not_found("Resource")
    return r


def require_project_access(db: Session, project: Project, user: User) -> None:
    """Project member OR org admin (§4.2)."""
    org = db.get(Organization, project.org_id)
    m = org_membership(db, org, user) if org else None
    if not m:
        raise forbidden("You are not a member of this organization")
    if m.role == "ADMIN":
        return
    is_member = (
        db.query(ProjectMember.id)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .first()
    )
    if not is_member:
        raise forbidden("You are not a member of this project")


def require_pod_access(db: Session, pod: Pod, user: User) -> None:
    """Pod member OR project lead OR org admin (§4.2)."""
    project = project_or_404(db, pod.project_id)
    org = db.get(Organization, project.org_id)
    m = org_membership(db, org, user) if org else None
    if not m:
        raise forbidden("You are not a member of this organization")
    if m.role == "ADMIN":
        return
    pod_member = (
        db.query(PodMember.id).filter(PodMember.pod_id == pod.id, PodMember.user_id == user.id).first()
    )
    if pod_member:
        return
    lead = (
        db.query(ProjectMember.id)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.role == "LEAD",
        )
        .first()
    )
    if not lead:
        raise forbidden("You are not a member of this pod")


def scope_org(db: Session, resource: Resource) -> Organization | None:
    """Resolve the org a resource ultimately lives in (None for PUBLIC scope)."""
    if resource.scope_type == "ORG":
        return db.get(Organization, resource.scope_id)
    if resource.scope_type == "PROJECT":
        project = db.get(Project, resource.scope_id)
        return db.get(Organization, project.org_id) if project else None
    if resource.scope_type == "POD":
        pod = db.get(Pod, resource.scope_id)
        if pod:
            project = db.get(Project, pod.project_id)
            return db.get(Organization, project.org_id) if project else None
    return None


def require_resource_read(db: Session, resource: Resource, user: User) -> None:
    if resource.is_public or resource.scope_type == "PUBLIC":
        return
    if resource.scope_type == "ORG":
        org = db.get(Organization, resource.scope_id)
        if org:
            require_org_member(db, org, user)
        return
    if resource.scope_type == "PROJECT":
        project = project_or_404(db, resource.scope_id)
        require_project_access(db, project, user)
        return
    if resource.scope_type == "POD":
        pod = pod_or_404(db, resource.scope_id)
        require_pod_access(db, pod, user)


def require_resource_write(db: Session, resource: Resource, user: User) -> None:
    """Author or admin of the owning org."""
    if resource.author_id == user.id:
        return
    org = scope_org(db, resource)
    if org:
        m = org_membership(db, org, user)
        if m and m.role == "ADMIN":
            return
    raise forbidden("Only the author or an org admin can modify this resource")
