/**
 * Data models — mirror BACKEND SPEC §2 exactly (see backend/BACKEND_SPEC.md).
 * When the real API lands these types stay; only the transport changes
 * (see lib/api/http.ts).
 */

export type ResourceType = "SKILL" | "MCP" | "NOTE";
/** Public-listing review state (spec §3). Only `approved` + `is_public`
 *  resources appear on public read paths. */
export type ApprovalStatus = "pending" | "approved" | "rejected";
export type ScopeType = "ORG" | "PROJECT" | "POD" | "PUBLIC";
// Every scope speaks the same two roles. Legacy rows (LEAD/OWNER) are still
// accepted by the API and normalized to ADMIN, so the union stays permissive.
export type ScopeRole = "ADMIN" | "MEMBER";
export type OrgRole = ScopeRole;
export type ProjectRole = ScopeRole | "LEAD";
export type PodRole = ScopeRole | "OWNER";
export type ProjectVisibility = "ORG" | "PUBLIC";
// Resource audience: who can read it. Narrowest is POD (only the owning pod's
// members); widen to PROJECT or ORG to share further. See backend visibility.py.
export type Visibility = "POD" | "PROJECT" | "ORG";

export interface User {
  id: string;
  email: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string;
  /** GitHub-style profile extras */
  location?: string;
  website?: string;
  is_publisher: boolean;
  verified?: boolean;
  /** Personal/publisher plan tier (spec §2). Present on the /me payload. */
  plan?: Plan;
  /** Platform admin — only present on the self (/me) payload. */
  is_admin?: boolean;
  /** Set for first-time accounts; the dashboard forces a password change until
   *  cleared via POST /api/auth/change-password. */
  must_change_password?: boolean;
  created_at: string;
  updated_at: string;
}

/** Plan ladder (spec §2). Two billable entities share it: a user's personal /
 *  publisher space (User.plan) and each Organization (Organization.plan). */
export type Plan = "FREE" | "PRO" | "ENTERPRISE";
/** `PREMIUM` is the legacy binary tier (old license flow); the backend
 *  normalizes it to ENTERPRISE. Kept in the union so old rows still type-check. */
export type PlanTier = Plan | "PREMIUM";

/** Personal / publisher-space entitlements (GET /api/auth/me/entitlements). */
export interface UserEntitlements {
  plan: Plan;
  plan_name: string;
  publisher_resource_quota: number | null;
  publisher_resource_used: number;
  max_orgs: number | null;
  orgs_owned: number;
  mcp_included: boolean;
}

/** Per-org entitlements (GET /api/orgs/{slug}/entitlements). */
export interface OrgEntitlements {
  plan: Plan;
  plan_name: string;
  resource_quota: number | null;
  resource_used: number;
  mcp_included: boolean;
}

/** Public pricing entry (billing config / marketing pricing page). */
export interface BillingPlan {
  key: Plan;
  name: string;
  price_usd: number;
  max_orgs: number | null;
  resource_quota: number | null;
  mcp_included: boolean;
  tagline: string;
}

/** Billing/checkout config (GET /api/billing/config). Scaffolded/disabled until
 *  Razorpay keys are set — `enabled:false` means the UI shows "coming soon". */
export interface BillingConfig {
  enabled: boolean;
  key_id: string | null;
  provider: string;
  currency: string;
  plans: BillingPlan[];
}

export interface Payment {
  id: string;
  target_type: "user" | "org";
  target_id: string;
  plan: Plan;
  amount: number;
  currency: string;
  status: "created" | "paid" | "failed";
  provider: string;
  created_at: string;
}

/** GET /api/billing/subscription — current plans + recent payments. */
export interface BillingSubscription {
  user: UserEntitlements;
  orgs: (OrgEntitlements & { slug: string; name: string })[];
  payments: Payment[];
}

/** Org-facing labels for the hierarchy. Data model stays projects → pods;
 *  orgs that think in "Teams" relabel the UI (premium: custom-terminology). */
export interface Terminology {
  project: string;
  pod: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  logo_url: string | null;
  description: string;
  is_public: boolean;
  owner_id: string;
  plan: PlanTier;
  plan_name?: string;
  terminology?: Terminology;
  created_at: string;
}

/** Feature flag catalog entry (global definition). */
export interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  /** Minimum plan that unlocks the flag (spec §2). `premium` is derived from
   *  this (= min_plan !== "FREE") and kept for older clients. */
  min_plan?: Plan;
  /** premium flags require a paid plan to enable */
  premium: boolean;
  default_enabled: boolean;
}

/** A flag resolved for one org (what the client consumes). */
export interface OrgFeature extends FeatureFlag {
  enabled: boolean;
  /** false when premium and the org has no license — toggle is locked */
  licensed: boolean;
}

export interface OrgMember {
  id: string;
  org_id: string;
  user_id: string;
  role: OrgRole;
  joined_at: string;
  user?: User;
  /** convenience for the members table */
  last_active?: string;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  description: string;
  tags: string[];
  visibility: ProjectVisibility;
  created_by: string;
  created_at: string;
  /** denormalized counts returned by the API for list views */
  pods_count?: number;
  members_count?: number;
  resources_count?: number;
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: ProjectRole;
  user?: User;
}

export interface Pod {
  id: string;
  project_id: string;
  name: string;
  description: string;
  purpose_tag: string;
  created_by: string;
  created_at: string;
  members_count?: number;
  resources_count?: number;
}

export interface PodMember {
  id: string;
  pod_id: string;
  user_id: string;
  role: PodRole;
  user?: User;
}

export type AttachmentKind = "link" | "image" | "video" | "file";

/** Typed media attached to a resource (hybrid content model). content_md
 *  stays the canonical prose; attachments add structured media items. */
export interface Attachment {
  kind: AttachmentKind;
  url: string;
  title?: string | null;
  caption?: string | null;
}

export interface Resource {
  id: string;
  type: ResourceType;
  title: string;
  description: string;
  content_md: string;
  attachments?: Attachment[];
  /** MCP-only structured fields (serialized into content for v1 API parity) */
  server_url?: string;
  config_json?: string;
  file_url: string | null;
  version: string;
  tags: string[];
  scope_type: ScopeType;
  scope_id: string | null;
  /** Audience — who can read it: POD | PROJECT | ORG (see backend visibility). */
  visibility?: Visibility;
  author_id: string;
  is_public: boolean;
  /** Public-listing review state (spec §3). */
  approval_status?: ApprovalStatus;
  /** Reviewer's note, set when rejected. */
  review_note?: string | null;
  stars_count: number;
  installs_count?: number;
  /** stable hash of the source artifact (local push or GitHub import) */
  source_fingerprint?: string;
  created_at: string;
  updated_at: string;
  /** added by the API on scoped list endpoints (BACKEND SPEC §5) */
  scope_label?: ScopeType;
  /** human-readable name of the owning scope (org/project/pod), from the API */
  scope_name?: string | null;
  author?: User;
  starred_by_me?: boolean;
  /** true when the signed-in user has pinned this to their profile */
  pinned_by_me?: boolean;
}

/** GitHub-style contribution heatmap (profile). One bucket per day. */
export interface ContributionDay {
  date: string; // YYYY-MM-DD
  count: number;
}
export interface Contributions {
  weeks: number;
  start: string;
  end: string;
  total: number;
  max: number;
  days: ContributionDay[];
}

export interface Invitation {
  id: string;
  org_id: string;
  email: string;
  role: OrgRole;
  token: string;
  expires_at: string;
  accepted_at: string | null;
}

/** Product feedback — a rating + message users send from the dashboard, CLI,
 *  or MCP. Either general ("platform") or about a specific resource. */
export type FeedbackCategory =
  | "bug"
  | "idea"
  | "praise"
  | "question"
  | "other"
  | "general";

export interface FeedbackInput {
  message: string;
  rating?: number | null;
  category?: FeedbackCategory;
  target_type?: "platform" | "resource";
  target_id?: string | null;
  source?: "dashboard" | "cli" | "mcp";
  context?: Record<string, unknown> | null;
}

export interface Feedback {
  id: string;
  user_id: string;
  target_type: "platform" | "resource";
  target_id: string | null;
  target?: { id: string; title: string | null; type: string | null } | null;
  rating: number | null;
  category: FeedbackCategory;
  message: string;
  source: "dashboard" | "cli" | "mcp";
  context?: Record<string, unknown> | null;
  status: "open" | "reviewed";
  /** Admin moderation decision for public display on the website (spec §4). */
  public_status?: "pending" | "approved" | "rejected";
  created_at: string;
  updated_at: string;
  user?: User;
}

/** BACKEND SPEC §7 — error envelope */
export interface ApiError {
  error: {
    code:
      | "UNAUTHORIZED"
      | "FORBIDDEN"
      | "NOT_FOUND"
      | "VALIDATION_ERROR"
      | "CONFLICT"
      | "PAYMENT_REQUIRED"
      | "SERVICE_UNAVAILABLE"
      | "INTERNAL_ERROR";
    message: string;
    status: number;
  };
}

export interface AuthSession {
  user: User;
  access_token: string;
  refresh_token?: string;
}

/** Response to signup / password-reset step 1: a code was emailed (or, when
 *  email delivery isn't configured, returned as `dev_otp` so the flow still
 *  works). No session yet — the caller must confirm the code. */
export interface SignupPending {
  pending: boolean;
  email: string;
  email_sent: boolean;
  expires_in: number;
  dev_otp?: string;
}

/** Activity feed (dashboard home + profile) */
export interface Activity {
  id: string;
  user_id: string;
  org_id: string;
  verb: "created" | "updated" | "published" | "starred" | "joined" | "invited";
  object_type: "resource" | "project" | "pod" | "org" | "member";
  object_id: string;
  object_title: string;
  meta?: string;
  created_at: string;
  user?: User;
}

/** Notification inbox (F1) — resources added/published in scopes you belong to. */
export interface Notification {
  id: string;
  actor_id: string;
  /** null for follower notifications about a PUBLIC-scoped resource */
  org_id: string | null;
  scope_type: ScopeType;
  scope_id: string | null;
  verb: "created" | "published" | "approved" | "rejected";
  object_type: "resource";
  object_id: string;
  object_title: string;
  meta?: string | null;
  read_at: string | null;
  created_at: string;
  actor?: User;
  deep_link?: string | null;
  install_command?: string | null;
}

/* ---- Integrations (org Integrations section) ---- */

/** A capability the connection may unlock, with whether the current credential
 *  grants it and what to grant if not. Features gate on `enabled`. */
export interface IntegrationCapability {
  key: string;
  name: string;
  description: string;
  recommend: string | null;
  enabled: boolean;
}

/** A recommended permission for a connection method. */
export interface RecommendedPermission {
  scope: string;
  why: string;
  required: boolean;
}

/** A way to connect a provider (e.g. classic PAT). `available:false` → coming soon. */
export interface IntegrationAuthMethod {
  key: string;
  name: string;
  hint: string;
  docs_url?: string;
  available: boolean;
  status?: string;
  recommended: RecommendedPermission[];
}

/** A per-org connection to a provider. Never carries the secret token — only a
 *  masked hint (last 4 chars) and non-secret metadata. */
export interface IntegrationConnection {
  id: string;
  provider_key: string;
  status: "connected" | "error" | "disconnected";
  auth_method: string;
  account_label: string | null;
  account_type: string | null;
  account_url: string | null;
  account_avatar: string | null;
  token_hint: string | null;
  scopes: string[];
  capabilities: IntegrationCapability[];
  config: Record<string, unknown>;
  last_error: string | null;
  connected_by: string;
  created_at: string | null;
  updated_at: string | null;
  last_synced_at: string | null;
}

/** A connectable integration (GitHub, …) annotated with this org's connection. */
export interface IntegrationProvider {
  key: string;
  name: string;
  tagline: string;
  description: string;
  category: string;
  icon: string;
  docs_url: string | null;
  auth_type: "pat" | "oauth" | "app";
  status: "available" | "beta" | "coming_soon";
  auth_methods: IntegrationAuthMethod[];
  connected: boolean;
  connection: IntegrationConnection | null;
}

/** A link between a SkillShare resource and a GitHub repo (publish/attach). */
export interface ResourceRepoLink {
  id: string;
  resource_id: string;
  resource_title: string | null;
  resource_type: string | null;
  provider_key: string;
  repo_full_name: string;
  repo_url: string | null;
  path: string;
  visibility: "public" | "private";
  managed: boolean;
  direction: string;
  last_pushed_at: string | null;
  last_pulled_at: string | null;
  created_at: string | null;
}

/** A repo attached to a scope (org/team/pod). Resources in the scope whose
 *  visibility matches auto-sync to it. A scope can have many. */
export interface ScopeRepoLink {
  id: string;
  scope_type: "ORG" | "PROJECT" | "POD";
  scope_id: string;
  provider_key: string;
  repo_full_name: string;
  repo_url: string | null;
  path_prefix: string;
  visibility: "all" | "public" | "private";
  auto_sync: boolean;
  last_synced_at: string | null;
  created_at: string | null;
}

/** A repository summary returned by the GitHub integration search/list. */
export interface GithubRepo {
  full_name: string;
  name: string;
  owner: string | null;
  description: string;
  private: boolean;
  archived: boolean;
  fork: boolean;
  language: string | null;
  stars: number;
  forks: number;
  open_issues: number;
  license: string | null;
  homepage: string | null;
  topics: string[];
  html_url: string | null;
  default_branch: string;
  pushed_at: string | null;
  updated_at: string | null;
}
