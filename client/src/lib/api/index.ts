/**
 * Typed API client — one function per endpoint in backend/BACKEND_SPEC.md §3.
 * Screens never call fetch directly; they call these via React Query.
 */

import { request, uploadAvatar, uploadFile, uploadOrgLogo } from "./http";
import type {
  Activity,
  AuthSession,
  Contributions,
  Feedback,
  FeedbackInput,
  Invitation,
  Notification,
  OrgFeature,
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

export interface ResourceQuery {
  q?: string;
  type?: ResourceType | "ALL";
  tag?: string;
  sort?: "relevance" | "updated" | "newest" | "stars" | "installs";
  scope?: "all" | "pod" | "project" | "org";
}

const qs = (params: Record<string, string | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) s.set(k, v);
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  /* ---- auth ---- */
  signup: (body: { email: string; password: string; display_name: string }) =>
    request<AuthSession>("POST", "/api/auth/signup", body),
  login: (body: { email: string; password: string }) =>
    request<AuthSession>("POST", "/api/auth/login", body),
  logout: () => request<{ ok: true }>("POST", "/api/auth/logout"),
  me: () => request<User>("GET", "/api/auth/me"),
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
  orgFeatures: (slug: string) => request<OrgFeature[]>("GET", `/api/orgs/${slug}/features`),
  setFeature: (slug: string, key: string, enabled: boolean) =>
    request<OrgFeature>("PATCH", `/api/orgs/${slug}/features/${key}`, { enabled }),
  activateLicense: (slug: string, licenseKey: string) =>
    request<{ plan: PlanTier; features: OrgFeature[] }>("POST", `/api/orgs/${slug}/license`, {
      license_key: licenseKey,
    }),
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
  projectMembers: (slug: string, projectId: string) =>
    request<ProjectMember[]>("GET", `/api/orgs/${slug}/projects/${projectId}/members`),
  addProjectMember: (slug: string, projectId: string, body: { user_id: string; role?: string }) =>
    request<ProjectMember>("POST", `/api/orgs/${slug}/projects/${projectId}/members`, body),

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
  podMembers: (projectId: string, podId: string) =>
    request<PodMember[]>("GET", `/api/projects/${projectId}/pods/${podId}/members`),
  addPodMember: (projectId: string, podId: string, body: { user_id: string; role?: string }) =>
    request<PodMember>("POST", `/api/projects/${projectId}/pods/${podId}/members`, body),

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
  }) => request<Resource>("POST", "/api/resources", body),
  resource: (id: string) => request<Resource>("GET", `/api/resources/${id}`),
  updateResource: (id: string, body: Partial<Resource>) =>
    request<Resource>("PATCH", `/api/resources/${id}`, body),
  deleteResource: (id: string) => request<{ ok: true }>("DELETE", `/api/resources/${id}`),
  orgResources: (slug: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/orgs/${slug}/resources${qs(query as Record<string, string>)}`),
  projectResources: (projectId: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/projects/${projectId}/resources${qs(query as Record<string, string>)}`),
  podResources: (podId: string, query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/pods/${podId}/resources${qs(query as Record<string, string>)}`),
  publish: (id: string) => request<Resource>("POST", `/api/resources/${id}/publish`),
  unpublish: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/publish`),
  star: (id: string) => request<Resource>("POST", `/api/resources/${id}/star`),
  unstar: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/star`),
  pin: (id: string) => request<Resource>("POST", `/api/resources/${id}/pin`),
  unpin: (id: string) => request<Resource>("DELETE", `/api/resources/${id}/pin`),
  upload: (filename: string) =>
    request<{ file_url: string }>("POST", "/api/resources/upload", { filename }),
  uploadFile: (file: File, kind: "image" | "video" | "file") => uploadFile(file, kind),
  importResource: (id: string, orgSlug: string) =>
    request<Resource>("POST", `/api/resources/${id}/import`, { org_slug: orgSlug }),

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

  /* ---- public marketplace ---- */
  publicResources: (query: ResourceQuery = {}) =>
    request<Resource[]>("GET", `/api/public/resources${qs(query as Record<string, string>)}`),
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
