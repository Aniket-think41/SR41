"use client";

/**
 * Shared React Query hooks. Query keys follow the resource hierarchy so
 * mutations can invalidate precisely (frontend spec §6).
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api, type ApprovalFilter, type ResourceQuery } from "./api";
import { useUi } from "./store";

export const qk = {
  me: ["me"] as const,
  myEntitlements: ["me", "entitlements"] as const,
  orgs: ["orgs"] as const,
  org: (slug: string) => ["org", slug] as const,
  orgEntitlements: (slug: string) => ["org", slug, "entitlements"] as const,
  orgReviewQueue: (slug: string, status: ApprovalFilter) => ["org", slug, "review-queue", status] as const,
  features: (slug: string) => ["org", slug, "features"] as const,
  orgMembers: (slug: string) => ["org", slug, "members"] as const,
  invitations: (slug: string) => ["org", slug, "invitations"] as const,
  orgActivity: (slug: string) => ["org", slug, "activity"] as const,
  orgPublished: (slug: string) => ["org", slug, "published"] as const,
  orgResources: (slug: string, q?: ResourceQuery) => ["org", slug, "resources", q ?? {}] as const,
  projects: (slug: string) => ["org", slug, "projects"] as const,
  project: (id: string) => ["project", id] as const,
  projectResources: (id: string, q?: ResourceQuery) => ["project", id, "resources", q ?? {}] as const,
  pods: (projectId: string) => ["project", projectId, "pods"] as const,
  pod: (id: string) => ["pod", id] as const,
  podResources: (id: string, q?: ResourceQuery) => ["pod", id, "resources", q ?? {}] as const,
  resource: (id: string) => ["resource", id] as const,
  publicResources: (q?: ResourceQuery) => ["public", "resources", q ?? {}] as const,
  publicResource: (id: string) => ["public", "resource", id] as const,
  profile: (username: string) => ["profile", username] as const,
  publisher: (username: string) => ["publisher", username] as const,
  notifications: (unreadOnly = false) => ["notifications", { unreadOnly }] as const,
  notificationsUnread: ["notifications", "unread_count"] as const,
  billingConfig: ["billing", "config"] as const,
  billingSubscription: ["billing", "subscription"] as const,
  adminReviewQueue: (status: ApprovalFilter) => ["admin", "review", status] as const,
  adminFeedback: (status?: "open" | "reviewed") => ["admin", "feedback", status ?? "all"] as const,
};

/** Current signed-in user; null when logged out. */
export function useSession() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => {
      try {
        return await api.me();
      } catch {
        return null;
      }
    },
    staleTime: 60_000,
  });
}

/** Personal / publisher-space entitlements for the signed-in user (spec §2). */
export function useMyEntitlements() {
  const { data: user } = useSession();
  return useQuery({
    queryKey: qk.myEntitlements,
    queryFn: api.myEntitlements,
    enabled: !!user,
    staleTime: 60_000,
  });
}

/**
 * Whether the current user may create another organization (spec §2).
 * FREE users (max_orgs === 0) cannot; paid users are capped at max_orgs owned.
 * Defaults to `false` while entitlements load so the gate never flashes open.
 */
export function useCanCreateOrg(): { canCreate: boolean; isLoading: boolean; reason: string | null } {
  const { data: ent, isLoading } = useMyEntitlements();
  if (!ent) return { canCreate: false, isLoading, reason: null };
  if (ent.max_orgs === 0)
    return { canCreate: false, isLoading, reason: `Creating organizations requires a paid plan. You're on ${ent.plan_name}.` };
  if (ent.max_orgs !== null && ent.orgs_owned >= ent.max_orgs)
    return {
      canCreate: false,
      isLoading,
      reason: `Your ${ent.plan_name} plan allows up to ${ent.max_orgs} organization${ent.max_orgs === 1 ? "" : "s"}.`,
    };
  return { canCreate: true, isLoading, reason: null };
}

/** Redirect to /login when unauthenticated. Used by the dashboard layout. */
export function useRequireAuth() {
  const { data: user, isLoading } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!isLoading && user === null) router.replace("/login");
  }, [isLoading, user, router]);
  return { user: user ?? null, isLoading };
}

/** Orgs I belong to + the currently selected one (sidebar org switcher). */
export function useCurrentOrg() {
  const { orgSlug, setOrgSlug } = useUi();
  const orgsQuery = useQuery({ queryKey: qk.orgs, queryFn: api.myOrgs });
  const orgs = orgsQuery.data ?? [];

  // Resolve selection: stored slug if still a member, else first org.
  const current = orgs.find((o) => o.slug === orgSlug) ?? orgs[0] ?? null;

  useEffect(() => {
    if (current && current.slug !== orgSlug) setOrgSlug(current.slug);
  }, [current, orgSlug, setOrgSlug]);

  return { org: current, orgs, isLoading: orgsQuery.isLoading, setOrgSlug };
}

/** Feature flags for the current org (catalog + overrides + license). */
export function useFeatures() {
  const { org } = useCurrentOrg();
  return useQuery({
    queryKey: qk.features(org?.slug ?? ""),
    queryFn: () => api.orgFeatures(org!.slug),
    enabled: !!org,
    staleTime: 30_000,
  });
}

/** Plan, quota, and current resource usage for the current org (spec §2). */
export function useOrgEntitlements() {
  const { org } = useCurrentOrg();
  return useQuery({
    queryKey: qk.orgEntitlements(org?.slug ?? ""),
    queryFn: () => api.orgEntitlements(org!.slug),
    enabled: !!org,
    staleTime: 30_000,
  });
}

/**
 * One flag for the current org. Defaults to enabled while loading so the UI
 * doesn't flash features off; gated mutations are still enforced server-side.
 */
export function useFeature(key: string): { enabled: boolean; licensed: boolean } {
  const { data } = useFeatures();
  const f = data?.find((x) => x.key === key);
  return { enabled: f?.enabled ?? true, licensed: f?.licensed ?? true };
}

const plural = (s: string) => (/s$/i.test(s) ? s : `${s}s`);

/**
 * Org-facing labels for the hierarchy (custom-terminology feature).
 * Data model stays projects → pods; this only changes what users read.
 */
export function useTerms() {
  const { org } = useCurrentOrg();
  const project = org?.terminology?.project?.trim() || "Project";
  const pod = org?.terminology?.pod?.trim() || "Pod";
  return { project, pod, projects: plural(project), pods: plural(pod) };
}

/** Invalidate every resource list a mutation could affect. */
export function useInvalidateResources() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["org"] }),
      qc.invalidateQueries({ queryKey: ["project"] }),
      qc.invalidateQueries({ queryKey: ["pod"] }),
      qc.invalidateQueries({ queryKey: ["public"] }),
      qc.invalidateQueries({ queryKey: ["resource"] }),
      qc.invalidateQueries({ queryKey: ["profile"] }),
    ]);
}
