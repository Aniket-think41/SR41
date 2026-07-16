/**
 * Typed API client — one function per endpoint in backend/BACKEND_SPEC.md §3.
 * Screens never call fetch directly; they call these via React Query.
 */

import { request, requestList, uploadAvatar, uploadFile, uploadOrgLogo } from "./http";
import type {
  Activity,
  Attachment,
  AuthSession,
  SignupPending,
  BillingConfig,
  BillingSubscription,
  Contributions,
  Feedback,
  FeedbackInput,
  GithubRepo,
  IntegrationProvider,
  ResourceRepoLink,
  Invitation,
  Notification,
  OrgEntitlements,
  OrgFeature,
  Plan,
  PlanTier,
  Terminology,
  Organization,
  OrgMember,
  OrgRole,
  Pod,
  PodMember,
  Project,
  ProjectMember,
  Resource,
  ResourceType,
  ScopeType,
  User,
  UserEntitlements,
} from "../types";

export type OrgWithRole = Organization & {
  my_role: OrgRole;
  followers_count?: number;
  following?: boolean;
};
export type PublisherProfile = User & {
  resources: Resource[];
  followers_count: number;
  following: boolean;
};
export type UserProfile = User & {
  stats: {
    resources: number;
    public_resources: number;
    stars_received: number;
    stars_given: number;
    orgs: number;
    followers: number;
    following: number;
  };
};

export interface GithubDetected {
  kind: "skill" | "mcp" | "note";
  type: ResourceType;
  title: string;
  description: string;
  tags: string[];
  source_path: string;
  fingerprint: string;
  redaction: string[];
  server_url?: string | null;
  has_config: boolean;
  content_preview: string;
  attachments: Attachment[];
}
export interface GithubPreview {
  repo: { owner: string; repo: string; ref: string | null; description: string; html_url: string };
  detected: GithubDetected[];
}
export interface GithubImportResult {
  created: Resource[];
  skipped: { title: string; fingerprint: string; reason: string; resource_id?: string }[];
  repo: { owner: string; repo: string };
}

export interface DeviceInfo {
  client_name: string;
  status: "pending" | "approved" | "denied" | "expired";
  created_at: string;
}

export interface ResourceQuery {
  q?: string;
  type?: ResourceType | "ALL";
  tag?: string;
  sort?: "relevance" | "updated" | "newest" | "stars" | "installs";
  scope?: "all" | "pod" | "project" | "org";
  /** marketplace: filter by publisher (org name or author display name) */
  publisher?: string;
  /** marketplace pagination */
  limit?: number;
  offset?: number;
}

/** A page of resources plus the server's total count (from X-Total-Count),
 *  so the marketplace can fetch one page at a time instead of everything. */
export interface ResourcePage {
  items: Resource[];
  total: number;
}

export interface MarketplaceFacets {
  tags: [string, number][];
  publishers: string[];
}

/** Review-queue filter (spec §3). */
export type ApprovalFilter = "pending" | "approved" | "rejected";

const qs = (params: Record<string, string | number | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  /* ---- auth ---- */
  // Signup is a two-step, email-verified flow: `signup` emails a one-time code
  // and returns a pending payload (no session); `verifyEmail` confirms the code
  // and creates the account, returning the session.
  signup: (body: { email: string; password: string; display_name: string }) =>
    request<SignupPending>("POST", "/api/auth/signup", body),
  verifyEmail: (body: { email: string; code: string }) =>
    request<AuthSession>("POST", "/api/auth/verify-email", body),
  resendSignupOtp: (email: string) =>
    request<SignupPending>("POST", "/api/auth/signup/resend", { email }),
  login: (body: { email: string; password: string }) =>
    request<AuthSession>("POST", "/api/auth/login", body),
  google: (idToken: string) => request<AuthSession>("POST", "/api/auth/google", { id_token: idToken }),
  microsoft: (idToken: string) => request<AuthSession>("POST", "/api/auth/microsoft", { id_token: idToken }),
  logout: () => request<{ ok: true }>("POST", "/api/auth/logout"),
  me: () => request<User>("GET", "/api/auth/me"),
  /** Personal / publisher-space plan, quotas, usage (spec §2). */
  myEntitlements: () => request<UserEntitlements>("GET", "/api/auth/me/entitlements"),
  changePassword: (body: { current_password?: string; new_password: string }) =>
    request<User>("POST", "/api/auth/change-password", body),
  // In-dashboard password reset via email OTP (for a signed-in user): request a
  // code to your own inbox, then verify it with the new password.
  startPasswordReset: () =>
    request<SignupPending>("POST", "/api/auth/password/reset-otp", {}),
  verifyPasswordReset: (body: { code: string; new_password: string }) =>
    request<User>("POST", "/api/auth/password/reset-verify", body),

  /* ---- device login (CLI / MCP browser approval) ---- */
  deviceInfo: (userCode: string) =>
    request<DeviceInfo>("GET", `/api/auth/device/${encodeURIComponent(userCode)}`),
  deviceApprove: (userCode: string) =>
    request<{ ok: true; client_name: string }>("POST", "/api/auth/device/approve", { user_code: userCode }),
  deviceDeny: (userCode: string) =>
    request<{ ok: true }>("POST", "/api/auth/device/deny", { user_code: userCode }),
  updateMe: (body: Partial<User>) => request<User>("PATCH", "/api/auth/me", body),
  uploadAvatar: (file: File) => uploadAvatar(file),

  /* ---- orgs ---- */
  myOrgs: () => request<OrgWithRole[]>("GET", "/api/orgs"),
  createOrg: (body: { name: string; slug?: string; description?: string }) =>
    request<Organization>("POST", "/api/orgs", body),
  org: (slug: string) => request<OrgWithRole>("GET", `/api/orgs/${slug}`),
  updateOrg: (slug: string, body: Partial<Organization> & { terminology?: Terminology | null }) =>
    request<Organization>("PATCH", `/api/orgs/${slug}`, body),
  uploadOrgLogo: (slug: string, file: File) => uploadOrgLogo(slug, file),
  /** Per-org plan, quota, and current resource usage (spec §2). */
  orgEntitlements: (slug: string) =>
    request<OrgEntitlements>("GET", `/api/orgs/${slug}/entitlements`),
  orgFeatures: (slug: string) => request<OrgFeature[]>("GET", `/api/orgs/${slug}/features`),
  setFeature: (slug: string, key: string, enabled: boolean) =>
    request<OrgFeature>("PATCH", `/api/orgs/${slug}/features/${key}`, { enabled }),
  activateLicense: (slug: string, licenseKey: string) =>
    request<{ plan: PlanTier; features: OrgFeature[] }>("POST", `/api/orgs/${slug}/license`, {
      license_key: licenseKey,
    }),
  join: (slug: string, token: string) =>
    request<{ ok: true }>("POST", `/api/orgs/${slug}/join/${token}`),
  orgMembers: (slug: string) => request<OrgMember[]>("GET", `/api/orgs/${slug}/members`),
  invite: (slug: string, body: { email: string; role: OrgRole }) =>
    request<Invitation>("POST", `/api/orgs/${slug}/invite`, body),
  invitations: (slug: string) => request<Invitation[]>("GET", `/api/orgs/${slug}/invitations`),
  cancelInvitation: (slug: string, invId: string) =>
    request<{ ok: true }>("DELETE", `/api/orgs/${slug}/invitations/${invId}`),
  removeMember: (slug: string, userId: string) =>
    request<{ ok: true }>("DELETE", `/api/orgs/${slug}/members/${userId}`),
  setMemberRole: (slug: string, userId: string, role: OrgRole) =>
    request<OrgMember>("PATCH", `/api/orgs/${slug}/members/${userId}`, { role }),
  orgActivity: (slug: string) => request<Activity[]>("GET", `/api/orgs/${slug}/activity`),
  orgPublished: (slug: string) => request<Resource[]>("GET", `/api/orgs/${slug}/published`),
  followOrg: (slug: string) =>
    request<{ following: boolean; followers_count: number }>("POST", `/api/orgs/${slug}/follow`),
  unfollowOrg: (slug: string) =>
    request<{ following: boolean; followers_count: number }>("DELETE", `/api/orgs/${slug}/follow`),
  orgSearch: (slug: string, q: string) =>
    request<{ resources: Resource[]; projects: Project[]; pods: Pod[]; members: User[] }>(
      "GET",
      `/api/orgs/${slug}/search${qs({ q })}`
    ),
  /** Org-admin review queue: org-owned resources awaiting a public-listing
   *  decision (spec §3). status = pending | approved | rejected. */
  orgReviewQueue: (slug: string, status: ApprovalFilter = "pending") =>
    request<Resource[]>("GET", `/api/orgs/${slug}/review-queue${qs({ status })}`),

  /* ---- integrations (premium; org Integrations section) ---- */
  /** Integration cards available to this org, each with its connection state. */
  integrationProviders: (slug: string) =>
    request<IntegrationProvider[]>("GET", `/api/orgs/${slug}/integrations/providers`),
  /** One provider + this org's connection (config page). */
  integration: (slug: string, provider: string) =>
    request<IntegrationProvider>("GET", `/api/orgs/${slug}/integrations/${provider}`),
  /** Connect a provider by supplying credentials (validated + encrypted server-side). */
  connectIntegration: (
    slug: string,
    provider: string,
    body: { token: string; account?: string; auth_method?: string }
  ) => request<IntegrationProvider>("POST", `/api/orgs/${slug}/integrations/${provider}/connect`, body),
  /** Re-check the stored credential: refresh account metadata + granted scopes/
   *  capabilities (picks up newly-granted permissions without re-entering the token). */
  syncIntegration: (slug: string, provider: string) =>
    request<IntegrationProvider>("POST", `/api/orgs/${slug}/integrations/${provider}/sync`),
  /** Update a connection's non-secret settings (e.g. default sync mode). */
  updateIntegrationConfig: (slug: string, provider: string, config: Record<string, unknown>) =>
    request<IntegrationProvider>("PATCH", `/api/orgs/${slug}/integrations/${provider}`, { config }),
  disconnectIntegration: (slug: string, provider: string) =>
    request<{ ok: true }>("DELETE", `/api/orgs/${slug}/integrations/${provider}`),
  /** List repositories visible to the connected GitHub account. */
  githubIntegrationRepos: (slug: string, account?: string) =>
    request<GithubRepo[]>("GET", `/api/orgs/${slug}/integrations/github/repos${qs({ account })}`),
  /** Search GitHub repositories (scoped to the connected account by default). */
  githubIntegrationSearch: (slug: string, q: string, account?: string, page = 1) =>
    request<GithubRepo[]>(
      "GET",
      `/api/orgs/${slug}/integrations/github/search${qs({ q, account, page: String(page) })}`
    ),
  /* ---- publish / attach / sync (SkillShare ⇄ GitHub) ---- */
  githubLinks: (slug: string, opts: { resource_id?: string; repo?: string } = {}) =>
    request<ResourceRepoLink[]>("GET", `/api/orgs/${slug}/integrations/github/links${qs(opts)}`),
  /** Publish a resource to GitHub. Omit repo_full_name → managed repo mirroring
   *  the resource's visibility (public → public repo, private → private). */
  githubPublish: (slug: string, body: { resource_id: string; repo_full_name?: string; path?: string }) =>
    request<ResourceRepoLink>("POST", `/api/orgs/${slug}/integrations/github/publish`, body),
  /** Re-push a linked resource's content to its repo (write sync). */
  githubPush: (slug: string, resourceId: string) =>
    request<ResourceRepoLink>("POST", `/api/orgs/${slug}/integrations/github/push`, { resource_id: resourceId }),
  /** Pull the linked repo's content back into the resource (read sync). */
  githubPull: (slug: string, resourceId: string) =>
    request<Resource>("POST", `/api/orgs/${slug}/integrations/github/pull`, { resource_id: resourceId }),
  /** Attach an existing repo to a resource without pushing. */
  githubLinkRepo: (slug: string, body: { resource_id: string; repo_full_name: string; path?: string }) =>
    request<ResourceRepoLink>("POST", `/api/orgs/${slug}/integrations/github/link`, body),
  githubUnlink: (slug: string, linkId: string) =>
    request<{ ok: true }>("DELETE", `/api/orgs/${slug}/integrations/github/links/${linkId}`),

  /* ---- projects ---- */
  projects: (slug: string) => request<Project[]>("GET", `/api/orgs/${slug}/projects`),
  createProject: (slug: string, body: { name: string; description?: string; tags?: string[] }) =>
    request<Project>("POST", `/api/orgs/${slug}/projects`, body),
  project: (slug: string, projectId: string) =>
    request<Project>("GET", `/api/orgs/${slug}/projects/${projectId}`),
  updateProject: (slug: string, projectId: string, body: Partial<Project>) =>
    request<Project>("PATCH", `/api/orgs/${slug}/projects/${projectId}`, body),
  deleteProject: (slug: string, projectId: string) =>
    request<{ ok: true }>("DELETE", `/api/orgs/${slug}/projects/${projectId}`),
  // Member management is id-addressed (shared with CLI/MCP). Add by user_id OR
  // email — an unknown email auto-provisions the account and cascades membership.
  projectMembers: (projectId: string) =>
    request<ProjectMember[]>("GET", `/api/projects/${projectId}/members`),
  addProjectMember: (projectId: string, body: { user_id?: string; email?: string; role?: string }) =>
    request<ProjectMember>("POST", `/api/projects/${projectId}/members`, body),
  setProjectMemberRole: (projectId: string, userId: string, role: string) =>
    request<ProjectMember>("PATCH", `/api/projects/${projectId}/members/${userId}`, { role }),
  removeProjectMember: (projectId: string, userId: string) =>
    request<{ ok: true }>("DELETE", `/api/projects/${projectId}/members/${userId}`),

  /* ---- pods ---- */
  pods: (projectId: string) => request<Pod[]>("GET", `/api/projects/${projectId}/pods`),
  createPod: (projectId: string, body: { name: string; description?: string; purpose_tag?: string }) =>
    request<Pod>("POST", `/api/projects/${projectId}/pods`, body),
  pod: (projectId: string, podId: string) =>
    request<Pod>("GET", `/api/projects/${projectId}/pods/${podId}`),
  updatePod: (projectId: string, podId: string, body: Partial<Pod>) =>
    request<Pod>("PATCH", `/api/projects/${projectId}/pods/${podId}`, body),
  deletePod: (projectId: string, podId: string) =>
    request<{ ok: true }>("DELETE", `/api/projects/${projectId}/pods/${podId}`),
  podMembers: (podId: string) =>
    request<PodMember[]>("GET", `/api/pods/${podId}/members`),
  addPodMember: (podId: string, body: { user_id?: string; email?: string; role?: string }) =>
    request<PodMember>("POST", `/api/pods/${podId}/members`, body),
  setPodMemberRole: (podId: string, userId: string, role: string) =>
    request<PodMember>("PATCH", `/api/pods/${podId}/members/${userId}`, { role }),
  removePodMember: (podId: string, userId: string) =>
    request<{ ok: true }>("DELETE", `/api/pods/${podId}/members/${userId}`),

  /* ---- resources ---- */
  createResource: (body: {
    type: ResourceType;
    title: string;
    description?: string;
    content_md?: string;
    server_url?: string;
    config_json?: string;
    file_url?: string | null;
    version?: string;
    tags?: string[];
    scope_type: ScopeType;
    scope_id: string | null;
    visibility?: string;
  }) => request<Resource>("POST", "/api/resources", body),
  resource: (id: string) => request<Resource>("GET", `/api/resources/${id}`),
  updateResource: (id: string, body: Partial<Resource>) =>
    request<Resource>("PATCH", `/api/resources/${id}`, body),
  moveResource: (id: string, body: { scope_type: ScopeType; scope_id: string | null; visibility?: string }) =>
    request<Resource>("POST", `/api/resources/${id}/move`, body),
  deleteResource: (id: string) => request<{ ok: true }>("DELETE", `/api/resources/${id}`),
  orgResources: (slug: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/orgs/${slug}/resources${qs(query as Record<string, string>)}`),
  projectResources: (projectId: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/projects/${projectId}/resources${qs(query as Record<string, string>)}`),
  podResources: (podId: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/pods/${podId}/resources${qs(query as Record<string, string>)}`),
  publish: (id: string) => request<Resource>("POST", `/api/resources/${id}/publish`),
  unpublish: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/publish`),
  /** Approve/reject a resource submitted for public listing (spec §3). */
  reviewResource: (id: string, body: { decision: "approve" | "reject"; note?: string }) =>
    request<Resource>("POST", `/api/resources/${id}/review`, body),
  /** Usage ping — records an install/use (spec §7). */
  useResource: (id: string) =>
    request<{ ok: boolean; installs_count: number }>("POST", `/api/resources/${id}/use`),
  star: (id: string) => request<Resource>("POST", `/api/resources/${id}/star`),
  unstar: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/star`),
  pin: (id: string) => request<Resource>("POST", `/api/resources/${id}/pin`),
  unpin: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/pin`),
  upload: (filename: string) =>
    request<{ file_url: string }>("POST", "/api/resources/upload", { filename }),
  uploadFile: (file: File, kind: "image" | "video" | "file") => uploadFile(file, kind),
  importResource: (id: string, orgSlug: string) =>
    request<Resource>("POST", `/api/resources/${id}/import`, { org_slug: orgSlug }),

  /* ---- GitHub-URL ingestion ---- */
  githubPreview: (url: string) =>
    request<GithubPreview>("POST", "/api/resources/github/preview", { url }),
  githubImport: (body: { url: string; scope_type: ScopeType; scope_id: string | null; select?: string[] }) =>
    request<GithubImportResult>("POST", "/api/resources/github/import", body),

  /* ---- notifications (F1) ---- */
  notifications: (opts: { unreadOnly?: boolean; limit?: number } = {}) =>
    request<Notification[]>(
      "GET",
      `/api/notifications${qs({
        unread_only: opts.unreadOnly ? "true" : undefined,
        limit: opts.limit ? String(opts.limit) : undefined,
      })}`
    ),
  notificationsUnreadCount: () =>
    request<{ count: number }>("GET", "/api/notifications/unread_count"),
  markNotificationsRead: (body: { ids?: string[]; all?: boolean }) =>
    request<{ ok: true; marked: number }>("POST", "/api/notifications/read", body),

  /* ---- feedback ---- */
  submitFeedback: (body: FeedbackInput) =>
    request<Feedback>("POST", "/api/feedback", { source: "dashboard", ...body }),
  myFeedback: () => request<Feedback[]>("GET", "/api/feedback/mine"),

  /* ---- billing (spec §5; scaffolded/disabled by default) ---- */
  billingConfig: () => request<BillingConfig>("GET", "/api/billing/config"),
  billingCheckout: (body: { plan: Plan; target_type: "user" | "org"; org_slug?: string }) =>
    request<{ payment_id: string; order_id: string; amount: number; currency: string; key_id: string | null }>(
      "POST",
      "/api/billing/checkout",
      body
    ),
  billingSubscription: () => request<BillingSubscription>("GET", "/api/billing/subscription"),

  /* ---- platform admin (User.is_admin) ---- */
  adminReviewQueue: (status: ApprovalFilter = "pending") =>
    request<Resource[]>("GET", `/api/admin/resources${qs({ status })}`),
  adminFeedback: (status?: "open" | "reviewed") =>
    request<Feedback[]>("GET", `/api/admin/feedback${qs({ status })}`),
  moderateFeedback: (id: string, decision: "approve" | "reject") =>
    request<Feedback>("POST", `/api/admin/feedback/${id}/moderate`, { decision }),
  setFeedbackStatus: (id: string, status: "open" | "reviewed") =>
    request<Feedback>("POST", `/api/admin/feedback/${id}/status`, { status }),
  setUserPlan: (username: string, plan: Plan) =>
    request<UserEntitlements>("PATCH", `/api/admin/users/${username}/plan`, { plan }),
  setOrgPlan: (slug: string, plan: Plan) =>
    request<OrgEntitlements>("PATCH", `/api/admin/orgs/${slug}/plan`, { plan }),

  /* ---- public marketplace ---- */
  publicResources: (query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/public/resources${qs(query as Record<string, string>)}`),
  /** One page of marketplace resources + the server-reported total count. */
  publicResourcesPage: async (query: ResourceQuery = {}): Promise<ResourcePage> => {
    const { items, total } = await requestList<Resource>(
      `/api/public/resources${qs(query as Record<string, string | number | undefined>)}`
    );
    return { items, total };
  },
  /** Lightweight filter facets (top tags + publishers) for the sidebar. */
  publicFacets: () => request<MarketplaceFacets>("GET", "/api/public/facets"),
  publicResource: (id: string) => request<Resource>("GET", `/api/public/resources/${id}`),
  publisher: (username: string) =>
    request<PublisherProfile>("GET", `/api/public/publishers/${username}`),
  followPublisher: (username: string) =>
    request<{ following: boolean; followers_count: number }>("POST", `/api/public/publishers/${username}/follow`),
  unfollowPublisher: (username: string) =>
    request<{ following: boolean; followers_count: number }>("DELETE", `/api/public/publishers/${username}/follow`),

  /* ---- profile ---- */
  userProfile: (username: string) => request<UserProfile>("GET", `/api/users/${username}`),
  userResources: (username: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/users/${username}/resources${qs(query as Record<string, string>)}`),
  userStarred: (username: string) => request<Resource[]>("GET", `/api/users/${username}/starred`),
  userPinned: (username: string) => request<Resource[]>("GET", `/api/users/${username}/pinned`),
  userContributions: (username: string) =>
    request<Contributions>("GET", `/api/users/${username}/contributions`),
  userActivity: (username: string) => request<Activity[]>("GET", `/api/users/${username}/activity`),
  userOrgs: (username: string) => request<OrgWithRole[]>("GET", `/api/users/${username}/orgs`),
};
