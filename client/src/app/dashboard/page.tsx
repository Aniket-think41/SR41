"use client";

/**
 * Dashboard home — greeting, org stat tiles, recent activity, and the
 * freshest resources across the org (frontend spec route map).
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Library, Users, Star, ArrowRight, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useCurrentOrg, useFeature, useSession, useTerms } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { timeAgo } from "@/lib/utils";
import { Avatar } from "@/components/Avatar";
import { TypeGlyph } from "@/components/badges";

const VERBS: Record<string, string> = {
  created: "created",
  updated: "updated",
  published: "published",
  starred: "starred",
  joined: "joined",
  invited: "invited",
};

export default function DashboardHome() {
  const { data: user } = useSession();
  const { org } = useCurrentOrg();
  const { openAdd, openDetail } = useUi();
  const terms = useTerms();
  const activityFeature = useFeature("activity-feed");

  const { data: projects } = useQuery({
    queryKey: qk.projects(org?.slug ?? ""),
    queryFn: () => api.projects(org!.slug),
    enabled: !!org,
  });
  const { data: members } = useQuery({
    queryKey: qk.orgMembers(org?.slug ?? ""),
    queryFn: () => api.orgMembers(org!.slug),
    enabled: !!org,
  });
  const { data: activity } = useQuery({
    queryKey: qk.orgActivity(org?.slug ?? ""),
    queryFn: () => api.orgActivity(org!.slug),
    enabled: !!org && activityFeature.enabled,
  });
  const { data: orgResources } = useQuery({
    queryKey: qk.orgResources(org?.slug ?? "", { sort: "updated" }),
    queryFn: () => api.orgResources(org!.slug, { sort: "updated" }),
    enabled: !!org,
  });

  const firstName = user?.display_name.split(" ")[0] ?? "";
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  const stats = [
    { label: terms.projects, value: projects?.length ?? "—", icon: FolderKanban, href: "/dashboard/projects" },
    { label: "Org resources", value: orgResources?.length ?? "—", icon: Library, href: "/dashboard/org/resources" },
    { label: "Members", value: members?.length ?? "—", icon: Users, href: "/dashboard/members" },
    {
      label: "Stars received",
      value: orgResources ? orgResources.reduce((a, r) => a + r.stars_count, 0) : "—",
      icon: Star,
      href: "/dashboard/org/resources",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <div className="reveal flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker">{org?.name ?? "…"}</p>
          <h1 className="font-display mt-1 text-3xl font-semibold sm:text-4xl">
            {greeting}, <span className="hl">{firstName}</span>.
          </h1>
          <p className="mt-2 text-sm text-body">
            Here&rsquo;s what&rsquo;s moving in your registry.
          </p>
        </div>
        <button
          onClick={() => org && openAdd({ scope_type: "ORG", scope_id: org.id })}
          className="btn btn-primary"
        >
          <Plus className="h-4 w-4" /> Add resource
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ label, value, icon: Icon, href }, i) => (
          <Link
            key={label}
            href={href}
            className="card card-hover reveal p-5"
            style={{ animationDelay: `${i * 0.06}s` }}
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary">
              <Icon className="h-4.5 w-4.5" />
            </span>
            <p className="font-display mt-3 text-3xl font-semibold">{value}</p>
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
          </Link>
        ))}
      </div>

      <div className={`grid gap-6 ${activityFeature.enabled ? "lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]" : ""}`}>
        {/* Recently updated resources */}
        <section className="card min-w-0 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold">Recently updated</h2>
            <Link href="/dashboard/org/resources" className="flex items-center gap-1 text-xs font-bold text-primary hover:underline">
              Org resources <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {(orgResources ?? []).slice(0, 5).map((r) => (
              <button
                key={r.id}
                onClick={() => openDetail(r)}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-surface"
              >
                <TypeGlyph type={r.type} className="w-5 text-center" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-bold text-ink">{r.title}</span>
                  <span className="block truncate text-xs text-muted">{r.description}</span>
                </span>
                <span className="shrink-0 text-xs text-muted">{timeAgo(r.updated_at)}</span>
              </button>
            ))}
            {orgResources?.length === 0 && (
              <p className="py-8 text-center text-sm text-muted">No org-level resources yet.</p>
            )}
          </div>
        </section>

        {/* Activity feed (feature-gated) */}
        {activityFeature.enabled && (
        <section className="card min-w-0 p-6">
          <h2 className="font-display mb-4 text-lg font-semibold">Recent activity</h2>
          <ol className="relative space-y-4 before:absolute before:bottom-2 before:left-[11px] before:top-2 before:w-px before:bg-line">
            {(activity ?? []).slice(0, 8).map((a) => (
              <li key={a.id} className="relative flex items-start gap-3 pl-0.5">
                <Avatar name={a.user?.display_name ?? "?"} src={a.user?.avatar_url} size="xs" className="relative z-10 ring-2 ring-white" />
                <div className="min-w-0 flex-1 text-sm">
                  <p className="break-words leading-snug">
                    <span className="font-bold text-ink">{a.user?.display_name}</span>{" "}
                    <span className="text-body">{VERBS[a.verb]}</span>{" "}
                    <span className="font-semibold text-primary">{a.object_title}</span>
                    {a.meta && <span className="text-muted"> · {a.meta}</span>}
                  </p>
                  <p className="text-xs text-muted">{timeAgo(a.created_at)}</p>
                </div>
              </li>
            ))}
            {activity?.length === 0 && <p className="py-8 text-center text-sm text-muted">Quiet so far.</p>}
          </ol>
        </section>
        )}
      </div>

      {/* Projects strip */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold">Your {terms.projects.toLowerCase()}</h2>
          <Link href="/dashboard/projects" className="flex items-center gap-1 text-xs font-bold text-primary hover:underline">
            All {terms.projects.toLowerCase()} <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {(projects ?? []).map((p) => (
            <Link key={p.id} href={`/dashboard/projects/${p.id}`} className="card card-hover p-5">
              <h3 className="font-display text-lg font-semibold">{p.name}</h3>
              <p className="mt-1 line-clamp-2 text-sm text-body">{p.description}</p>
              <p className="mt-3 text-xs font-semibold text-muted">
                {p.pods_count} pods · {p.members_count} members · {p.resources_count} resources
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
