/**
 * Data models — mirror BACKEND SPEC §2 exactly (see backend/BACKEND_SPEC.md).
 * When the real API lands these types stay; only the transport changes
 * (see lib/api/http.ts).
 */

export type ResourceType = "SKILL" | "MCP" | "NOTE";
export type ScopeType = "ORG" | "PROJECT" | "POD" | "PUBLIC";
export type OrgRole = "ADMIN" | "MEMBER";
export type ProjectRole = "LEAD" | "MEMBER";
export type PodRole = "OWNER" | "MEMBER";
export type ProjectVisibility = "ORG" | "PUBLIC";

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
  created_at: string;
  updated_at: string;
}

export type PlanTier = "FREE" | "PREMIUM";

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
  terminology?: Terminology;
  created_at: string;
}

/** Feature flag catalog entry (global definition). */
export interface FeatureFlag {
  key: string;
  name: string;
  description: string;
  /** premium flags require an org license to enable */
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
  author_id: string;
  is_public: boolean;
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
  verb: "created" | "published";
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
