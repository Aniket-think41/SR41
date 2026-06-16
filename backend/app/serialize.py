"""
Wire-format serializers — produce exactly the JSON shapes the client types
(client/src/lib/types.ts) expect, including the enrichment fields
scope_label / author / starred_by_me and the denormalized counts.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    Activity,
    BlogPost,
    ChangelogEntry,
    ContentPage,
    Invitation,
    Notification,
    Organization,
    OrgMember,
    Pod,
    PodMember,
    Project,
    ProjectMember,
    Resource,
    ResourceStar,
    User,
)


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "display_name": u.display_name,
        "avatar_url": u.avatar_url,
        "bio": u.bio,
        "location": u.location,
        "website": u.website,
        "is_publisher": u.is_publisher,
        "verified": u.verified,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
    }


def org_out(o: Organization, my_role: str | None = None) -> dict:
    out = {
        "id": o.id,
        "name": o.name,
        "slug": o.slug,
        "logo_url": o.logo_url,
        "description": o.description,
        "is_public": o.is_public,
        "owner_id": o.owner_id,
        "plan": o.plan,
        "terminology": o.terminology,
        "created_at": o.created_at,
    }
    if my_role is not None:
        out["my_role"] = my_role
    return out


def resource_out(db: Session, r: Resource, me: User | None) -> dict:
    starred = False
    if me:
        starred = (
            db.query(ResourceStar.id)
            .filter(ResourceStar.resource_id == r.id, ResourceStar.user_id == me.id)
            .first()
            is not None
        )
    return {
        "id": r.id,
        "type": r.type,
        "title": r.title,
        "description": r.description,
        "content_md": r.content_md,
        "server_url": r.server_url,
        "config_json": r.config_json,
        "file_url": r.file_url,
        "version": r.version,
        "tags": r.tags or [],
        "attachments": r.attachments or [],
        "scope_type": r.scope_type,
        "scope_id": r.scope_id,
        "author_id": r.author_id,
        "is_public": r.is_public,
        "source_fingerprint": r.source_fingerprint,
        "stars_count": r.stars_count,
        "installs_count": r.installs_count,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "scope_label": r.scope_type,
        "author": user_out(r.author) if r.author else None,
        "starred_by_me": starred,
    }


def project_out(db: Session, p: Project) -> dict:
    pods_count = db.query(func.count(Pod.id)).filter(Pod.project_id == p.id).scalar()
    members_count = db.query(func.count(ProjectMember.id)).filter(ProjectMember.project_id == p.id).scalar()
    resources_count = (
        db.query(func.count(Resource.id))
        .filter(Resource.scope_type == "PROJECT", Resource.scope_id == p.id)
        .scalar()
    )
    return {
        "id": p.id,
        "org_id": p.org_id,
        "name": p.name,
        "description": p.description,
        "tags": p.tags or [],
        "visibility": p.visibility,
        "created_by": p.created_by,
        "created_at": p.created_at,
        "pods_count": pods_count,
        "members_count": members_count,
        "resources_count": resources_count,
    }


def pod_out(db: Session, p: Pod) -> dict:
    members_count = db.query(func.count(PodMember.id)).filter(PodMember.pod_id == p.id).scalar()
    resources_count = (
        db.query(func.count(Resource.id)).filter(Resource.scope_type == "POD", Resource.scope_id == p.id).scalar()
    )
    return {
        "id": p.id,
        "project_id": p.project_id,
        "name": p.name,
        "description": p.description,
        "purpose_tag": p.purpose_tag,
        "created_by": p.created_by,
        "created_at": p.created_at,
        "members_count": members_count,
        "resources_count": resources_count,
    }


def org_member_out(m: OrgMember) -> dict:
    return {
        "id": m.id,
        "org_id": m.org_id,
        "user_id": m.user_id,
        "role": m.role,
        "joined_at": m.joined_at,
        "last_active": m.last_active,
        "user": user_out(m.user) if m.user else None,
    }


def member_out(m: ProjectMember | PodMember, parent_key: str) -> dict:
    return {
        "id": m.id,
        parent_key: getattr(m, parent_key),
        "user_id": m.user_id,
        "role": m.role,
        "user": user_out(m.user) if m.user else None,
    }


def invitation_out(i: Invitation) -> dict:
    return {
        "id": i.id,
        "org_id": i.org_id,
        "email": i.email,
        "role": i.role,
        "token": i.token,
        "expires_at": i.expires_at,
        "accepted_at": i.accepted_at,
    }


def activity_out(a: Activity) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "org_id": a.org_id,
        "verb": a.verb,
        "object_type": a.object_type,
        "object_id": a.object_id,
        "object_title": a.object_title,
        "meta": a.meta,
        "created_at": a.created_at,
        "user": user_out(a.user) if a.user else None,
    }


# Verbs that fan out into per-user notifications (F1). Kept narrow on purpose:
# "something new/shared appeared in a scope I belong to". Stars/joins/invites
# stay out of the inbox to avoid noise.
NOTIFY_VERBS = {"created", "published"}


def _notification_recipients(db: Session, *, org_id: str, scope_type: str, scope_id: str | None) -> set[str]:
    """User ids to notify for an event in (scope_type, scope_id). Membership-based
    (F1 decision): POD → pod members, PROJECT → project members, else org members."""
    if scope_type == "POD" and scope_id:
        rows = db.query(PodMember.user_id).filter(PodMember.pod_id == scope_id).all()
    elif scope_type == "PROJECT" and scope_id:
        rows = db.query(ProjectMember.user_id).filter(ProjectMember.project_id == scope_id).all()
    else:  # ORG / PUBLIC publish → the whole owning org
        rows = db.query(OrgMember.user_id).filter(OrgMember.org_id == org_id).all()
    return {r[0] for r in rows}


def _fan_out_notifications(
    db: Session,
    *,
    actor_id: str,
    org_id: str,
    verb: str,
    object_type: str,
    object_id: str,
    object_title: str,
    meta: str | None,
    scope_type: str,
    scope_id: str | None,
) -> None:
    # Only resource events (skills/MCPs/notes) reach the inbox — not pod/project
    # creation, invites, or joins.
    if verb not in NOTIFY_VERBS or object_type != "resource":
        return
    # Gate on the org's feature flag (imported lazily to avoid an import cycle).
    from .features import feature_enabled

    org = db.get(Organization, org_id)
    if not org or not feature_enabled(db, org, "notifications"):
        return
    recipients = _notification_recipients(db, org_id=org_id, scope_type=scope_type, scope_id=scope_id)
    recipients.discard(actor_id)
    for uid in recipients:
        db.add(
            Notification(
                user_id=uid,
                actor_id=actor_id,
                org_id=org_id,
                scope_type=scope_type,
                scope_id=scope_id,
                verb=verb,
                object_type=object_type,
                object_id=object_id,
                object_title=object_title,
                meta=meta,
            )
        )


def notification_out(db: Session, n: Notification) -> dict:
    """Serialize a notification, attaching a ready-to-run install hint + a
    dashboard deep link so CLI/MCP/web can act on it directly."""
    deep_link = None
    install_command = None
    if n.object_type == "resource":
        r = db.get(Resource, n.object_id)
        if r and r.is_public:
            deep_link = f"/dashboard/marketplace/{n.object_id}"
        else:
            deep_link = f"/dashboard/org/resources?open={n.object_id}"
        if r:
            install_command = f"skillshare pull {n.object_id}"
    return {
        "id": n.id,
        "actor_id": n.actor_id,
        "org_id": n.org_id,
        "scope_type": n.scope_type,
        "scope_id": n.scope_id,
        "verb": n.verb,
        "object_type": n.object_type,
        "object_id": n.object_id,
        "object_title": n.object_title,
        "meta": n.meta,
        "read_at": n.read_at,
        "created_at": n.created_at,
        "actor": user_out(n.actor) if n.actor else None,
        "deep_link": deep_link,
        "install_command": install_command,
    }


def log_activity(
    db: Session,
    *,
    user_id: str,
    org_id: str,
    verb: str,
    object_type: str,
    object_id: str,
    object_title: str,
    meta: str | None = None,
    scope_type: str = "ORG",
    scope_id: str | None = None,
) -> None:
    db.add(
        Activity(
            user_id=user_id,
            org_id=org_id,
            verb=verb,
            object_type=object_type,
            object_id=object_id,
            object_title=object_title,
            meta=meta,
        )
    )
    _fan_out_notifications(
        db,
        actor_id=user_id,
        org_id=org_id,
        verb=verb,
        object_type=object_type,
        object_id=object_id,
        object_title=object_title,
        meta=meta,
        scope_type=scope_type,
        scope_id=scope_id,
    )


def filter_resources(rows: list[Resource], q: str | None, type_: str | None, tag: str | None) -> list[Resource]:
    """Shared ?q=&type=&tag= filtering — matches the client mock exactly
    (title, description, or tags; case-insensitive). Python-side for v1;
    move to Postgres FTS when datasets demand it (§1 search row)."""
    if type_ and type_.upper() != "ALL":
        rows = [r for r in rows if r.type == type_.upper()]
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    if q and q.strip():
        needle = q.lower().strip()
        rows = [
            r
            for r in rows
            if needle in r.title.lower()
            or needle in (r.description or "").lower()
            or any(needle in t.lower() for t in (r.tags or []))
        ]
    return rows


# ---- Marketing content serializers ----
#
# Public shapes mirror the marketing site's types field-for-field
# (website/src/lib/blog.ts BlogPost, website/src/components/LegalPage.tsx
# LegalSection) so the site can consume them with no remapping. The admin
# variants add id/status/timestamps for content management.


def blog_post_out(p: BlogPost, admin: bool = False) -> dict:
    out = {
        "slug": p.slug,
        "title": p.title,
        "date": p.date,
        "tag": p.tag,
        "excerpt": p.excerpt,
        "readingMinutes": p.reading_minutes,
        "author": {"name": p.author_name, "role": p.author_role},
        "standfirst": p.standfirst,
        "featured": p.featured,
        "body": p.body or [],
    }
    if admin:
        out.update({"id": p.id, "status": p.status, "created_at": p.created_at, "updated_at": p.updated_at})
    return out


def changelog_out(c: ChangelogEntry, admin: bool = False) -> dict:
    out = {"date": c.date, "tag": c.tag, "title": c.title, "body": c.body}
    if admin:
        out.update({"id": c.id, "status": c.status, "created_at": c.created_at, "updated_at": c.updated_at})
    return out


def content_page_out(p: ContentPage, admin: bool = False) -> dict:
    out = {
        "key": p.key,
        "kicker": p.kicker,
        "title": p.title,
        "intro": p.intro,
        "updated": p.updated_label,
        "sections": p.sections or [],
    }
    if admin:
        out.update({"id": p.id, "status": p.status, "created_at": p.created_at, "updated_at": p.updated_at})
    return out


def sort_resources(rows: list[Resource], sort: str | None) -> list[Resource]:
    sort = sort or "updated"
    if sort == "stars":
        return sorted(rows, key=lambda r: r.stars_count, reverse=True)
    if sort == "installs":
        return sorted(rows, key=lambda r: r.installs_count, reverse=True)
    if sort == "newest":
        return sorted(rows, key=lambda r: r.created_at, reverse=True)
    return sorted(rows, key=lambda r: r.updated_at, reverse=True)
