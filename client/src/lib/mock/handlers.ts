/**
 * Mock API server — implements the same REST surface as BACKEND SPEC §3
 * (backend/BACKEND_SPEC.md), route for route, including the error envelope.
 *
 * lib/api/http.ts dispatches here when NEXT_PUBLIC_API_URL is unset. When
 * the real backend exists, requests go over the network instead and this
 * file is dead code. Keep route patterns in sync with the spec.
 */

import { FEATURES, getDb, saveDb, uid, resetDb, type Db } from "./db";
import { detectGithubFull, toPreview, detectedToCreateBody } from "./github";
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
  Visibility,
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

// short device user_code chunk, ambiguity-free alphabet (matches the backend)
const rand4 = () =>
  Array.from({ length: 4 }, () => "ABCDEFGHJKMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 31)]).join("");

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

/* ---- plans & entitlements (mirrors backend/app/entitlements.py) ---- */

type Plan = "FREE" | "PRO" | "ENTERPRISE";
const PLAN_RANK: Record<Plan, number> = { FREE: 0, PRO: 1, ENTERPRISE: 2 };

interface PlanSpec {
  key: Plan;
  name: string;
  price_usd: number;
  max_orgs: number | null;
  resource_quota: number | null;
  mcp_included: boolean;
  tagline: string;
}
const PLAN_SPECS: Record<Plan, PlanSpec> = {
  FREE: { key: "FREE", name: "Free", price_usd: 0, max_orgs: 0, resource_quota: 100, mcp_included: false, tagline: "Publish as an individual. Up to 100 resources." },
  PRO: { key: "PRO", name: "Pro", price_usd: 20, max_orgs: 2, resource_quota: 500, mcp_included: true, tagline: "Up to 2 organizations, 500 resources each, MCP included." },
  ENTERPRISE: { key: "ENTERPRISE", name: "Enterprise", price_usd: 100, max_orgs: null, resource_quota: null, mcp_included: true, tagline: "Unlimited organizations and resources. MCP unlimited." },
};
const PLANS: Plan[] = ["FREE", "PRO", "ENTERPRISE"];

function normPlan(plan?: string | null): Plan {
  const p = String(plan ?? "").toUpperCase();
  if (p === "PREMIUM") return "ENTERPRISE"; // legacy binary tier → top tier
  return (PLANS as string[]).includes(p) ? (p as Plan) : "FREE";
}
const specFor = (plan?: string | null): PlanSpec => PLAN_SPECS[normPlan(plan)];
const planAtLeast = (plan: string | null | undefined, min: string) =>
  PLAN_RANK[normPlan(plan)] >= PLAN_RANK[normPlan(min)];

const payment_required = (message: string) => new HttpError(402, "PAYMENT_REQUIRED", message);

/** Resources homed anywhere in an org's subtree (ORG + its projects + pods). */
function orgResourceUsage(db: Db, orgId: string): number {
  const projectIds = db.projects.filter((p) => p.org_id === orgId).map((p) => p.id);
  const podIds = db.pods.filter((p) => projectIds.includes(p.project_id)).map((p) => p.id);
  return db.resources.filter(
    (r) =>
      (r.scope_type === "ORG" && r.scope_id === orgId) ||
      (r.scope_type === "PROJECT" && projectIds.includes(r.scope_id ?? "")) ||
      (r.scope_type === "POD" && podIds.includes(r.scope_id ?? ""))
  ).length;
}
const publisherUsage = (db: Db, userId: string): number =>
  db.resources.filter((r) => r.scope_type === "PUBLIC" && r.author_id === userId).length;
const userOrgCount = (db: Db, userId: string): number =>
  db.organizations.filter((o) => o.owner_id === userId).length;

function mcpIncludedForUser(db: Db, user: User): boolean {
  if (specFor(user.plan).mcp_included) return true;
  return db.org_members
    .filter((m) => m.user_id === user.id)
    .some((m) => specFor(db.organizations.find((o) => o.id === m.org_id)?.plan).mcp_included);
}

function userEntitlements(db: Db, user: User) {
  const spec = specFor(user.plan);
  return {
    plan: spec.key,
    plan_name: spec.name,
    publisher_resource_quota: spec.resource_quota,
    publisher_resource_used: publisherUsage(db, user.id),
    max_orgs: spec.max_orgs,
    orgs_owned: userOrgCount(db, user.id),
    mcp_included: mcpIncludedForUser(db, user),
  };
}
function orgEntitlements(db: Db, org: { id: string; plan?: string }) {
  const spec = specFor(org.plan);
  return {
    plan: spec.key,
    plan_name: spec.name,
    resource_quota: spec.resource_quota,
    resource_used: orgResourceUsage(db, org.id),
    mcp_included: spec.mcp_included,
  };
}
function planCatalog() {
  return PLANS.map((k) => {
    const s = PLAN_SPECS[k];
    return { key: s.key, name: s.name, price_usd: s.price_usd, max_orgs: s.max_orgs, resource_quota: s.resource_quota, mcp_included: s.mcp_included, tagline: s.tagline };
  });
}

function enforceCanCreateOrg(db: Db, user: User) {
  const spec = specFor(user.plan);
  if (spec.max_orgs === 0)
    throw payment_required("Creating organizations requires a paid plan. Upgrade to Pro to create up to 2 organizations.");
  if (spec.max_orgs !== null && userOrgCount(db, user.id) >= spec.max_orgs)
    throw payment_required(`Your ${spec.name} plan allows up to ${spec.max_orgs} organizations. Upgrade to Enterprise for unlimited organizations.`);
}

function enforceCanAddResource(db: Db, user: User, scopeType: string, scopeId: string | null) {
  if (scopeType === "PUBLIC") {
    const spec = specFor(user.plan);
    if (spec.resource_quota !== null && publisherUsage(db, user.id) >= spec.resource_quota)
      throw payment_required(`Your ${spec.name} plan allows up to ${spec.resource_quota} published resources. Upgrade to publish more.`);
    return;
  }
  const orgId = resolveOwningOrgId(db, scopeType, scopeId);
  if (!orgId) return;
  const org = db.organizations.find((o) => o.id === orgId);
  const spec = specFor(org?.plan);
  if (spec.resource_quota !== null && orgResourceUsage(db, orgId) >= spec.resource_quota)
    throw payment_required(`"${org?.name}" is on the ${spec.name} plan (limit ${spec.resource_quota} resources). Upgrade the organization to add more.`);
}

function resolveOwningOrgId(db: Db, scopeType: string, scopeId: string | null): string | null {
  if (scopeType === "ORG") return scopeId;
  if (scopeType === "PROJECT") return db.projects.find((p) => p.id === scopeId)?.org_id ?? null;
  if (scopeType === "POD") {
    const pod = db.pods.find((p) => p.id === scopeId);
    return db.projects.find((p) => p.id === pod?.project_id)?.org_id ?? null;
  }
  return null;
}

/* ---- resource review (mirrors backend/app/review.py) ---- */

function isOrgAdmin(db: Db, orgId: string | null, userId: string): boolean {
  if (!orgId) return false;
  return db.org_members.some((m) => m.org_id === orgId && m.user_id === userId && m.role === "ADMIN");
}
function canReview(db: Db, r: Resource, user: User): boolean {
  if (user.is_admin) return true;
  return isOrgAdmin(db, scopeOrgId(db, r), user.id);
}
function submitForReview(db: Db, r: Resource, actor: User) {
  // Personal (PUBLIC-scope) content is owner-governed — no review. Org content
  // auto-approves only for a reviewer (org/platform admin), else pends.
  if (r.scope_type === "PUBLIC" || canReview(db, r, actor)) {
    r.approval_status = "approved";
    r.review_note = null;
  } else {
    r.approval_status = "pending";
    r.review_note = null;
  }
}
function notifyAuthorOfReview(db: Db, r: Resource, actor: User, verb: "approved" | "rejected", note: string | null) {
  if (r.author_id === actor.id) return;
  db.notifications.unshift({
    id: uid("ntf"), actor_id: actor.id, org_id: scopeOrgId(db, r),
    scope_type: r.scope_type, scope_id: r.scope_id, verb, object_type: "resource",
    object_id: r.id, object_title: r.title, meta: note ?? null, read_at: null, created_at: now(),
  });
}
function approveResource(db: Db, r: Resource, reviewer: User) {
  r.approval_status = "approved";
  r.review_note = null;
  if (!r.is_public) r.is_public = true; // approving a queued item makes it live
  notifyAuthorOfReview(db, r, reviewer, "approved", null);
}
function rejectResource(db: Db, r: Resource, reviewer: User, note: string | null) {
  r.approval_status = "rejected";
  r.review_note = note;
  r.is_public = false; // rejected content is not live
  notifyAuthorOfReview(db, r, reviewer, "rejected", note);
}
const isPubliclyVisible = (r: Resource) => !!r.is_public && r.approval_status === "approved";

/** Resolve one org's feature flags: catalog defaults + overrides + plan (spec §2). */
function resolveFeatures(db: Db, orgId: string) {
  const org = db.organizations.find((o) => o.id === orgId);
  return FEATURES.map((f) => {
    const min_plan = f.min_plan ?? "FREE";
    const licensed = planAtLeast(org?.plan, min_plan);
    const override = db.org_features.find((x) => x.org_id === orgId && x.key === f.key);
    return {
      ...f,
      min_plan,
      premium: min_plan !== "FREE",
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

/* ---- integrations registry (mirrors backend/app/integrations.py) ---- */

const INTEGRATION_PROVIDERS = [
  {
    key: "github",
    name: "GitHub",
    tagline: "Turn your repositories into a living catalog of skills, MCP servers, and notes.",
    description:
      "Connect your organization's GitHub and SkillShare discovers resources from your repositories " +
      "automatically, keeps them in sync, and lets your team manage everything from Git. Import public " +
      "repos, keep private ones in sync, attach repos to resources, and search them straight from the CLI and MCP.",
    category: "Source Control",
    icon: "github",
    docs_url: "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens",
    auth_type: "pat" as const,
    min_plan: "PRO",
    feature_flag: null as string | null,
    status: "available" as const,
    sort_order: 10,
    enabled: true,
  },
  {
    key: "hive",
    name: "Hive",
    tagline: "Mirror your company's people and teams from Hive into your organization.",
    description:
      "Connect Hive (your HR & delivery system) and SkillShare keeps your organization in step with the " +
      "real company: import employees as members, map delivery projects to projects and teams to pods, and " +
      "keep membership current as people join, move, and leave. Connecting only fetches the directory for " +
      "review — nothing is added until you approve it, and imports never send bulk mail.",
    category: "HR & Directory",
    icon: "hive",
    docs_url: "https://hive.think41.com/",
    auth_type: "oauth" as const,
    min_plan: "ENTERPRISE",
    feature_flag: null as string | null,
    status: "available" as const,
    sort_order: 20,
    enabled: true,
  },
];

const AUTH_METHODS: Record<string, unknown[]> = {
  github: [
    {
      key: "classic_pat",
      name: "Personal Access Token (classic)",
      hint: "The quickest way to connect. Create a token with the scopes below.",
      docs_url: "https://github.com/settings/tokens/new",
      available: true,
      recommended: [
        { scope: "repo", why: "Read private repositories and push changes back", required: false },
        { scope: "read:org", why: "Discover your organization's repositories", required: false },
        { scope: "read:user", why: "Identify the connected account", required: true },
        { scope: "admin:repo_hook", why: "Receive repository events (live sync, coming soon)", required: false },
      ],
    },
    {
      key: "github_app",
      name: "GitHub App",
      hint: "Org-grade install with fine-grained per-repo access and webhooks.",
      available: false,
      status: "coming_soon",
      recommended: [],
    },
  ],
  hive: [
    {
      key: "oauth",
      name: "Sign in with Hive",
      hint: "Authorize SkillShare in your browser — sign in with an HR / allocation-manager account.",
      docs_url: "https://hive.think41.com/",
      available: true,
      recommended: [
        { scope: "employees:read", why: "Import employees as organization members", required: true },
        { scope: "delivery:read", why: "Map delivery projects to projects", required: false },
        { scope: "allocations:read", why: "Place people on the right project/pod", required: false },
        { scope: "groups:read", why: "Map teams to pods with their members", required: false },
      ],
    },
    {
      key: "service_token",
      name: "Paste a Hive token",
      hint: "Advanced / testing: paste a short-lived Hive access token and the tenant code.",
      available: true,
      recommended: [],
    },
  ],
};

const CAPABILITY_CATALOG: Record<string, { key: string; name: string; description: string; always?: boolean; scopes: string[]; recommend?: string }[]> = {
  github: [
    { key: "read_public", name: "Read public repositories", description: "Discover and read any public repository.", always: true, scopes: [] },
    { key: "search", name: "Search repositories", description: "Search across the connected account's repositories.", always: true, scopes: [] },
    { key: "read_org", name: "Read organization repositories", description: "List and read repositories owned by your organization.", scopes: ["read:org", "repo"], recommend: "read:org" },
    { key: "read_private", name: "Access private repositories", description: "Read private repositories and import their resources.", scopes: ["repo"], recommend: "repo" },
    { key: "write", name: "Push changes to GitHub", description: "Two-way / write-only sync back to repositories.", scopes: ["repo"], recommend: "repo" },
    { key: "webhooks", name: "Receive repository events", description: "Live sync on push/release via webhooks (coming soon).", scopes: ["admin:repo_hook"], recommend: "admin:repo_hook" },
  ],
  hive: [
    { key: "read_people", name: "Read employees", description: "Import employees as organization members and detect leavers.", always: true, scopes: [] },
    { key: "read_projects", name: "Read delivery projects", description: "Map Hive projects to SkillShare projects.", always: true, scopes: [] },
    { key: "read_allocations", name: "Read allocations", description: "Place people on the projects/pods they're allocated to.", always: true, scopes: [] },
    { key: "read_groups", name: "Read teams", description: "Map Hive groups/teams to pods with their members.", always: true, scopes: [] },
  ],
};

/* ---- hive staging (offline demo directory) ---- */
type HiveStaged = {
  id: string;
  kind: "employee" | "project" | "group";
  external_ref: string;
  email: string | null;
  display_name: string;
  status: "pending" | "applied" | "removed" | "skipped";
  payload: Record<string, unknown>;
  fetched_at: string | null;
  applied_at: string | null;
  member_refs?: string[];
};

const MOCK_HIVE_DIR: HiveStaged[] = [
  { id: "hst-m1", kind: "employee", external_ref: "m1", email: "alice@think41.com", display_name: "Alice Rao", status: "pending", payload: {}, fetched_at: null, applied_at: null },
  { id: "hst-m2", kind: "employee", external_ref: "m2", email: "bob@think41.com", display_name: "Bob Singh", status: "pending", payload: {}, fetched_at: null, applied_at: null },
  { id: "hst-m3", kind: "employee", external_ref: "m3", email: "carol@think41.com", display_name: "Carol Meyer", status: "pending", payload: {}, fetched_at: null, applied_at: null },
  { id: "hst-p1", kind: "project", external_ref: "p1", email: null, display_name: "Apollo", status: "pending", payload: {}, fetched_at: null, applied_at: null, member_refs: ["m1", "m2"] },
  { id: "hst-g1", kind: "group", external_ref: "g1", email: null, display_name: "Platform", status: "pending", payload: {}, fetched_at: null, applied_at: null, member_refs: ["m2", "m3"] },
];

function computeCaps(providerKey: string, scopes: string[]): string[] {
  const granted = new Set(scopes);
  return (CAPABILITY_CATALOG[providerKey] ?? [])
    .filter((c) => c.always || c.scopes.some((s) => granted.has(s)))
    .map((c) => c.key);
}

/** Mock scope detection: no real GitHub call, so derive scopes from the token —
 *  a token containing "limited" grants only read:user (demoes disabled features
 *  that Sync can later enable). */
function fakeScopes(token: string): string[] {
  return token.includes("limited") ? ["read:user"] : ["repo", "read:org", "read:user", "admin:repo_hook"];
}

type MockProvider = (typeof INTEGRATION_PROVIDERS)[number];
type MockConn = Db["org_integrations"][number];

function providerAvailable(db: Db, orgId: string, provider: MockProvider): boolean {
  const org = db.organizations.find((o) => o.id === orgId);
  if (!provider.enabled || !org) return false;
  if (!featureEnabled(db, orgId, "integrations")) return false;
  if (!planAtLeast(org.plan, provider.min_plan)) return false;
  if (provider.feature_flag && !featureEnabled(db, orgId, provider.feature_flag)) return false;
  return true;
}

function orgConnection(db: Db, orgId: string, key: string): MockConn | undefined {
  return db.org_integrations.find((c) => c.org_id === orgId && c.provider_key === key);
}

function capabilitiesOut(conn: MockConn) {
  const enabled = new Set(conn.capabilities ?? []);
  return (CAPABILITY_CATALOG[conn.provider_key] ?? []).map((c) => ({
    key: c.key,
    name: c.name,
    description: c.description,
    recommend: c.recommend ?? null,
    enabled: enabled.has(c.key),
  }));
}

function connectionOut(conn: MockConn | undefined) {
  if (!conn) return null;
  return {
    id: conn.id,
    provider_key: conn.provider_key,
    status: conn.status,
    auth_method: conn.auth_method,
    account_label: conn.account_label,
    account_type: conn.account_type,
    account_url: conn.account_url,
    account_avatar: conn.account_avatar,
    token_hint: conn.token_hint,
    scopes: conn.scopes ?? [],
    capabilities: capabilitiesOut(conn),
    config: conn.config ?? {},
    last_error: conn.last_error,
    connected_by: conn.connected_by,
    created_at: conn.created_at,
    updated_at: conn.updated_at,
    last_synced_at: conn.last_synced_at,
  };
}

function providerOut(provider: MockProvider, conn: MockConn | undefined) {
  return {
    key: provider.key,
    name: provider.name,
    tagline: provider.tagline,
    description: provider.description,
    category: provider.category,
    icon: provider.icon,
    docs_url: provider.docs_url,
    auth_type: provider.auth_type,
    status: provider.status,
    auth_methods: AUTH_METHODS[provider.key] ?? [],
    connected: !!conn && conn.status === "connected",
    connection: connectionOut(conn),
  };
}

type MockLink = Db["resource_repo_links"][number];

function linkOut(db: Db, link: MockLink) {
  const r = db.resources.find((x) => x.id === link.resource_id);
  return { ...link, resource_title: r?.title ?? null, resource_type: r?.type ?? null };
}

const repoSlug = (title: string) =>
  (title || "resource").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "resource";

/** Guard: org member (or admin) + the integrations feature must be on. */
function requireIntegrations(db: Db, slug: string, admin: boolean) {
  const org = orgBySlug(db, slug);
  const me = currentUser(db);
  const m = db.org_members.find((x) => x.org_id === org.id && x.user_id === me.id);
  if (!m) throw new HttpError(403, "FORBIDDEN", "You are not a member of this organization");
  if (admin && m.role !== "ADMIN")
    throw new HttpError(403, "FORBIDDEN", "Only org admins can do this");
  if (!featureEnabled(db, org.id, "integrations"))
    throw new HttpError(403, "FORBIDDEN", "Integrations are a premium feature — upgrade this organization to Pro");
  return { org, me };
}

function requireAvailableProvider(db: Db, orgId: string, key: string): MockProvider {
  const provider = INTEGRATION_PROVIDERS.find((p) => p.key === key);
  if (!provider || !providerAvailable(db, orgId, provider)) throw notFound(`Integration "${key}"`);
  return provider;
}

/** Deterministic fake repos so the GitHub search/list feel real in mock mode. */
function mockRepos(account: string, q: string, page = 1): unknown[] {
  if (page > 1) return []; // single mock page → "Load more" terminates cleanly
  const owner = account || "acme";
  const base = [
    { name: "awesome-mcp-server", description: "A streamable MCP server for vector search.", language: "Python", stars: 342, forks: 41, open_issues: 7, license: "MIT", topics: ["mcp", "ai"], private: false, archived: false, fork: false },
    { name: "skillshare-cli", description: "Command-line client and skill bundle.", language: "Python", stars: 88, forks: 9, open_issues: 2, license: "Apache-2.0", topics: ["cli", "skill"], private: false, archived: false, fork: false },
    { name: "terraform-gcp", description: "Reusable GCP infrastructure templates.", language: "HCL", stars: 51, forks: 15, open_issues: 0, license: "MPL-2.0", topics: ["template", "gcp"], private: false, archived: true, fork: false },
    { name: "backend-auth-service", description: "Internal auth microservice.", language: "Go", stars: 12, forks: 1, open_issues: 5, license: null, topics: ["service"], private: true, archived: false, fork: false },
    { name: "prompt-library", description: "Curated prompt collection for support agents.", language: "Markdown", stars: 27, forks: 3, open_issues: 1, license: "CC-BY-4.0", topics: ["prompts"], private: true, archived: false, fork: true },
  ];
  const needle = q.toLowerCase().trim();
  return base
    .filter((r) => !needle || r.name.includes(needle) || r.description.toLowerCase().includes(needle) || r.topics.some((t) => t.includes(needle)))
    .map((r) => ({
      full_name: `${owner}/${r.name}`,
      name: r.name,
      owner,
      description: r.description,
      private: r.private,
      archived: r.archived,
      fork: r.fork,
      language: r.language,
      stars: r.stars,
      forks: r.forks,
      open_issues: r.open_issues,
      license: r.license,
      homepage: null,
      topics: r.topics,
      html_url: `https://github.com/${owner}/${r.name}`,
      default_branch: "main",
      pushed_at: now(),
      updated_at: now(),
    }));
}

/* ---- membership: normalize / provision / cascade (mirrors permissions.py) ---- */

const ADMIN_ALIASES = ["ADMIN", "OWNER", "LEAD"];
const normRole = (role: unknown): "ADMIN" | "MEMBER" =>
  ADMIN_ALIASES.includes(String(role ?? "").toUpperCase()) ? "ADMIN" : "MEMBER";

function uniqueUsername(db: Db, base: string): string {
  const cand = base.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "user";
  let username = cand;
  let n = 1;
  while (db.users.some((u) => u.username === username)) username = `${cand}-${++n}`;
  return username;
}

/** Find by user_id/email, or auto-provision a brand-new account by email
 *  (must_change_password) — mirrors resolve_or_provision_user on the backend. */
function resolveOrProvision(db: Db, body: Json): User {
  if (body.user_id) {
    const u = db.users.find((x) => x.id === body.user_id);
    if (!u) throw notFound("User");
    return u;
  }
  const email = String(body.email ?? "").toLowerCase();
  if (!email) throw notFound("User");
  const found = db.users.find((x) => x.email === email);
  if (found) return found;
  const u: User = {
    id: uid("u"), email, username: uniqueUsername(db, email.split("@")[0]),
    display_name: email.split("@")[0], avatar_url: null, bio: "",
    is_publisher: false, must_change_password: true, created_at: now(), updated_at: now(),
  };
  db.users.push(u);
  return u;
}

function ensureOrgMember(db: Db, orgId: string, userId: string, role: OrgRole = "MEMBER") {
  let m = db.org_members.find((x) => x.org_id === orgId && x.user_id === userId);
  if (!m) {
    m = { id: uid("om"), org_id: orgId, user_id: userId, role, joined_at: now(), last_active: now() };
    db.org_members.push(m);
  }
  return m;
}
function ensureProjectMember(db: Db, projectId: string, userId: string, role = "MEMBER") {
  let m = db.project_members.find((x) => x.project_id === projectId && x.user_id === userId);
  if (!m) {
    m = { id: uid("pm"), project_id: projectId, user_id: userId, role: role as "LEAD" | "MEMBER" };
    db.project_members.push(m);
  }
  return m;
}
function ensurePodMember(db: Db, podId: string, userId: string, role = "MEMBER") {
  let m = db.pod_members.find((x) => x.pod_id === podId && x.user_id === userId);
  if (!m) {
    m = { id: uid("pdm"), pod_id: podId, user_id: userId, role: role as "OWNER" | "MEMBER" };
    db.pod_members.push(m);
  }
  return m;
}
const withUser = (m: { user_id: string }, db: Db) => ({ ...m, user: db.users.find((u) => u.id === m.user_id) });

// Resource audience (visibility) — mirrors backend/app/visibility.py.
const VIS_ALLOWED: Record<string, string[]> = {
  POD: ["POD", "PROJECT", "ORG"],
  PROJECT: ["PROJECT", "ORG"],
  ORG: ["ORG"],
  PUBLIC: ["ORG"],
};
const defaultVisibility = (scope: string): Visibility =>
  (({ POD: "POD", PROJECT: "PROJECT", ORG: "ORG" } as Record<string, Visibility>)[scope] ?? "ORG");
const normVisibility = (scope: string, vis?: string): Visibility => {
  const v = String(vis ?? "").toUpperCase();
  return (VIS_ALLOWED[scope] ?? ["ORG"]).includes(v) ? (v as Visibility) : defaultVisibility(scope);
};

/* ---------------- route table ---------------- */

// Mock-only in-memory stores for the two-step OTP flows (signup + password
// reset). The real backend keeps these in the DB; here a module Map is enough
// for a single browser session.
const _pendingSignups = new Map<string, { password: string; display_name: string; code: string }>();
const _pendingResets = new Map<string, string>(); // user id → code
const _mockOtp = () => String(Math.floor(100000 + Math.random() * 900000));

const routes: [method: string, pattern: string, fn: Handler][] = [
  /* ---- 3.1 Auth ---- */
  // Step 1: email a one-time code (mock returns it as dev_otp). No account yet.
  ["POST", "/api/auth/signup", (_p, body, _q, db) => {
    const email = String(body.email ?? "").toLowerCase();
    if (db.users.some((u) => u.email === email))
      throw new HttpError(409, "CONFLICT", "An account with this email already exists");
    const code = _mockOtp();
    _pendingSignups.set(email, {
      password: String(body.password ?? ""),
      display_name: String(body.display_name ?? email.split("@")[0]),
      code,
    });
    return { pending: true, email, email_sent: false, expires_in: 600, dev_otp: code };
  }],

  ["POST", "/api/auth/signup/resend", (_p, body) => {
    const email = String(body.email ?? "").toLowerCase();
    const p = _pendingSignups.get(email);
    if (!p) throw new HttpError(404, "NOT_FOUND", "No pending signup for this email — start again");
    p.code = _mockOtp();
    return { pending: true, email, email_sent: false, expires_in: 600, dev_otp: p.code };
  }],

  // Step 2: confirm the code → create the account and sign in.
  ["POST", "/api/auth/verify-email", (_p, body, _q, db) => {
    const email = String(body.email ?? "").toLowerCase();
    const p = _pendingSignups.get(email);
    if (!p) throw new HttpError(422, "VALIDATION_ERROR", "No pending signup for this email — start again");
    if (String(body.code ?? "").trim() !== p.code)
      throw new HttpError(401, "UNAUTHORIZED", "That code is incorrect");
    const username = p.display_name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    const user: User = {
      id: uid("u"),
      email,
      username,
      display_name: p.display_name || username,
      avatar_url: null,
      bio: "",
      is_publisher: false,
      // Verified via OTP and chose their own password → no forced-reset gate.
      must_change_password: false,
      created_at: now(),
      updated_at: now(),
    };
    db.users.push(user);
    db.session_user_id = user.id;
    _pendingSignups.delete(email);
    saveDb();
    return { user, access_token: "mock-access-token", refresh_token: "mock-refresh-token" };
  }],

  ["POST", "/api/auth/change-password", (_p, _b, _q, db) => {
    const me = currentUser(db);
    me.must_change_password = false;
    me.updated_at = now();
    saveDb();
    return me;
  }],

  // In-dashboard password reset via OTP (signed-in user).
  ["POST", "/api/auth/password/reset-otp", (_p, _b, _q, db) => {
    const me = currentUser(db);
    const code = _mockOtp();
    _pendingResets.set(me.id, code);
    return { pending: true, email: me.email, email_sent: false, expires_in: 600, dev_otp: code };
  }],

  ["POST", "/api/auth/password/reset-verify", (_p, body, _q, db) => {
    const me = currentUser(db);
    const code = _pendingResets.get(me.id);
    if (!code) throw new HttpError(422, "VALIDATION_ERROR", "Request a reset code first");
    if (String(body.code ?? "").trim() !== code)
      throw new HttpError(401, "UNAUTHORIZED", "That code is incorrect");
    me.must_change_password = false;
    me.updated_at = now();
    _pendingResets.delete(me.id);
    saveDb();
    return me;
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

  // Mock Google / Microsoft sign-in: no real id_token to verify, so sign in (or
  // fall back to) a demo account. The real backend verifies the token.
  ["POST", "/api/auth/google", (_p, _b, _q, db) => {
    const user = db.users.find((u) => u.id === "u-aniket") ?? db.users[0];
    if (!user) throw new HttpError(401, "UNAUTHORIZED", "No demo account available");
    db.session_user_id = user.id;
    saveDb();
    return { user, access_token: "mock-access-token", refresh_token: "mock-refresh-token" };
  }],

  ["POST", "/api/auth/microsoft", (_p, _b, _q, db) => {
    const user = db.users.find((u) => u.id === "u-aniket") ?? db.users[0];
    if (!user) throw new HttpError(401, "UNAUTHORIZED", "No demo account available");
    db.session_user_id = user.id;
    saveDb();
    return { user, access_token: "mock-access-token", refresh_token: "mock-refresh-token" };
  }],

  ["POST", "/api/auth/logout", (_p, _b, _q, db) => {
    db.session_user_id = null;
    saveDb();
    return { ok: true };
  }],

  // ---- device login (CLI/MCP browser approval) ----
  ["POST", "/api/auth/device/start", (_p, body, _q, db) => {
    db.device_auths ??= [];
    const userCode = `${rand4()}-${rand4()}`;
    const rec = {
      id: uid("dev"), device_code: uid("dc") + uid("dc"), user_code: userCode,
      client_name: String(body.client_name || "SkillShare CLI"),
      status: "pending" as const, user_id: null,
    };
    db.device_auths.push(rec);
    saveDb();
    return {
      device_code: rec.device_code, user_code: rec.user_code,
      verification_uri: "/activate",
      verification_uri_complete: `/activate?code=${rec.user_code}`,
      expires_in: 900, interval: 2,
    };
  }],

  ["POST", "/api/auth/device/token", (_p, body, _q, db) => {
    db.device_auths ??= [];
    const rec = db.device_auths.find((d) => d.device_code === body.device_code);
    if (!rec) throw notFound("Device session");
    if (rec.status === "denied") return { status: "denied" };
    if (rec.status !== "approved") return { status: "pending", interval: 2 };
    return { status: "approved", access_token: "mock-access-token", refresh_token: "mock-refresh-token", expires_in: 900, user: db.users.find((u) => u.id === rec.user_id) };
  }],

  ["GET", "/api/auth/device/:userCode", (p, _b, _q, db) => {
    db.device_auths ??= [];
    const rec = db.device_auths.find((d) => d.user_code === p.userCode.toUpperCase());
    if (!rec) throw notFound("Device session");
    currentUser(db); // must be signed in to view/approve
    return { client_name: rec.client_name, status: rec.status, created_at: now() };
  }],

  ["POST", "/api/auth/device/approve", (_p, body, _q, db) => {
    db.device_auths ??= [];
    const me = currentUser(db);
    const rec = db.device_auths.find((d) => d.user_code === String(body.user_code).toUpperCase());
    if (!rec) throw notFound("Device session");
    rec.status = "approved";
    rec.user_id = me.id;
    saveDb();
    return { ok: true, client_name: rec.client_name };
  }],

  ["POST", "/api/auth/device/deny", (_p, body, _q, db) => {
    db.device_auths ??= [];
    const me = currentUser(db);
    void me;
    const rec = db.device_auths.find((d) => d.user_code === String(body.user_code).toUpperCase());
    if (!rec) throw notFound("Device session");
    rec.status = "denied";
    saveDb();
    return { ok: true };
  }],

  ["GET", "/api/auth/me", (_p, _b, _q, db) => {
    const me = currentUser(db);
    // /me carries the plan (spec §2); default FREE for older seed rows.
    return { ...me, plan: normPlan(me.plan) };
  }],

  ["GET", "/api/auth/me/entitlements", (_p, _b, _q, db) => userEntitlements(db, currentUser(db))],

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
    enforceCanCreateOrg(db, me); // 402 for FREE users (spec §2)
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

  /* ---- entitlements & review queue (spec §2 / §3) ---- */
  ["GET", "/api/orgs/:slug/entitlements", (p, _b, _q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    if (!db.org_members.some((m) => m.org_id === org.id && m.user_id === me.id))
      throw new HttpError(403, "FORBIDDEN", "You are not a member of this organization");
    return orgEntitlements(db, org);
  }],

  ["GET", "/api/orgs/:slug/review-queue", (p, _b, q, db) => {
    const org = orgBySlug(db, p.slug);
    const me = currentUser(db);
    const membership = db.org_members.find((m) => m.org_id === org.id && m.user_id === me.id);
    if (membership?.role !== "ADMIN")
      throw new HttpError(403, "FORBIDDEN", "Only org admins can review resources");
    const status = q.get("status") ?? "pending";
    const projectIds = db.projects.filter((x) => x.org_id === org.id).map((x) => x.id);
    const podIds = db.pods.filter((x) => projectIds.includes(x.project_id)).map((x) => x.id);
    return db.resources
      .filter(
        (r) =>
          r.approval_status === status &&
          ((r.scope_type === "ORG" && r.scope_id === org.id) ||
            (r.scope_type === "PROJECT" && projectIds.includes(r.scope_id ?? "")) ||
            (r.scope_type === "POD" && podIds.includes(r.scope_id ?? "")))
      )
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map((r) => enrich(r, db));
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
    return { plan: org.plan, features: resolveFeatures(db, org.id), entitlements: orgEntitlements(db, org) };
  }],

  /* ---- integrations (org Integrations section) ----
   * Route order matters: literal /providers and /github/* before the dynamic
   * /:provider_key so they aren't captured as a provider key. */
  ["GET", "/api/orgs/:slug/integrations/providers", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    return INTEGRATION_PROVIDERS
      .filter((prov) => providerAvailable(db, org.id, prov))
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((prov) => providerOut(prov, orgConnection(db, org.id, prov.key)));
  }],

  ["GET", "/api/orgs/:slug/integrations/github/repos", (p, _b, q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    requireAvailableProvider(db, org.id, "github");
    const conn = orgConnection(db, org.id, "github");
    if (!conn || conn.status !== "connected") throw new HttpError(422, "VALIDATION_ERROR", "Connect GitHub first");
    return mockRepos(q.get("account") || conn.account_label || "", "");
  }],

  ["GET", "/api/orgs/:slug/integrations/github/search", (p, _b, q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    requireAvailableProvider(db, org.id, "github");
    const conn = orgConnection(db, org.id, "github");
    if (!conn || conn.status !== "connected") throw new HttpError(422, "VALIDATION_ERROR", "Connect GitHub first");
    return mockRepos(q.get("account") || conn.account_label || "", q.get("q") || "", Number(q.get("page") || "1"));
  }],

  ["GET", "/api/orgs/:slug/integrations/github/links", (p, _b, q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    let rows = db.resource_repo_links.filter((l) => l.org_id === org.id);
    const rid = q.get("resource_id");
    const repo = q.get("repo");
    if (rid) rows = rows.filter((l) => l.resource_id === rid);
    if (repo) rows = rows.filter((l) => l.repo_full_name === repo);
    return rows.map((l) => linkOut(db, l));
  }],

  ["POST", "/api/orgs/:slug/integrations/github/publish", (p, body, _q, db) => {
    const { org, me } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!conn || conn.status !== "connected") throw new HttpError(422, "VALIDATION_ERROR", "Connect GitHub first");
    if (!(conn.capabilities ?? []).includes("write"))
      throw new HttpError(403, "FORBIDDEN", "This connection can't write to GitHub — grant the 'repo' scope and Sync");
    const resource = db.resources.find((r) => r.id === body.resource_id);
    if (!resource) throw notFound("Resource");
    const account = conn.account_label || "acme";
    const explicit = String(body.repo_full_name ?? "").trim();
    const full = explicit || `${account}/${repoSlug(resource.title)}`;
    const managed = !explicit;
    const visibility: "public" | "private" = resource.is_public ? "public" : "private";
    let link = db.resource_repo_links.find((l) => l.resource_id === resource.id && l.repo_full_name === full);
    if (!link) {
      link = {
        id: uid("rrl"), org_id: org.id, resource_id: resource.id, provider_key: "github",
        repo_full_name: full, repo_url: `https://github.com/${full}`, path: String(body.path ?? ""),
        visibility, managed, direction: "write", last_pushed_at: now(), last_pulled_at: null, created_at: now(),
      };
      db.resource_repo_links.push(link);
    } else {
      link.visibility = visibility;
      link.last_pushed_at = now();
    }
    void me;
    saveDb();
    return linkOut(db, link);
  }],

  ["POST", "/api/orgs/:slug/integrations/github/push", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!(conn?.capabilities ?? []).includes("write"))
      throw new HttpError(403, "FORBIDDEN", "This connection can't write to GitHub — grant the 'repo' scope and Sync");
    const link = db.resource_repo_links.find((l) => l.org_id === org.id && l.resource_id === body.resource_id);
    if (!link) throw notFound("Repository link");
    link.last_pushed_at = now();
    saveDb();
    return linkOut(db, link);
  }],

  ["POST", "/api/orgs/:slug/integrations/github/pull", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const link = db.resource_repo_links.find((l) => l.org_id === org.id && l.resource_id === body.resource_id);
    if (!link) throw notFound("Repository link");
    const resource = db.resources.find((r) => r.id === body.resource_id);
    if (!resource) throw notFound("Resource");
    resource.description = `Synced from ${link.repo_full_name}`;
    resource.updated_at = now();
    link.last_pulled_at = now();
    saveDb();
    return enrich(resource, db);
  }],

  ["POST", "/api/orgs/:slug/integrations/github/link", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!conn || conn.status !== "connected") throw new HttpError(422, "VALIDATION_ERROR", "Connect GitHub first");
    const resource = db.resources.find((r) => r.id === body.resource_id);
    if (!resource) throw notFound("Resource");
    const full = String(body.repo_full_name ?? "").trim();
    let link = db.resource_repo_links.find((l) => l.resource_id === resource.id && l.repo_full_name === full);
    if (!link) {
      link = {
        id: uid("rrl"), org_id: org.id, resource_id: resource.id, provider_key: "github",
        repo_full_name: full, repo_url: `https://github.com/${full}`, path: String(body.path ?? ""),
        visibility: resource.is_public ? "public" : "private", managed: false, direction: "both",
        last_pushed_at: null, last_pulled_at: null, created_at: now(),
      };
      db.resource_repo_links.push(link);
    }
    saveDb();
    return linkOut(db, link);
  }],

  ["DELETE", "/api/orgs/:slug/integrations/github/links/:id", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const idx = db.resource_repo_links.findIndex((l) => l.id === p.id && l.org_id === org.id);
    if (idx >= 0) db.resource_repo_links.splice(idx, 1);
    saveDb();
    return { ok: true };
  }],

  ["POST", "/api/orgs/:slug/integrations/github/publish-scope", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!(conn?.capabilities ?? []).includes("write"))
      throw new HttpError(403, "FORBIDDEN", "This connection can't write to GitHub — grant the 'repo' scope and Sync");
    const account = conn?.account_label || "acme";
    const scopeType = String(body.scope_type ?? "ORG");
    const resources = db.resources.filter(
      (r) => scopeOrgId(db, r) === org.id && (scopeType === "ORG" || r.scope_id === body.scope_id)
    );
    let count = 0;
    for (const r of resources) {
      const full = `${account}/${repoSlug(r.title)}`;
      if (!db.resource_repo_links.find((l) => l.resource_id === r.id && l.repo_full_name === full)) {
        db.resource_repo_links.push({
          id: uid("rrl"), org_id: org.id, resource_id: r.id, provider_key: "github",
          repo_full_name: full, repo_url: `https://github.com/${full}`, path: "",
          visibility: r.is_public ? "public" : "private", managed: true, direction: "write",
          last_pushed_at: now(), last_pulled_at: null, created_at: now(),
        });
      }
      count++;
    }
    saveDb();
    return { published: [], count };
  }],

  ["POST", "/api/orgs/:slug/integrations/github/sync-all", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!(conn?.capabilities ?? []).includes("write"))
      throw new HttpError(403, "FORBIDDEN", "This connection can't write to GitHub — grant the 'repo' scope and Sync");
    let pushed = 0;
    for (const l of db.resource_repo_links.filter((l) => l.org_id === org.id)) {
      l.last_pushed_at = now();
      pushed++;
    }
    saveDb();
    return { pushed };
  }],

  ["GET", "/api/orgs/:slug/integrations/github/scope-links", (p, _b, q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    let rows = db.scope_repo_links.filter((l) => l.org_id === org.id);
    const st = q.get("scope_type");
    const sid = q.get("scope_id");
    if (st) rows = rows.filter((l) => l.scope_type === st);
    if (sid) rows = rows.filter((l) => l.scope_id === sid);
    return rows;
  }],

  ["POST", "/api/orgs/:slug/integrations/github/scope-links", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "github");
    if (!(conn?.capabilities ?? []).includes("write"))
      throw new HttpError(403, "FORBIDDEN", "This connection can't write to GitHub — grant the 'repo' scope and Sync");
    const st = String(body.scope_type ?? "ORG") as "ORG" | "PROJECT" | "POD";
    const sid = String(body.scope_id ?? "");
    const account = conn?.account_label || "acme";
    const route = String(body.visibility ?? "all") as "all" | "public" | "private";
    const wantsPrivate = route === "all" || route === "private";

    let full: string;
    let repoPrivate: boolean;
    const createName = String(body.create_repo_name ?? "").trim();
    if (createName) {
      full = `${account}/${createName}`;
      repoPrivate = body.create_private !== false || wantsPrivate; // forced private if holding private content
    } else {
      full = String(body.repo_full_name ?? "").trim();
      if (full.length < 3) throw new HttpError(422, "VALIDATION_ERROR", "Pick a repository or provide a name to create");
      const known = mockRepos(account, "").find((r) => (r as { full_name: string }).full_name === full) as { private?: boolean } | undefined;
      repoPrivate = known?.private ?? true; // unknown repos assumed private in mock
    }
    // Safety: a public repo can only route public resources.
    if (!repoPrivate && wantsPrivate)
      throw new HttpError(422, "VALIDATION_ERROR", "A public repository can only hold public resources. Attach a private repo or set the route to Public only.");

    const dir = String(body.sync_direction ?? "push") as "off" | "pull" | "push" | "both";
    let link = db.scope_repo_links.find((l) => l.org_id === org.id && l.scope_type === st && l.scope_id === sid && l.repo_full_name === full);
    if (!link) {
      link = {
        id: uid("srl"), org_id: org.id, scope_type: st, scope_id: sid, provider_key: "github",
        repo_full_name: full, repo_url: `https://github.com/${full}`, repo_private: repoPrivate,
        path_prefix: String(body.path_prefix ?? ""), visibility: route, sync_direction: dir,
        auto_sync: dir === "push" || dir === "both", last_synced_at: null, created_at: now(),
      };
      db.scope_repo_links.push(link);
    } else {
      link.visibility = route; link.sync_direction = dir; link.repo_private = repoPrivate;
      link.auto_sync = dir === "push" || dir === "both";
    }
    saveDb();
    return link;
  }],

  ["DELETE", "/api/orgs/:slug/integrations/github/scope-links/:id", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const idx = db.scope_repo_links.findIndex((l) => l.id === p.id && l.org_id === org.id);
    if (idx >= 0) db.scope_repo_links.splice(idx, 1);
    saveDb();
    return { ok: true };
  }],

  ["POST", "/api/orgs/:slug/integrations/github/scope-links/:id/sync", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const link = db.scope_repo_links.find((l) => l.id === p.id && l.org_id === org.id);
    if (!link) throw notFound("Scope link");
    // Mock: count resources in the scope that match the visibility filter.
    const inScope = db.resources.filter((r) => {
      if (link.scope_type === "ORG") return scopeOrgId(db, r) === org.id;
      return r.scope_type === link.scope_type && r.scope_id === link.scope_id;
    }).filter((r) => link.visibility === "all" || (link.visibility === "public" ? r.is_public : !r.is_public));
    link.last_synced_at = now();
    saveDb();
    const pushed = link.sync_direction === "push" || link.sync_direction === "both" ? inScope.length : 0;
    return { pushed, imported: 0 };
  }],

  /* ---- hive (HR/directory) — offline demo of fetch → review → apply ---- */
  ["POST", "/api/orgs/:slug/integrations/hive/oauth/start", (p, _b, q, db) => {
    const { org, me } = requireIntegrations(db, p.slug, true);
    const tenant = (q.get("tenant") ?? "").trim() || "think41";
    // Mock shortcut: "connect" immediately so the demo works without a real
    // Hive tab (the popup opens a harmless '#'), and stamp the tenant.
    let conn = orgConnection(db, org.id, "hive");
    if (!conn) {
      conn = {
        id: uid("oint"), org_id: org.id, provider_key: "hive", status: "connected",
        auth_method: "oauth", account_label: tenant, account_type: "Tenant",
        account_url: "https://hive.think41.com/", account_avatar: null,
        token_hint: "demo", scopes: [], capabilities: computeCaps("hive", []),
        config: { tenant }, last_error: null, last_synced_at: null, connected_by: me.id,
        created_at: now(), updated_at: now(),
      };
      db.org_integrations.push(conn);
    } else {
      conn.status = "connected"; conn.config = { ...(conn.config ?? {}), tenant }; conn.updated_at = now();
    }
    saveDb();
    return { authorize_url: "#hive-mock-connected" };
  }],

  ["POST", "/api/orgs/:slug/integrations/hive/fetch", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "hive");
    if (!conn) throw new HttpError(422, "VALIDATION_ERROR", "Connect Hive first");
    const staged = MOCK_HIVE_DIR.map((e) => {
      const prev = (conn.config?.hive_staged as HiveStaged[] | undefined)?.find((s) => s.external_ref === e.external_ref && s.kind === e.kind);
      return { ...e, status: prev?.status === "applied" ? "applied" : "pending" } as HiveStaged;
    });
    conn.config = { ...(conn.config ?? {}), hive_staged: staged };
    conn.last_synced_at = now();
    conn.updated_at = now();
    saveDb();
    const c = (s: string) => staged.filter((x) => x.status === s).length;
    return {
      members: staged.filter((s) => s.kind === "employee").length,
      projects: staged.filter((s) => s.kind === "project").length,
      groups: staged.filter((s) => s.kind === "group").length,
      allocations: 2, pending_count: c("pending"), applied_count: c("applied"), removed_count: c("removed"),
    };
  }],

  ["GET", "/api/orgs/:slug/integrations/hive/staged", (p, _b, q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    const conn = orgConnection(db, org.id, "hive");
    const statusFilter = q.get("status");
    const staged = ((conn?.config?.hive_staged as HiveStaged[]) ?? []).filter(
      (s) => !statusFilter || s.status === statusFilter
    );
    const groups = { employee: [] as HiveStaged[], project: [] as HiveStaged[], group: [] as HiveStaged[] };
    for (const s of staged) groups[s.kind].push(s);
    const cnt = (st: string) => ((conn?.config?.hive_staged as HiveStaged[]) ?? []).filter((s) => s.status === st).length;
    return { groups, counts: { pending: cnt("pending"), applied: cnt("applied"), removed: cnt("removed"), skipped: cnt("skipped") } };
  }],

  ["POST", "/api/orgs/:slug/integrations/hive/apply", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const conn = orgConnection(db, org.id, "hive");
    if (!conn) throw new HttpError(422, "VALIDATION_ERROR", "Connect Hive first");
    const scope = String(body.scope ?? "all");
    const refs = new Set((body.refs as string[] | undefined) ?? []);
    const createStructure = body.create_structure !== false;
    const staged = (conn.config?.hive_staged as HiveStaged[]) ?? [];
    const res = { members_added: 0, projects_created: 0, pods_created: 0, memberships_added: 0, offboarded: 0 };
    const want = (k: HiveStaged["kind"]) =>
      (scope === "all" || (scope === "members" && k === "employee") || (scope === "projects" && k === "project") || (scope === "groups" && k === "group"));
    const userFor = (ref: string): User | undefined => {
      const emp = staged.find((s) => s.kind === "employee" && s.external_ref === ref);
      if (!emp?.email) return undefined;
      const u = resolveOrProvision(db, { email: emp.email });
      ensureOrgMember(db, org.id, u.id);
      if (emp.status === "pending") { emp.status = "applied"; res.members_added += 1; }
      return u;
    };
    for (const s of staged) {
      if (s.status !== "pending" || !want(s.kind)) continue;
      if (refs.size && !refs.has(s.external_ref)) continue;
      if (s.kind === "employee") { userFor(s.external_ref); }
    }
    if (createStructure && (scope === "all" || scope === "projects")) {
      for (const s of staged.filter((x) => x.kind === "project" && x.status === "pending" && (!refs.size || refs.has(x.external_ref)))) {
        const proj = { id: uid("proj"), org_id: org.id, name: s.display_name, description: "", tags: [], visibility: "ORG" as const, created_by: org.owner_id, created_at: now() };
        db.projects.push(proj); res.projects_created += 1;
        for (const mref of (s.member_refs ?? [])) { const u = userFor(mref); if (u) { ensureProjectMember(db, proj.id, u.id); res.memberships_added += 1; } }
        s.status = "applied";
      }
    }
    if (createStructure && (scope === "all" || scope === "groups")) {
      const teamRows = staged.filter((x) => x.kind === "group" && x.status === "pending" && (!refs.size || refs.has(x.external_ref)));
      if (teamRows.length) {
        let teams = db.projects.find((x) => x.org_id === org.id && x.name === "Teams (from Hive)");
        if (!teams) { teams = { id: uid("proj"), org_id: org.id, name: "Teams (from Hive)", description: "Teams synced from Hive.", tags: [], visibility: "ORG" as const, created_by: org.owner_id, created_at: now() }; db.projects.push(teams); }
        for (const s of teamRows) {
          const pod = { id: uid("pod"), project_id: teams.id, name: s.display_name, description: "", purpose_tag: "", created_by: org.owner_id, created_at: now() };
          db.pods.push(pod); res.pods_created += 1;
          for (const mref of (s.member_refs ?? [])) { const u = userFor(mref); if (u) { ensureProjectMember(db, teams.id, u.id); ensurePodMember(db, pod.id, u.id); res.memberships_added += 1; } }
          s.status = "applied";
        }
      }
    }
    conn.updated_at = now();
    saveDb();
    return res;
  }],

  ["GET", "/api/orgs/:slug/integrations", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    return db.org_integrations.filter((c) => c.org_id === org.id).map((c) => connectionOut(c));
  }],

  ["GET", "/api/orgs/:slug/integrations/:provider", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, false);
    const provider = requireAvailableProvider(db, org.id, p.provider);
    return providerOut(provider, orgConnection(db, org.id, p.provider));
  }],

  ["POST", "/api/orgs/:slug/integrations/:provider/connect", (p, body, _q, db) => {
    const { org, me } = requireIntegrations(db, p.slug, true);
    const provider = requireAvailableProvider(db, org.id, p.provider);
    const token = String(body.token ?? "").trim();
    if (token.length < 10) throw new HttpError(422, "VALIDATION_ERROR", "That doesn't look like a valid token");
    const method = String(body.auth_method ?? "classic_pat");
    const m = (AUTH_METHODS[p.provider] as { key: string; available: boolean; name: string }[] ?? []).find((x) => x.key === method);
    if (!m) throw new HttpError(422, "VALIDATION_ERROR", `Unknown connection method '${method}'`);
    if (!m.available) throw new HttpError(422, "VALIDATION_ERROR", `${m.name} isn't available yet`);
    const account = String(body.account ?? "").trim() || "acme";
    const scopes = fakeScopes(token);
    let conn = orgConnection(db, org.id, p.provider);
    if (!conn) {
      conn = {
        id: uid("oint"), org_id: org.id, provider_key: p.provider, status: "connected",
        auth_method: method, account_label: account, account_type: "Organization",
        account_url: `https://github.com/${account}`, account_avatar: null,
        token_hint: token.slice(-4), scopes, capabilities: computeCaps(p.provider, scopes),
        config: {}, last_error: null, last_synced_at: now(), connected_by: me.id,
        created_at: now(), updated_at: now(),
      };
      db.org_integrations.push(conn);
    } else {
      conn.status = "connected";
      conn.auth_method = method;
      conn.account_label = account;
      conn.account_url = `https://github.com/${account}`;
      conn.token_hint = token.slice(-4);
      conn.scopes = scopes;
      conn.capabilities = computeCaps(p.provider, scopes);
      conn.last_error = null;
      conn.last_synced_at = now();
      conn.updated_at = now();
    }
    saveDb();
    return providerOut(provider, conn);
  }],

  ["POST", "/api/orgs/:slug/integrations/:provider/sync", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const provider = requireAvailableProvider(db, org.id, p.provider);
    const conn = orgConnection(db, org.id, p.provider);
    if (!conn) throw notFound(`${provider.name} connection`);
    // Mock: re-detect from the "same token" — grant full scopes on sync so the
    // enable-on-sync flow is demonstrable (a limited connect → full after sync).
    conn.scopes = ["repo", "read:org", "read:user", "admin:repo_hook"];
    conn.capabilities = computeCaps(p.provider, conn.scopes);
    conn.status = "connected";
    conn.last_error = null;
    conn.last_synced_at = now();
    conn.updated_at = now();
    saveDb();
    return providerOut(provider, conn);
  }],

  ["PATCH", "/api/orgs/:slug/integrations/:provider", (p, body, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const provider = requireAvailableProvider(db, org.id, p.provider);
    const conn = orgConnection(db, org.id, p.provider);
    if (!conn) throw notFound(`${provider.name} connection`);
    conn.config = { ...(conn.config ?? {}), ...((body.config as Record<string, unknown>) ?? {}) };
    conn.updated_at = now();
    saveDb();
    return providerOut(provider, conn);
  }],

  ["DELETE", "/api/orgs/:slug/integrations/:provider", (p, _b, _q, db) => {
    const { org } = requireIntegrations(db, p.slug, true);
    const idx = db.org_integrations.findIndex((c) => c.org_id === org.id && c.provider_key === p.provider);
    if (idx >= 0) db.org_integrations.splice(idx, 1);
    saveDb();
    return { ok: true };
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
          isPubliclyVisible(r) &&
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
    db.project_members.push({ id: uid("pm"), project_id: project.id, user_id: me.id, role: "ADMIN" });
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

  // Member management is id-addressed (shared with CLI/MCP). Add by user_id OR
  // email (unknown email → auto-provision); adding cascades org membership.
  ["GET", "/api/projects/:projectId/members", (p, _b, _q, db) =>
    db.project_members.filter((m) => m.project_id === p.projectId).map((m) => withUser(m, db)),
  ],

  ["POST", "/api/projects/:projectId/members", (p, body, _q, db) => {
    const project = db.projects.find((x) => x.id === p.projectId);
    if (!project) throw notFound("Project");
    const target = resolveOrProvision(db, body);
    const role = normRole(body.role);
    ensureOrgMember(db, project.org_id, target.id);
    const m = ensureProjectMember(db, project.id, target.id, role);
    m.role = role as "LEAD" | "MEMBER";
    saveDb();
    return withUser(m, db);
  }],

  ["PATCH", "/api/projects/:projectId/members/:userId", (p, body, _q, db) => {
    const m = db.project_members.find((x) => x.project_id === p.projectId && x.user_id === p.userId);
    if (!m) throw notFound("Member");
    m.role = normRole(body.role) as "LEAD" | "MEMBER";
    saveDb();
    return withUser(m, db);
  }],

  ["DELETE", "/api/projects/:projectId/members/:userId", (p, _b, _q, db) => {
    const podIds = db.pods.filter((x) => x.project_id === p.projectId).map((x) => x.id);
    db.pod_members = db.pod_members.filter((m) => !(podIds.includes(m.pod_id) && m.user_id === p.userId));
    db.project_members = db.project_members.filter((m) => !(m.project_id === p.projectId && m.user_id === p.userId));
    saveDb();
    return { ok: true };
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
    db.pod_members.push({ id: uid("pdm"), pod_id: pod.id, user_id: me.id, role: "ADMIN" });
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

  ["GET", "/api/pods/:podId/members", (p, _b, _q, db) =>
    db.pod_members.filter((m) => m.pod_id === p.podId).map((m) => withUser(m, db)),
  ],

  ["POST", "/api/pods/:podId/members", (p, body, _q, db) => {
    const pod = db.pods.find((x) => x.id === p.podId);
    if (!pod) throw notFound("Pod");
    const project = db.projects.find((x) => x.id === pod.project_id);
    if (!project) throw notFound("Project");
    const target = resolveOrProvision(db, body);
    const role = normRole(body.role);
    // Cascade: pod ⇒ project ⇒ org, each as MEMBER (only the pod row gets `role`).
    ensureOrgMember(db, project.org_id, target.id);
    ensureProjectMember(db, project.id, target.id);
    const m = ensurePodMember(db, pod.id, target.id, role);
    m.role = role as "OWNER" | "MEMBER";
    saveDb();
    return withUser(m, db);
  }],

  ["PATCH", "/api/pods/:podId/members/:userId", (p, body, _q, db) => {
    const m = db.pod_members.find((x) => x.pod_id === p.podId && x.user_id === p.userId);
    if (!m) throw notFound("Member");
    m.role = normRole(body.role) as "OWNER" | "MEMBER";
    saveDb();
    return withUser(m, db);
  }],

  ["DELETE", "/api/pods/:podId/members/:userId", (p, _b, _q, db) => {
    db.pod_members = db.pod_members.filter((m) => !(m.pod_id === p.podId && m.user_id === p.userId));
    saveDb();
    return { ok: true };
  }],

  /* ---- 3.5 Resources ---- */
  ["POST", "/api/resources", (_p, body, _q, db) => {
    const me = currentUser(db);
    const title = String(body.title ?? "").trim();
    if (!title) throw new HttpError(422, "VALIDATION_ERROR", "Title is required");
    const scopeType = body.scope_type as ScopeType;
    // PUBLIC = the publisher's own marketplace shelf: no org/scope_id, gated on
    // being a registered publisher (mirrors the backend).
    if (scopeType === "PUBLIC" && !me.is_publisher)
      throw new HttpError(403, "FORBIDDEN", "Become a publisher first to add resources to the marketplace");
    enforceCanAddResource(db, me, scopeType, (body.scope_id as string) ?? null); // plan/quota gate (spec §2)
    const isPublic = scopeType === "PUBLIC";
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
      scope_type: scopeType,
      scope_id: isPublic ? null : ((body.scope_id as string) ?? null),
      visibility: normVisibility(scopeType, body.visibility as string | undefined),
      author_id: me.id,
      // Created UNPUBLISHED — a private draft its author owns. The author
      // publishes explicitly afterwards (mirrors the backend).
      is_public: false,
      approval_status: "approved",
      review_note: null,
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
    // Re-validate audience against the (possibly new) scope.
    r.visibility = normVisibility(r.scope_type, (body.visibility as string | undefined) ?? r.visibility);
    // Editing a rejected-but-still-public resource resubmits it for review (§3).
    if (r.is_public && r.approval_status === "rejected") submitForReview(db, r, me);
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "updated", object_type: "resource", object_id: r.id, object_title: r.title, meta: `v${r.version}` });
    saveDb();
    return enrich(r, db);
  }],

  ["POST", "/api/resources/:id/move", (p, body, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    const scopeType = String(body.scope_type ?? "");
    if (!["ORG", "PROJECT", "POD"].includes(scopeType)) throw new HttpError(422, "VALIDATION_ERROR", "scope_type must be ORG, PROJECT, or POD");
    if (!body.scope_id) throw new HttpError(422, "VALIDATION_ERROR", "scope_id is required");
    r.scope_type = scopeType as ScopeType;
    r.scope_id = String(body.scope_id);
    r.visibility = normVisibility(scopeType, body.visibility as string | undefined);
    r.updated_at = now();
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "updated", object_type: "resource", object_id: r.id, object_title: r.title, meta: "moved" });
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
    // A publisher can always publish a resource they authored. The premium
    // "publishing" feature gates publishing *other people's* org resources.
    if (r.author_id !== me.id && !featureEnabled(db, scopeOrgId(db, r), "publishing"))
      throw new HttpError(403, "FORBIDDEN", "Marketplace publishing is disabled for this organization");
    const wasVisible = isPubliclyVisible(r);
    r.is_public = true;
    r.updated_at = now();
    // Enter review (spec §3): org content → org admin, publisher content →
    // platform admin. Auto-approved when the actor is already its reviewer.
    submitForReview(db, r, me);
    const orgId = scopeOrgId(db, r);
    if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "published", object_type: "resource", object_id: r.id, object_title: r.title });
    // Notify the author's followers only on the transition to publicly visible
    // (approved). The mock inbox is single-user (no recipient field), so we add
    // one entry per follow; in seed only Ada has a follower (the demo user).
    if (isPubliclyVisible(r) && !wasVisible) {
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

  // Approve / reject a resource submitted for public listing (spec §3).
  ["POST", "/api/resources/:id/review", (p, body, _q, db) => {
    const me = currentUser(db);
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    if (!canReview(db, r, me))
      throw new HttpError(403, "FORBIDDEN", "You don't have review authority over this resource");
    const decision = String(body.decision ?? "").trim().toLowerCase();
    if (decision === "approve") approveResource(db, r, me);
    else if (decision === "reject") rejectResource(db, r, me, (String(body.note ?? "").trim()) || null);
    else throw new HttpError(422, "VALIDATION_ERROR", 'decision must be "approve" or "reject"');
    r.updated_at = now();
    saveDb();
    return enrich(r, db);
  }],

  // Usage ping — records an install/use (spec §7).
  ["POST", "/api/resources/:id/use", (p, _b, _q, db) => {
    const me = currentUser(db);
    void me;
    const r = db.resources.find((x) => x.id === p.id);
    if (!r) throw notFound("Resource");
    // Dashboard source doesn't bump installs (only cli/mcp do on the backend).
    return { ok: true, installs_count: r.installs_count ?? 0 };
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

  // GitHub-URL ingestion — declared BEFORE /api/resources/:id/import so "github"
  // isn't captured as a resource id by the dynamic route.
  ["POST", "/api/resources/github/preview", async (_p, body) => {
    const det = await detectGithubFull(String(body.url ?? ""));
    return toPreview(det);
  }],

  ["POST", "/api/resources/github/import", async (_p, body, _q, db) => {
    const me = currentUser(db);
    if (!["ORG", "PROJECT", "POD", "PUBLIC"].includes(String(body.scope_type)))
      throw new HttpError(422, "VALIDATION_ERROR", "scope_type must be ORG, PROJECT, POD, or PUBLIC");
    const det = await detectGithubFull(String(body.url ?? ""));
    const select = (body.select as string[]) ?? [];
    let items = det.items;
    if (select.length) {
      const wanted = new Set(select);
      items = items.filter((i) => wanted.has(i.fingerprint));
    }
    if (!items.length)
      throw new HttpError(422, "VALIDATION_ERROR", "No skills, MCP servers, or notes were detected in that repository");

    const scope_type = body.scope_type as ScopeType;
    const scope_id = (body.scope_id as string) ?? null;
    const created: Resource[] = [];
    const skipped: { title: string; fingerprint: string; reason: string; resource_id?: string }[] = [];
    for (const it of items) {
      const existing = db.resources.find(
        (r) => r.source_fingerprint === it.fingerprint && r.scope_type === scope_type && r.scope_id === scope_id
      );
      if (existing) {
        skipped.push({ title: it.title, fingerprint: it.fingerprint, reason: "already imported", resource_id: existing.id });
        continue;
      }
      const b = detectedToCreateBody(it);
      const r: Resource = {
        id: uid("res"),
        type: b.type,
        title: b.title.slice(0, 120),
        description: b.description,
        content_md: b.content_md,
        server_url: b.server_url,
        config_json: b.config_json,
        file_url: null,
        version: "0.1.0",
        tags: b.tags,
        attachments: b.attachments,
        scope_type,
        scope_id,
        author_id: me.id,
        is_public: false,
        stars_count: 0,
        source_fingerprint: b.source_fingerprint,
        created_at: now(),
        updated_at: now(),
      };
      db.resources.push(r);
      const orgId = scopeOrgId(db, r);
      if (orgId) logActivity(db, { user_id: me.id, org_id: orgId, verb: "created", object_type: "resource", object_id: r.id, object_title: r.title, meta: "imported from GitHub" });
      created.push(r);
    }
    saveDb();
    return { created: created.map((r) => enrich(r, db)), skipped, repo: { owner: det.repo.owner, repo: det.repo.repo } };
  }],

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
    filterResources(db.resources.filter(isPubliclyVisible), q, db),
  ],

  ["GET", "/api/public/resources/:id", (p, _b, _q, db) => {
    const r = db.resources.find((x) => x.id === p.id && isPubliclyVisible(x));
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
        .filter((r) => isPubliclyVisible(r) && r.author_id === user.id)
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
    filterResources(db.resources.filter(isPubliclyVisible), q, db),
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

  /* ---- billing (spec §5; scaffolded, disabled by default) ---- */
  ["GET", "/api/billing/config", () => ({
    enabled: false,
    key_id: null,
    provider: "razorpay",
    currency: "USD",
    plans: planCatalog(),
  })],

  ["POST", "/api/billing/checkout", (_p, body, _q, db) => {
    const me = currentUser(db);
    const plan = normPlan(body.plan as string);
    if (plan === "FREE") throw new HttpError(422, "VALIDATION_ERROR", "plan must be PRO or ENTERPRISE");
    if (body.target_type === "org") {
      if (!body.org_slug) throw new HttpError(422, "VALIDATION_ERROR", "org_slug is required when target_type is 'org'");
      const org = orgBySlug(db, String(body.org_slug));
      const m = db.org_members.find((x) => x.org_id === org.id && x.user_id === me.id);
      if (m?.role !== "ADMIN") throw new HttpError(403, "FORBIDDEN", "Only org admins can upgrade the organization");
    }
    // Online upgrades are disabled until Razorpay keys are configured (spec §5).
    throw new HttpError(503, "SERVICE_UNAVAILABLE", "Online upgrades aren't available yet. Ask a platform admin to grant your plan in the meantime.");
  }],

  ["GET", "/api/billing/subscription", (_p, _b, _q, db) => {
    const me = currentUser(db);
    const owned = db.organizations.filter((o) => o.owner_id === me.id);
    return {
      user: userEntitlements(db, me),
      orgs: owned.map((o) => ({ slug: o.slug, name: o.name, ...orgEntitlements(db, o) })),
      payments: (db.payments ?? []).filter((p) => p.target_id === me.id || owned.some((o) => o.id === p.target_id)),
    };
  }],

  /* ---- platform admin (User.is_admin) ---- */
  ["GET", "/api/admin/resources", (_p, _b, q, db) => {
    requireAdmin(db);
    const status = q.get("status") ?? "pending";
    return db.resources
      .filter((r) => r.approval_status === status)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .map((r) => enrich(r, db));
  }],

  ["GET", "/api/admin/feedback", (_p, _b, q, db) => {
    requireAdmin(db);
    const status = q.get("status");
    return (db.feedback ?? [])
      .filter((f) => (status === "open" || status === "reviewed" ? f.status === status : true))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((f) => ({ ...f, user: db.users.find((u) => u.id === f.user_id) }));
  }],

  ["POST", "/api/admin/feedback/:id/moderate", (p, body, _q, db) => {
    requireAdmin(db);
    const fb = (db.feedback ?? []).find((f) => f.id === p.id);
    if (!fb) throw notFound("Feedback");
    fb.public_status = body.decision === "approve" ? "approved" : "rejected";
    fb.updated_at = now();
    saveDb();
    return { ...fb, user: db.users.find((u) => u.id === fb.user_id) };
  }],

  ["POST", "/api/admin/feedback/:id/status", (p, body, _q, db) => {
    requireAdmin(db);
    const fb = (db.feedback ?? []).find((f) => f.id === p.id);
    if (!fb) throw notFound("Feedback");
    fb.status = body.status === "open" ? "open" : "reviewed";
    fb.updated_at = now();
    saveDb();
    return { ...fb, user: db.users.find((u) => u.id === fb.user_id) };
  }],

  ["PATCH", "/api/admin/users/:username/plan", (p, body, _q, db) => {
    requireAdmin(db);
    const u = db.users.find((x) => x.username === p.username);
    if (!u) throw notFound("User");
    const plan = normPlan(body.plan as string);
    u.plan = plan;
    u.updated_at = now();
    saveDb();
    return userEntitlements(db, u);
  }],

  ["PATCH", "/api/admin/orgs/:slug/plan", (p, body, _q, db) => {
    requireAdmin(db);
    const org = orgBySlug(db, p.slug);
    org.plan = normPlan(body.plan as string);
    saveDb();
    return orgEntitlements(db, org);
  }],

  /* ---- dev convenience ---- */
  ["POST", "/api/dev/reset", () => {
    resetDb();
    return { ok: true };
  }],
];

function requireAdmin(db: Db): User {
  const me = currentUser(db);
  if (!me.is_admin) throw new HttpError(403, "FORBIDDEN", "Platform admin access required");
  return me;
}

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
      return await fn(params, body ?? {}, query, db);
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
