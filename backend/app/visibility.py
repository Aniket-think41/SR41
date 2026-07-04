"""Resource visibility (audience) — who can READ a resource, independent of the
scope it lives in.

Levels: POD (only the owning pod's members) < PROJECT (all project members) <
ORG (all org members). A resource can be *elevated* above its home scope so other
pods / the whole org can see it, but never narrowed below it (an org-scoped
resource is inherently org-wide). See models.Resource.visibility.

This module centralizes three things so the read gate and every listing agree:
  • default/validate a visibility for a given home scope,
  • decide whether one user can read one resource (`resource_visible`),
  • filter a batch of rows for a viewer efficiently (`filter_visible`).
"""

from sqlalchemy.orm import Session

from .models import OrgMember, Pod, PodMember, Project, ProjectMember, Resource, User

LEVELS = ("POD", "PROJECT", "ORG")

# Allowed audiences per home scope (can't be narrower than the home scope).
_ALLOWED = {
    "POD": ("POD", "PROJECT", "ORG"),
    "PROJECT": ("PROJECT", "ORG"),
    "ORG": ("ORG",),
    "PUBLIC": ("ORG",),
}


def default_visibility(scope_type: str) -> str:
    """Narrowest sensible audience for a home scope (the create-time default)."""
    return {"POD": "POD", "PROJECT": "PROJECT", "ORG": "ORG"}.get(scope_type, "ORG")


def normalize_visibility(scope_type: str, vis: str | None) -> str:
    """Coerce a requested visibility to one valid for this home scope; falls back
    to the scope default when missing or too narrow."""
    v = (vis or "").strip().upper()
    return v if v in _ALLOWED.get(scope_type, ("ORG",)) else default_visibility(scope_type)


# --- home resolution -------------------------------------------------------

def home_ids(db: Session, r: Resource) -> tuple[str | None, str | None, str | None]:
    """(org_id, project_id, pod_id) for a resource's home scope; any may be None."""
    if r.scope_type == "ORG":
        return r.scope_id, None, None
    if r.scope_type == "PROJECT":
        p = db.get(Project, r.scope_id)
        return (p.org_id if p else None), r.scope_id, None
    if r.scope_type == "POD":
        pod = db.get(Pod, r.scope_id)
        proj = db.get(Project, pod.project_id) if pod else None
        return (proj.org_id if proj else None), (pod.project_id if pod else None), r.scope_id
    return None, None, None


# --- viewer membership sets ------------------------------------------------

def viewer_sets(db: Session, user: User) -> dict:
    """The scopes a user belongs to (+ where they're an admin/lead), fetched once
    so a batch of visibility checks costs a fixed number of queries."""
    def ids(model, col, **extra):
        q = db.query(col).filter(model.user_id == user.id)
        for k, v in extra.items():
            q = q.filter(getattr(model, k) == v) if not isinstance(v, tuple) else q.filter(getattr(model, k).in_(v))
        return {row[0] for row in q}

    return {
        "orgs": ids(OrgMember, OrgMember.org_id),
        "org_admins": ids(OrgMember, OrgMember.org_id, role="ADMIN"),
        "projects": ids(ProjectMember, ProjectMember.project_id),
        "project_leads": ids(ProjectMember, ProjectMember.project_id, role=("ADMIN", "LEAD")),
        "pods": ids(PodMember, PodMember.pod_id),
    }


def _decide(vis: str, org_id, project_id, pod_id, sets: dict) -> bool:
    if vis == "ORG":
        return org_id in sets["orgs"]
    if vis == "PROJECT":
        return project_id in sets["projects"] or org_id in sets["org_admins"]
    if vis == "POD":
        return pod_id in sets["pods"] or project_id in sets["project_leads"] or org_id in sets["org_admins"]
    return False


def resource_visible(db: Session, r: Resource, user: User) -> bool:
    """Can this user read this resource? Public resources and the author are
    always visible; otherwise membership must satisfy the resource's audience."""
    if r.is_public or r.scope_type == "PUBLIC":
        return True
    if r.author_id == user.id:
        return True
    vis = normalize_visibility(r.scope_type, r.visibility)
    org_id, project_id, pod_id = home_ids(db, r)
    return _decide(vis, org_id, project_id, pod_id, viewer_sets(db, user))


def filter_visible(db: Session, rows: list[Resource], user: User) -> list[Resource]:
    """Filter a batch of rows to those the user may read — resolves home ids in
    bulk and checks membership once (no per-row query storm)."""
    if not rows:
        return []
    sets = viewer_sets(db, user)
    # Bulk-load the pod→project and project→org maps needed to resolve homes.
    pod_ids = {r.scope_id for r in rows if r.scope_type == "POD" and r.scope_id}
    pods = {p.id: p for p in db.query(Pod).filter(Pod.id.in_(pod_ids))} if pod_ids else {}
    project_ids = {r.scope_id for r in rows if r.scope_type == "PROJECT" and r.scope_id}
    project_ids |= {p.project_id for p in pods.values()}
    projects = {p.id: p for p in db.query(Project).filter(Project.id.in_(project_ids))} if project_ids else {}

    out = []
    for r in rows:
        if r.is_public or r.scope_type == "PUBLIC" or r.author_id == user.id:
            out.append(r)
            continue
        if r.scope_type == "ORG":
            org_id, project_id, pod_id = r.scope_id, None, None
        elif r.scope_type == "PROJECT":
            proj = projects.get(r.scope_id)
            org_id, project_id, pod_id = (proj.org_id if proj else None), r.scope_id, None
        elif r.scope_type == "POD":
            pod = pods.get(r.scope_id)
            proj = projects.get(pod.project_id) if pod else None
            org_id, project_id, pod_id = (proj.org_id if proj else None), (pod.project_id if pod else None), r.scope_id
        else:
            continue
        if _decide(normalize_visibility(r.scope_type, r.visibility), org_id, project_id, pod_id, sets):
            out.append(r)
    return out
