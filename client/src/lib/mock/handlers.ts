/**
 * Mock API server — implements the same REST surface as BACKEND SPEC §3
 * (backend/BACKEND_SPEC.md), route for route, including the error envelope.
 *
 * lib/api/http.ts dispatches here when NEXT_PUBLIC_API_URL is unset. When
 * the real backend exists, requests go over the network instead and this
 * file is dead code. Keep route patterns in sync with the spec.
 */

import { FEATURES, getDb, saveDb, uid, resetDb, type Db } from "./db";
import type {
  Activity,
  ApiError,
  Feedback,
  Invitation,
  OrgRole,
  Pod,
  Project,
  Resource,
  ScopeType,
  User,
} from "../types";

type Json = Record<string, unknown>;
type Params = Record<string, string>;
type Handler = (p: Params, body: Json, query: URLSearchParams, db: Db) => unknown;

class HttpError extends Error {
  constructor(
    public status: number,
    public code: ApiError["error"]["code"],
    message: string
  ) {
    super(message);
  }
}

const notFound = (what: string) => new HttpError(404, "NOT_FOUND", `${what} not found`);
const unauthorized = () => new HttpError(401, "UNAUTHORIZED", "Authentication required");

/* ---------------- helpers ---------------- */

const now = () => new Date().toISOString();

function currentUser(db: Db): User {
  const u = db.users.find((x) => x.id === db.session_user_id);
  if (!u) throw unauthorized();
  return u;
}

function enrich(r: Resource, db: Db): Resource {
  const me = db.session_user_id;
  return {
    ...r,
    scope_label: r.scope_type,
    author: db.users.find((u) => u.id === r.author_id),
    starred_by_me: me
      ? db.resource_stars.some((s) => s.resource_id === r.id && s.user_id === me)
      : false,
    pinned_by_me: me
      ? db.resource_pins.some((p) => p.resource_id === r.id && p.user_id === me)
      : false,
  };
}

function projectWithCounts(p: Project, db: Db): Project {
  return {
    ...p,
    pods_count: db.pods.filter((x) => x.project_id === p.id).length,
    members_count: db.project_members.filter((x) => x.project_id === p.id).length,
    resources_count: db.resources.filter((r) => r.scope_type === "PROJECT" && r.scope_id === p.id).length,
  };
}

function podWithCounts(p: Pod, db: Db): Pod {
  return {
    ...p,
    members_count: db.pod_members.filter((x) => x.pod_id === p.id).length,
    resources_count: db.resources.filter((r) => r.scope_type === "POD" && r.scope_id === p.id).length,
  };
}

function orgBySlug(db: Db, slug: string) {
  const org = db.organizations.find((o) => o.slug === slug);
  if (!org) throw notFound(`Organization "${slug}"`);
  return org;
}

function logActivity(db: Db, a: Omit<Activity, "id" | "created_at">) {
  db.activities.unshift({ ...a, id: uid("act"), created_at: now() });
}

/** Resolve one org's feature flags: catalog defaults + overrides + license. */
function resolveFeatures(db: Db, orgId: string) {
  const org = db.organizations.find((o) => o.id === orgId);
  return FEATURES.map((f) => {
    const licensed = !f.premium || org?.plan === "PREMIUM";
    const override = db.org_features.find((x) => x.org_id === orgId && x.key === f.key);
    return {
      ...f,
      licensed,
      // unlicensed premium features are always off, regardless of override
      enabled: licensed && (override ? override.enabled : f.default_enabled),
    };
  });
}

function featureEnabled(db: Db, orgId: string | null, key: string): boolean {
  if (!orgId) return true; // resources outside an org scope aren't gated
  return resolveFeatures(db, orgId).find((f) => f.key === key)?.enabled ?? true;
}

/* ---------------- route table ---------------- */

const routes: [method: string, pattern: string, fn: Handler][] = [
  /* ---- 3.1 Auth ---- */
  ["POST", "/api/auth/signup", (_p, body, _q, db) => {
    const email = String(body.email ?? "").toLowerCase();
    if (db.users.some((u) => u.email === email))
      throw new HttpError(409, "CONFLICT", "An account with this email already exists");
    const username = String(body.display_name ?? email.split("@")[0])
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    const user: User = {
      id: uid("u"),
      email,
      username,
      display_name: String(body.display_name ?? username),
      avatar_url: null,
      bio: "",
      is_publisher: false,
      created_at: now(),
      updated_at: now(),
    };
    db.users.push(user);
    db.session_user_id = user.id;
    saveDb();
    return { user, access_token: "mock-access-token", refresh_token: "mock-refresh-token" };
  }],

  ["POST", "/api/auth/login", (_p, body, _q, db) => {
    const email = String(body.email ?? "").toLowerCase();
    const user = db.users.find((u) => u.email === email);
    // Mock accepts any password for a known email.
    if (!user) throw new HttpError(401, "UNAUTHORIZED", "Invalid email or password");
    db.session_user_id = user.id;
    saveDb();
    return { user, access_token: "mock-access-token", refresh_token: "mock-refresh-token" };
  }],

  ["POST", "/api/auth/logout", (_p, _b, _q, db) => {
    db.session_user_id = null;
    saveDb();
    return { ok: true };
  }],

  ["GET", "/api/auth/me", (_p, _b, _q, db) => currentUser(db)],

  ["PATCH", "/api/auth/me", (_p, body, _q, db) => {
    const me = currentUser(db);
    Object.assign(me, {
      display_name: body.display_name ?? me.display_name,
      bio: body.bio ?? me.bio,
      location: body.location ?? me.location,
      website: body.website ?? me.website,
      is_publisher: body.is_publisher ?? me.is_publisher,
      avatar_url: body.avatar_url !== undefined ? (body.avatar_url as string | null) : me.avatar_url,
      updated_at: now(),
    });
    saveDb();
    return me;
  }],

  /* ---- 3.2 Organizations ---- */
  ["GET", "/api/orgs", (_p, _b, _q, db) => {
    const me = currentUser(db);
    return db.org_members
      .filter((m) => m.user_id === me.id)
      .map((m) => ({
        ...db.organizations.find((o) => o.id === m.org_id)!,
        my_role: m.role,
      }));
  }],

  ["POST", "/api/orgs", (_p, body, _q, db) => {
    const me = currentUser(db);
    const name = String(body.name ?? "").trim();
    const slug = String(body.slug ?? name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    if (!name || !slug) throw new HttpError(422, "VALIDATION_ERROR", "Organization name is required");
    if (db.organizations.some((o) => o.slug === slug))
      throw new HttpError(409, "CONFLICT", `Slug "${slug}" is taken`);
    const org = {
      id: uid("org"), name, slug, logo_url: null,
      description: String(body.description ?? ""),
      is_public: false, owner_id: me.id,
      plan: "FREE" as const, created_at: now(),
    };
    db.organizations.push(org);
    db.org_members.push({ id: uid("om"), org_id: org.id, user_id: me.id, role: "ADMIN", joined_at: now(), last_active: now() });
    saveDb();
    return org;
  }],

  ["GET", "/api/orgs/:slug", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const membership = db.org_members.find((m) => m.org_id === org.id && m.user_id === me.id);
    if (!membership) throw new HttpError(403, "FORBIDDEN", "You are not a member of this organization");
    return {
      ...org,
      my_role: membership.role,
      followers_count: db.org_follows.filter((f) => f.org_id === org.id).length,
      following: db.org_follows.some((f) => f.org_id === org.id && f.follower_id === me.id),
    };
  }],

  ["POST", "/api/orgs/:slug/follow", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    if (!db.org_follows.some((f) => f.org_id === org.id && f.follower_id === me.id))
      db.org_follows.push({ id: uid("ofl"), follower_id: me.id, org_id: org.id });
    saveDb();
    return { following: true, followers_count: db.org_follows.filter((f) => f.org_id === org.id).length };
  }],

  ["DELETE", "/api/orgs/:slug/follow", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    db.org_follows = db.org_follows.filter((f) => !(f.org_id === org.id && f.follower_id === me.id));
    saveDb();
    return { following: false, followers_count: db.org_follows.filter((f) => f.org_id === org.id).length };
  }],

  ["PATCH", "/api/orgs/:slug", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    if (body.terminology !== undefined && !featureEnabled(db, org.id, "custom-terminology"))
      throw new HttpError(403, "FORBIDDEN", "Custom terminology is a premium feature — activate a license to rename Projects and Pods");
    Object.assign(org, {
      name: body.name ?? org.name,
      description: body.description ?? org.description,
      logo_url: body.logo_url ?? org.logo_url,
      terminology: body.terminology !== undefined ? body.terminology : org.terminology,
    });
    saveDb();
    return org;
  }],

  /* ---- feature flags & licensing (BACKEND SPEC §3.8) ---- */
  ["GET", "/api/orgs/:slug/features", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    return resolveFeatures(db, org.id);
  }],

  ["PATCH", "/api/orgs/:slug/features/:key", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const membership = db.org_members.find((m) => m.org_id === org.id && m.user_id === me.id);
    if (membership?.role !== "ADMIN")
      throw new HttpError(403, "FORBIDDEN", "Only org admins can change features");
    const flag = FEATURES.find((f) => f.key === p.key);
    if (!flag) throw notFound(`Feature "${p.key}"`);
    if (flag.premium && org.plan !== "PREMIUM")
      throw new HttpError(403, "FORBIDDEN", `"${flag.name}" is a premium feature — activate a license first`);
    const enabled = Boolean(body.enabled);
    const existing = db.org_features.find((x) => x.org_id === org.id && x.key === p.key);
    if (existing) existing.enabled = enabled;
    else db.org_features.push({ id: uid("of"), org_id: org.id, key: p.key, enabled });
    saveDb();
    return resolveFeatures(db, org.id).find((f) => f.key === p.key);
  }],

  ["POST", "/api/orgs/:slug/license", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const membership = db.org_members.find((m) => m.org_id === org.id && m.user_id === me.id);
    if (membership?.role !== "ADMIN")
      throw new HttpError(403, "FORBIDDEN", "Only org admins can activate a license");
    const key = String(body.license_key ?? "").trim().toUpperCase();
    // Mock validation — real backend verifies against the licensing service.
    if (!/^T41-PREM-[A-Z0-9]{4,}$/.test(key))
      throw new HttpError(422, "VALIDATION_ERROR", "Invalid license key (mock format: T41-PREM-XXXX)");
    org.plan = "PREMIUM";
    saveDb();
    return { plan: org.plan, features: resolveFeatures(db, org.id) };
  }],

  ["GET", "/api/orgs/:slug/members", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    return db.org_members
      .filter((m) => m.org_id === org.id)
      .map((m) => ({ ...m, user: db.users.find((u) => u.id === m.user_id) }));
  }],

  ["POST", "/api/orgs/:slug/invite", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const email = String(body.email ?? "").toLowerCase();
    if (!email.includes("@")) throw new HttpError(422, "VALIDATION_ERROR", "A valid email is required");
    const inv: Invitation = {
      id: uid("inv"), org_id: org.id, email,
      role: (body.role as OrgRole) ?? "MEMBER",
      token: uid("tok"),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      accepted_at: null,
    };
    db.invitations.push(inv);
    logActivity(db, { user_id: me.id, org_id: org.id, verb: "invited", object_type: "member", object_id: inv.id, object_title: email });
    saveDb();
    return inv;
  }],

  ["GET", "/api/orgs/:slug/invitations", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    return db.invitations.filter((i) => i.org_id === org.id && !i.accepted_at);
  }],

  ["DELETE", "/api/orgs/:slug/invitations/:invId", (p, _b, _q, db) => {
    db.invitations = db.invitations.filter((i) => i.id !== p.invId);
    saveDb();
    return { ok: true };
  }],

  ["POST", "/api/orgs/:slug/join/:token", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const inv = db.invitations.find((i) => i.org_id === org.id && i.token === p.token && !i.accepted_at);
    if (!inv) throw notFound("Invitation");
    inv.accepted_at = now();
    db.org_members.push({ id: uid("om"), org_id: org.id, user_id: me.id, role: inv.role, joined_at: now(), last_active: now() });
    saveDb();
    return { ok: true };
  }],

  ["DELETE", "/api/orgs/:slug/members/:userId", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    db.org_members = db.org_members.filter((m) => !(m.org_id === org.id && m.user_id === p.userId));
    saveDb();
    return { ok: true };
  }],

  ["PATCH", "/api/orgs/:slug/members/:userId", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const m = db.org_members.find((x) => x.org_id === org.id && x.user_id === p.userId);
    if (!m) throw notFound("Member");
    m.role = (body.role as OrgRole) ?? m.role;
    saveDb();
    return m;
  }],

  // Command-palette search: resources + projects + pods + members in one org
  ["GET", "/api/orgs/:slug/search", (p, _b, q, db) => {
    const org = orgBySlug(db, p.slug);
    const needle = (q.get("q") ?? "").toLowerCase().trim();
    const match = (s: string) => s.toLowerCase().includes(needle);
    const projects = db.projects.filter((x) => x.org_id === org.id);
    const projectIds = projects.map((x) => x.id);
    const pods = db.pods.filter((x) => projectIds.includes(x.project_id));
    const podIds = pods.map((x) => x.id);
    const resources = db.resources.filter(
      (r) =>
        (r.scope_type === "ORG" && r.scope_id === org.id) ||
        (r.scope_type === "PROJECT" && projectIds.includes(r.scope_id ?? "")) ||
        (r.scope_type === "POD" && podIds.includes(r.scope_id ?? ""))
    );
    const members = db.org_members
      .filter((m) => m.org_id === org.id)
      .map((m) => db.users.find((u) => u.id === m.user_id)!)
      .filter(Boolean);
    if (!needle)
      return { resources: resources.slice(0, 5).map((r) => enrich(r, db)), projects: projects.slice(0, 3), pods: pods.slice(0, 3), members: [] };
    return {
      resources: resources
        .filter((r) => match(r.title) || r.tags.some(match))
        .slice(0, 6)
        .map((r) => enrich(r, db)),
      projects: projects.filter((x) => match(x.name)).slice(0, 4),
      pods: pods.filter((x) => match(x.name)).slice(0, 4),
      members: members.filter((u) => match(u.display_name) || match(u.username)).slice(0, 4),
    };
  }],

  // Org page — everything this org has published to the marketplace.
  ["GET", "/api/orgs/:slug/published", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const projectIds = db.projects.filter((x) => x.org_id === org.id).map((x) => x.id);
    const podIds = db.pods.filter((x) => projectIds.includes(x.project_id)).map((x) => x.id);
    return db.resources
      .filter(
        (r) =>
          r.is_public &&
          ((r.scope_type === "ORG" && r.scope_id === org.id) ||
            (r.scope_type === "PROJECT" && projectIds.includes(r.scope_id ?? "")) ||
            (r.scope_type === "POD" && podIds.includes(r.scope_id ?? "")))
      )
      .sort((a, b) => b.stars_count - a.stars_count)
      .map((r) => enrich(r, db));
  }],

  ["GET", "/api/orgs/:slug/activity", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    return db.activities
      .filter((a) => a.org_id === org.id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 20)
      .map((a) => ({ ...a, user: db.users.find((u) => u.id === a.user_id) }));
  }],

  /* ---- notifications (F1) ---- */
  // Single-user mock: the seeded inbox belongs to the demo user; the real
  // backend filters per recipient. Here we just require auth and serve it.
  ["GET", "/api/notifications", (_p, _b, q, db) => {
    currentUser(db);
    const unreadOnly = q.get("unread_only") === "true";
    const limit = Number(q.get("limit") ?? 30);
    return (db.notifications ?? [])
      .filter((n) => (unreadOnly ? !n.read_at : true))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, limit)
      .map((n) => ({ ...n, actor: db.users.find((u) => u.id === n.actor_id) }));
  }],

  ["GET", "/api/notifications/unread_count", (_p, _b, _q, db) => {
    currentUser(db);
    return { count: (db.notifications ?? []).filter((n) => !n.read_at).length };
  }],

  ["POST", "/api/notifications/read", (_p, body, _q, db) => {
    currentUser(db);
    const all = body.all === true;
    const ids = Array.isArray(body.ids) ? (body.ids as string[]) : [];
    if (!all && ids.length === 0) throw new HttpError(422, "VALIDATION_ERROR", "Pass ids or all:true");
    let marked = 0;
    for (const n of db.notifications ?? []) {
      if (!n.read_at && (all || ids.includes(n.id))) {
        n.read_at = now();
        marked += 1;
      }
    }
    saveDb();
    return { ok: true, marked };
  }],

  /* ---- feedback ---- */
  ["POST", "/api/feedback", (_p, body, _q, db) => {
    const me = currentUser(db);
    const message = String(body.message ?? "").trim();
    if (!message) throw new HttpError(422, "VALIDATION_ERROR", "Feedback message is required");
    const targetType = body.target_type === "resource" ? "resource" : "platform";
    let targetId: string | null = null;
    if (targetType === "resource") {
      targetId = String(body.target_id ?? "");
      if (!targetId) throw new HttpError(422, "VALIDATION_ERROR", "target_id is required for resource feedback");
      if (!db.resources.some((r) => r.id === targetId)) throw notFound("Resource");
    }
    const rating = body.rating == null ? null : Number(body.rating);
    if (rating != null && (rating < 1 || rating > 5))
      throw new HttpError(422, "VALIDATION_ERROR", "rating must be 1-5");
    const fb: Feedback = {
      id: uid("fb"),
      user_id: me.id,
      target_type: targetType,
      target_id: targetId,
      rating,
      category: (body.category as Feedback["category"]) ?? "general",
      message,
      source: (body.source as Feedback["source"]) ?? "dashboard",
      context: (body.context as Record<string, unknown>) ?? null,
      status: "open",
      created_at: now(),
      updated_at: now(),
    };
    db.feedback = db.feedback ?? [];
    db.feedback.unshift(fb);
    saveDb();
    return fb;
  }],

  ["GET", "/api/feedback/mine", (_p, _b, _q, db) => {
    const me = currentUser(db);
    return (db.feedback ?? [])
      .filter((f) => f.user_id === me.id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }],

  /* ---- 3.3 Projects ---- */
  ["GET", "/api/orgs/:slug/projects", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    return db.projects.filter((x) => x.org_id === org.id).map((x) => projectWithCounts(x, db));
  }],

  ["POST", "/api/orgs/:slug/projects", (p, body, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const name = String(body.name ?? "").trim();
    if (!name) throw new HttpError(422, "VALIDATION_ERROR", "Project name is required");
    const project: Project = {
      id: uid("proj"), org_id: org.id, name,
      description: String(body.description ?? ""),
      tags: (body.tags as string[]) ?? [],
      visibility: "ORG", created_by: me.id, created_at: now(),
    };
    db.projects.push(project);
    db.project_members.push({ id: uid("pm"), project_id: project.id, user_id: me.id, role: "LEAD" });
    logActivity(db, { user_id: me.id, org_id: org.id, verb: "created", object_type: "project", object_id: project.id, object_title: project.name });
    saveDb();
    return projectWithCounts(project, db);
  }],

  ["GET", "/api/orgs/:slug/projects/:projectId", (p, _b, _q, db) => {
    const project = db.projects.find((x) => x.id === p.projectId);
    if (!project) throw notFound("Project");
    return projectWithCounts(project, db);
  }],

  ["PATCH", "/api/orgs/:slug/projects/:projectId", (p, body, _q, db) => {
    const project = db.projects.find((x) => x.id === p.projectId);
    if (!project) throw notFound("Project");
    Object.assign(project, {
      name: body.name ?? project.name,
      description: body.description ?? project.description,
      tags: body.tags ?? project.tags,
      visibility: body.visibility ?? project.visibility,
    });
    saveDb();
    return projectWithCounts(project, db);
  }],

  ["DELETE", "/api/orgs/:slug/projects/:projectId", (p, _b, _q, db) => {
    const podIds = db.pods.filter((x) => x.project_id === p.projectId).map((x) => x.id);
    db.pods = db.pods.filter((x) => x.project_id !== p.projectId);
    db.pod_members = db.pod_members.filter((m) => !podIds.includes(m.pod_id));
    db.resources = db.resources.filter(
      (r) =>
        !(r.scope_type === "PROJECT" && r.scope_id === p.projectId) &&
        !(r.scope_type === "POD" && podIds.includes(r.scope_id ?? ""))
    );
    db.project_members = db.project_members.filter((m) => m.project_id !== p.projectId);
    db.projects = db.projects.filter((x) => x.id !== p.projectId);
    saveDb();
    return { ok: true };
  }],

  ["GET", "/api/orgs/:slug/projects/:projectId/members", (p, _b, _q, db) =>
    db.project_members
      .filter((m) => m.project_id === p.projectId)
      .map((m) => ({ ...m, user: db.users.find((u) => u.id === m.user_id) })),
  ],

  ["POST", "/api/orgs/:slug/projects/:projectId/members", (p, body, _q, db) => {
    const m = {
      id: uid("pm"), project_id: p.projectId,
      user_id: String(body.user_id),
      role: (body.role as "LEAD" | "MEMBER") ?? "MEMBER",
    };
    db.project_members.push(m);
    saveDb();
    return m;
  }],

  /* ---- 3.4 Pods ---- */
  ["GET", "/api/projects/:projectId/pods", (p, _b, _q, db) =>
    db.pods.filter((x) => x.project_id === p.projectId).map((x) => podWithCounts(x, db)),
  ],

  ["POST", "/api/projects/:projectId/pods", (p, body, _q, db) => {
    const me = currentUser(db);
    const project = db.projects.find((x) => x.id === p.projectId);
    if (!project) throw notFound("Project");
    const name = String(body.name ?? "").trim();
    if (!name) throw new HttpError(422, "VALIDATION_ERROR", "Pod name is required");
    const pod: Pod = {
      id: uid("pod"), project_id: p.projectId, name,
      description: String(body.description ?? ""),
      purpose_tag: String(body.purpose_tag ?? ""),
      created_by: me.id, created_at: now(),
    };
    db.pods.push(pod);
    db.pod_members.push({ id: uid("pdm"), pod_id: pod.id, user_id: me.id, role: "OWNER" });
    logActivity(db, { user_id: me.id, org_id: project.org_id, verb: "created", object_type: "pod", object_id: pod.id, object_title: pod.name });
    saveDb();
    return podWithCounts(pod, db);
  }],

  ["GET", "/api/projects/:projectId/pods/:podId", (p, _b, _q, db) => {
    const pod = db.pods.find((x) => x.id === p.podId);
    if (!pod) throw notFound("Pod");
    return podWithCounts(pod, db);
  }],

  ["PATCH", "/api/projects/:projectId/pods/:podId", (p, body, _q, db) => {
    const pod = db.pods.find((x) => x.id === p.podId);
    if (!pod) throw notFound("Pod");
    Object.assign(pod, {
      name: body.name ?? pod.name,
      description: body.description ?? pod.description,
      purpose_tag: body.purpose_tag ?? pod.purpose_tag,
    });
    saveDb();
    return podWithCounts(pod, db);
  }],

  ["DELETE", "/api/projects/:projectId/pods/:podId", (p, _b, _q, db) => {
    db.pod_members = db.pod_members.filter((m) => m.pod_id !== p.podId);
    db.resources = db.resources.filter((r) => !(r.scope_type === "POD" && r.scope_id === p.podId));
    db.pods = db.pods.filter((x) => x.id !== p.podId);
    saveDb();
    return { ok: true };
  }],

  ["GET", "/api/projects/:projectId/pods/:podId/members", (p, _b, _q, db) =>
    db.pod_members
      .filter((m) => m.pod_id === p.podId)
      .map((m) => ({ ...m, user: db.users.find((u) => u.id === m.user_id) })),
  ],

  ["POST", "/api/projects/:projectId/pods/:podId/members", (p, body, _q, db) => {
    const m = {
      id: uid("pdm"), pod_id: p.podId,
      user_id: String(body.user_id),
      role: (body.role as "OWNER" | "MEMBER") ?? "MEMBER",
    };
    db.pod_members.push(m);
    saveDb();
    return m;
  }],

  /* ---- 3.5 Resources ---- */
  ["POST", "/api/resources", (_p, body, _q, db) => {
    const me = currentUser(db);
    const title = String(body.title ?? "").trim();
    if (!title) throw new HttpError(422, "VALIDATION_ERROR", "Title is required");
    const r: Resource = {
      id: uid("res"),
      type: body.type as Resource["type"],
      title,
      description: String(body.description ?? ""),
      content_md: String(body.content_md ?? ""),
      server_url: body.server_url ? String(body.server_url) : undefined,
      config_json: body.config_json ? String(body.config_json) : undefined,
      file_url: (body.file_url as string) ?? null,
      version: String(body.version ?? "0.1.0"),
      tags: (body.tags as string[]) ?? [],
      attachments: (body.attachments as Resource["attachments"]) ?? [],
      scope_type: body.scope_type as ScopeType,
      scope_id: (body.scope_id as string) ?? null,
      author_id: me.id,
      is_public: false,
      stars_count: 0,
      created_at: now(),
      updated_at: now(),
    };
    db.resources.push(r);
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "created", object_type: "resource", object_id: r.id, object_title: r.title });
    saveDb();
    return enrich(r, db);
  }],

  ["GET", "/api/resources/:id", (p, _b, _q, db) => {
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    return enrich(r, db);
  }],

  ["PATCH", "/api/resources/:id", (p, body, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    Object.assign(r, {
      title: body.title ?? r.title,
      description: body.description ?? r.description,
      content_md: body.content_md ?? r.content_md,
      server_url: body.server_url ?? r.server_url,
      config_json: body.config_json ?? r.config_json,
      version: body.version ?? r.version,
      tags: body.tags ?? r.tags,
      attachments: body.attachments ?? r.attachments,
      scope_type: body.scope_type ?? r.scope_type,
      scope_id: body.scope_id !== undefined ? body.scope_id : r.scope_id,
      file_url: body.file_url !== undefined ? body.file_url : r.file_url,
      updated_at: now(),
    });
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "updated", object_type: "resource", object_id: r.id, object_title: r.title, meta: `v${r.version}` });
    saveDb();
    return enrich(r, db);
  }],

  ["DELETE", "/api/resources/:id", (p, _b, _q, db) => {
    db.resources = db.resources.filter((x) => x.id !== p.id);
    db.resource_stars = db.resource_stars.filter((s) => s.resource_id !== p.id);
    saveDb();
    return { ok: true };
  }],

  ["GET", "/api/orgs/:slug/resources", (p, _b, q, db) => {
    const org = orgBySlug(db, p.slug);
    return filterResources(
      db.resources.filter((r) => r.scope_type === "ORG" && r.scope_id === org.id),
      q, db
    );
  }],

  ["GET", "/api/projects/:projectId/resources", (p, _b, q, db) =>
    filterResources(
      db.resources.filter((r) => r.scope_type === "PROJECT" && r.scope_id === p.projectId),
      q, db
    ),
  ],

  // Pod resources — BACKEND SPEC §5 inheritance union (?scope=all|pod|project|org)
  ["GET", "/api/pods/:podId/resources", (p, _b, q, db) => {
    const pod = db.pods.find((x) => x.id === p.podId);
    if (!pod) throw notFound("Pod");
    const project = db.projects.find((x) => x.id === pod.project_id);
    const scope = (q.get("scope") ?? "all").toLowerCase();
    const pool = db.resources.filter((r) => {
      const isPod = r.scope_type === "POD" && r.scope_id === pod.id;
      const isProject = r.scope_type === "PROJECT" && r.scope_id === pod.project_id;
      const isOrg = r.scope_type === "ORG" && r.scope_id === project?.org_id;
      if (scope === "pod") return isPod;
      if (scope === "project") return isProject;
      if (scope === "org") return isOrg;
      return isPod || isProject || isOrg;
    });
    return filterResources(pool, q, db);
  }],

  ["POST", "/api/resources/:id/publish", (p, _b, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    if (!me.is_publisher)
      throw new HttpError(403, "FORBIDDEN", "Enable publisher mode in your profile to publish to the marketplace");
    if (!featureEnabled(db, scopeOrgId(db, r), "publishing"))
      throw new HttpError(403, "FORBIDDEN", "Marketplace publishing is disabled for this organization");
    const wasPublic = r.is_public;
    r.is_public = true;
    r.updated_at = now();
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "published", object_type: "resource", object_id: r.id, object_title: r.title });
    // Newly public → notify the author's followers (mirrors backend
    // notify_followers). The mock inbox is single-user (no recipient field), so
    // we add one entry per follow; in seed only Ada has a follower (the demo
    // user), so this fires when viewing the real cross-user flow.
    if (!wasPublic) {
      for (const f of db.follows.filter((x) => x.publisher_id === r.author_id && x.follower_id !== r.author_id)) {
        void f;
        db.notifications.unshift({
          id: uid("ntf"), actor_id: r.author_id, org_id: orgId,
          scope_type: "PUBLIC", scope_id: null, verb: "published", object_type: "resource",
          object_id: r.id, object_title: r.title, meta: "from a publisher you follow",
          read_at: null, created_at: now(),
        });
      }
    }
    saveDb();
    return enrich(r, db);
  }],

  ["DELETE", "/api/resources/:id/publish", (p, _b, _q, db) => {
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    r.is_public = false;
    r.updated_at = now();
    saveDb();
    return enrich(r, db);
  }],

  ["POST", "/api/resources/:id/star", (p, _b, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    if (!db.resource_stars.some((s) => s.resource_id === r.id && s.user_id === me.id)) {
      db.resource_stars.push({ id: uid("st"), resource_id: r.id, user_id: me.id });
      r.stars_count += 1;
    }
    saveDb();
    return enrich(r, db);
  }],

  ["DELETE", "/api/resources/:id/star", (p, _b, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    const before = db.resource_stars.length;
    db.resource_stars = db.resource_stars.filter((s) => !(s.resource_id === r.id && s.user_id === me.id));
    if (db.resource_stars.length < before) r.stars_count = Math.max(0, r.stars_count - 1);
    saveDb();
    return enrich(r, db);
  }],

  ["POST", "/api/resources/:id/pin", (p, _b, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    if (!db.resource_pins.some((x) => x.resource_id === r.id && x.user_id === me.id)) {
      const count = db.resource_pins.filter((x) => x.user_id === me.id).length;
      if (count >= 6)
        throw new HttpError(422, "VALIDATION_ERROR", "You can pin up to 6 resources — unpin one first");
      db.resource_pins.push({ id: uid("pin"), resource_id: r.id, user_id: me.id, position: count });
    }
    saveDb();
    return enrich(r, db);
  }],

  ["DELETE", "/api/resources/:id/pin", (p, _b, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    db.resource_pins = db.resource_pins.filter((x) => !(x.resource_id === r.id && x.user_id === me.id));
    saveDb();
    return enrich(r, db);
  }],

  // Presigned-upload stand-in: returns a fake CDN URL immediately.
  ["POST", "/api/resources/upload", (_p, body) => ({
    file_url: `https://cdn.skillshare.think41.com/packages/${String(body.filename ?? "package.skill").replace(/[^a-zA-Z0-9.-]/g, "-")}`,
  })],

  // "Add to my org" — copies a public resource into an org (client addition, documented in backend spec §8)
  ["POST", "/api/resources/:id/import", (p, body, _q, db) => {
    const me = currentUser(db);
    const src = db.resources.find((x) => x.id === p.id && x.is_public);
    if (!src) throw notFound("Public resource");
    const org = orgBySlug(db, String(body.org_slug));
    if (!featureEnabled(db, org.id, "marketplace"))
      throw new HttpError(403, "FORBIDDEN", "The public marketplace is disabled for this organization");
    const copy: Resource = {
      ...structuredClone(src),
      id: uid("res"),
      scope_type: "ORG",
      scope_id: org.id,
      is_public: false,
      stars_count: 0,
      author_id: me.id,
      created_at: now(),
      updated_at: now(),
    };
    delete copy.author;
    delete copy.starred_by_me;
    delete copy.scope_label;
    db.resources.push(copy);
    if (src.installs_count !== undefined) src.installs_count += 1;
    logActivity(db, { user_id: me.id, org_id: org.id, verb: "created", object_type: "resource", object_id: copy.id, object_title: copy.title, meta: "imported from marketplace" });
    saveDb();
    return enrich(copy, db);
  }],

  /* ---- 3.6 Public marketplace ---- */
  ["GET", "/api/public/resources", (_p, _b, q, db) =>
    filterResources(db.resources.filter((r) => r.is_public), q, db),
  ],

  ["GET", "/api/public/resources/:id", (p, _b, _q, db) => {
    const r = db.resources.find((x) => x.id === p.id && x.is_public);
    if (!r) throw notFound("Resource");
    return enrich(r, db);
  }],

  ["GET", "/api/public/publishers/:username", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("Publisher");
    const me = db.session_user_id;
    return {
      ...user,
      resources: db.resources
        .filter((r) => r.is_public && r.author_id === user.id)
        .map((r) => enrich(r, db)),
      followers_count: db.follows.filter((f) => f.publisher_id === user.id).length,
      following: !!me && db.follows.some((f) => f.publisher_id === user.id && f.follower_id === me),
    };
  }],

  ["POST", "/api/public/publishers/:username/follow", (p, _b, _q, db) => {
    const me = currentUser(db);
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("Publisher");
    if (user.id === me.id) throw new HttpError(422, "VALIDATION_ERROR", "You can't follow yourself");
    if (!db.follows.some((f) => f.publisher_id === user.id && f.follower_id === me.id))
      db.follows.push({ id: uid("fol"), follower_id: me.id, publisher_id: user.id });
    saveDb();
    return { following: true, followers_count: db.follows.filter((f) => f.publisher_id === user.id).length };
  }],

  ["DELETE", "/api/public/publishers/:username/follow", (p, _b, _q, db) => {
    const me = currentUser(db);
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("Publisher");
    db.follows = db.follows.filter((f) => !(f.publisher_id === user.id && f.follower_id === me.id));
    saveDb();
    return { following: false, followers_count: db.follows.filter((f) => f.publisher_id === user.id).length };
  }],

  ["GET", "/api/public/search", (_p, _b, q, db) =>
    filterResources(db.resources.filter((r) => r.is_public), q, db),
  ],

  /* ---- profile extras (client additions, documented in backend spec §8) ---- */
  ["GET", "/api/users/:username", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    const mine = db.resources.filter((r) => r.author_id === user.id);
    return {
      ...user,
      stats: {
        resources: mine.length,
        public_resources: mine.filter((r) => r.is_public).length,
        stars_received: mine.reduce((acc, r) => acc + r.stars_count, 0),
        stars_given: db.resource_stars.filter((s) => s.user_id === user.id).length,
        orgs: db.org_members.filter((m) => m.user_id === user.id).length,
        followers: db.follows.filter((f) => f.publisher_id === user.id).length,
        following: db.follows.filter((f) => f.follower_id === user.id).length,
      },
    };
  }],

  ["GET", "/api/users/:username/resources", (p, _b, q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    return filterResources(db.resources.filter((r) => r.author_id === user.id), q, db);
  }],

  ["GET", "/api/users/:username/starred", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    const ids = db.resource_stars.filter((s) => s.user_id === user.id).map((s) => s.resource_id);
    return db.resources.filter((r) => ids.includes(r.id)).map((r) => enrich(r, db));
  }],

  ["GET", "/api/users/:username/pinned", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    const self = db.session_user_id === user.id;
    return db.resource_pins
      .filter((x) => x.user_id === user.id)
      .sort((a, b) => a.position - b.position)
      .map((x) => db.resources.find((r) => r.id === x.resource_id))
      .filter((r): r is Resource => !!r && (self || r.is_public))
      .map((r) => enrich(r, db));
  }],

  // GitHub-style contribution heatmap: a "contribution" is a resource authored
  // or a star given, bucketed per day over the trailing window (default 26wk).
  ["GET", "/api/users/:username/contributions", (p, _b, q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    const self = db.session_user_id === user.id;
    const weeks = Math.min(53, Math.max(1, Number(q.get("weeks") ?? 26)));
    const totalDays = weeks * 7;
    const dayMs = 86400_000;
    const endDate = new Date();
    const end = endDate.toISOString().slice(0, 10);
    const startMs = endDate.getTime() - (totalDays - 1) * dayMs;
    const startDay = new Date(startMs).toISOString().slice(0, 10);

    const counts: Record<string, number> = {};
    const bump = (iso: string) => {
      const d = iso.slice(0, 10);
      if (d >= startDay && d <= end) counts[d] = (counts[d] ?? 0) + 1;
    };
    db.resources
      .filter((r) => r.author_id === user.id && (self || r.is_public))
      .forEach((r) => bump(r.created_at));
    // stars don't carry a created_at in the mock store; approximate as today so
    // recent endorsements still register a contribution.
    db.resource_stars.filter((s) => s.user_id === user.id).forEach(() => bump(end));

    const days = Array.from({ length: totalDays }, (_, i) => {
      const d = new Date(startMs + i * dayMs).toISOString().slice(0, 10);
      return { date: d, count: counts[d] ?? 0 };
    });
    const values = Object.values(counts);
    return {
      weeks,
      start: startDay,
      end,
      total: values.reduce((a, b) => a + b, 0),
      max: values.length ? Math.max(...values) : 0,
      days,
    };
  }],

  ["GET", "/api/users/:username/activity", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    return db.activities
      .filter((a) => a.user_id === user.id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 20)
      .map((a) => ({ ...a, user }));
  }],

  ["GET", "/api/users/:username/orgs", (p, _b, _q, db) => {
    const user = db.users.find((u) => u.username === p.username);
    if (!user) throw notFound("User");
    return db.org_members
      .filter((m) => m.user_id === user.id)
      .map((m) => ({ ...db.organizations.find((o) => o.id === m.org_id)!, my_role: m.role }));
  }],

  /* ---- dev convenience ---- */
  ["POST", "/api/dev/reset", () => {
    resetDb();
    return { ok: true };
  }],
];

function scopeOrgId(db: Db, r: Resource): string | null {
  if (r.scope_type === "ORG") return r.scope_id;
  if (r.scope_type === "PROJECT") return db.projects.find((p) => p.id === r.scope_id)?.org_id ?? null;
  if (r.scope_type === "POD") {
    const pod = db.pods.find((p) => p.id === r.scope_id);
    return db.projects.find((p) => p.id === pod?.project_id)?.org_id ?? null;
  }
  return null;
}

/** Shared list filtering: ?q= &type= &tag= &sort= */
/* ---------------- relevance search ----------------
 * Mirrors the backend ranker (backend/app/serialize.py relevance_rank /
 * _score_resource). Pure substring matching missed semantically close terms —
 * "code reviewer" never surfaced "PR Reviewer". We tokenize, apply a light
 * stemmer, expand a small synonym map, fall back to fuzzy token matching, and
 * rank by a weighted score (title > tags > description). */
const STOPWORDS = new Set(["a", "an", "the", "and", "or", "for", "with", "to", "of", "in", "on", "is", "my", "your"]);
const SYNONYMS: Record<string, string[]> = {
  pr: ["pull", "request"], pull: ["pr"],
  db: ["database", "postgres", "sql"], database: ["db", "postgres", "sql"],
  postgres: ["postgresql", "pg", "database"], postgresql: ["postgres", "pg", "database"],
  ci: ["pipeline", "build"], cd: ["deploy", "release"],
  doc: ["documentation"], docs: ["documentation"],
  auth: ["authentication", "login"], k8s: ["kubernetes"],
  ui: ["frontend", "interface"], frontend: ["ui"],
  rag: ["retrieval"], retrieval: ["rag"],
};
const SUFFIXES = ["ing", "ers", "er", "ed", "es", "s"];

function stem(t: string): string {
  for (const suf of SUFFIXES) {
    if (t.length > suf.length + 2 && t.endsWith(suf)) return t.slice(0, -suf.length);
  }
  return t;
}
const tokenize = (text: string): string[] => (text.toLowerCase().match(/[a-z0-9]+/g) ?? []).map(stem);
function queryTokens(q: string): string[] {
  const seen: string[] = [];
  for (const m of q.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
    if (STOPWORDS.has(m)) continue;
    const t = stem(m);
    if (t && !seen.includes(t)) seen.push(t);
  }
  return seen;
}
function expansions(token: string): Set<string> {
  const out = new Set<string>([token]);
  for (const s of SYNONYMS[token] ?? []) out.add(stem(s));
  return out;
}
// Normalized similarity (1 − Levenshtein/maxLen) — approximates difflib's ratio
// closely enough to catch the same near-misses at the 0.82 threshold.
function similarity(a: string, b: string): number {
  if (a === b) return 1;
  const m = a.length, n = b.length;
  if (!m || !n) return 0;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
    }
    prev = cur;
  }
  return 1 - prev[n] / Math.max(m, n);
}
function scoreResource(qTokens: string[], r: Resource): number {
  const fields: [Set<string>, number][] = [
    [new Set(tokenize(r.title)), 3],
    [new Set(r.tags.flatMap(tokenize)), 2],
    [new Set(tokenize(r.description)), 1],
  ];
  let total = 0, matched = 0;
  for (const qt of qTokens) {
    const exp = expansions(qt);
    let best = 0;
    for (const [tokens, weight] of fields) {
      if (!tokens.size) continue;
      if (tokens.has(qt) || [...exp].some((e) => tokens.has(e))) {
        best = Math.max(best, weight);
        continue;
      }
      if (qt.length >= 4) {
        for (const dt of tokens) {
          if (dt.length >= 4 && Math.abs(dt.length - qt.length) <= 3) {
            const ratio = similarity(qt, dt);
            if (ratio >= 0.82) best = Math.max(best, weight * ratio * 0.7);
          }
        }
      }
    }
    if (best > 0) {
      matched++;
      total += best;
    }
  }
  if (matched === 0) return 0;
  if (matched === qTokens.length) total *= 1.5;
  return total;
}

function filterResources(list: Resource[], q: URLSearchParams, db: Db): Resource[] {
  let out = [...list];
  const type = q.get("type")?.toUpperCase();
  if (type && type !== "ALL") out = out.filter((r) => r.type === type);
  const tag = q.get("tag");
  if (tag) out = out.filter((r) => r.tags.includes(tag));

  const needle = q.get("q")?.trim();
  const tokens = needle ? queryTokens(needle) : [];
  if (tokens.length) {
    out = out
      .map((r) => ({ r, score: scoreResource(tokens, r) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.r);
  }

  // Relevance order leads when there's a query and no explicit sort chosen.
  const sort = q.get("sort") ?? (tokens.length ? "relevance" : "updated");
  if (sort !== "relevance") {
    out.sort((a, b) => {
      if (sort === "stars") return b.stars_count - a.stars_count;
      if (sort === "installs") return (b.installs_count ?? 0) - (a.installs_count ?? 0);
      if (sort === "newest") return b.created_at.localeCompare(a.created_at);
      return b.updated_at.localeCompare(a.updated_at);
    });
  }
  return out.map((r) => enrich(r, db));
}

/* ---------------- dispatcher ---------------- */

function matchPath(pattern: string, path: string): Params | null {
  const ps = pattern.split("/").filter(Boolean);
  const xs = path.split("/").filter(Boolean);
  if (ps.length !== xs.length) return null;
  const params: Params = {};
  for (let i = 0; i < ps.length; i++) {
    if (ps[i].startsWith(":")) params[ps[i].slice(1)] = decodeURIComponent(xs[i]);
    else if (ps[i] !== xs[i]) return null;
  }
  return params;
}

const LATENCY = 120; // small artificial latency so loading states are visible

export async function handle(method: string, url: string, body?: Json): Promise<unknown> {
  const [path, search] = url.split("?");
  const query = new URLSearchParams(search ?? "");
  const db = getDb();
  for (const [m, pattern, fn] of routes) {
    if (m !== method.toUpperCase()) continue;
    const params = matchPath(pattern, path);
    if (!params) continue;
    await new Promise((r) => setTimeout(r, LATENCY));
    try {
      return fn(params, body ?? {}, query, db);
    } catch (e) {
      if (e instanceof HttpError) {
        const err: ApiError = { error: { code: e.code, message: e.message, status: e.status } };
        throw err;
      }
      throw e;
    }
  }
  const err: ApiError = { error: { code: "NOT_FOUND", message: `No route for ${method} ${path}`, status: 404 } };
  throw err;
}
