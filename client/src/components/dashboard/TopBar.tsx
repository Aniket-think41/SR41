"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useCurrentOrg, useFeature, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { Avatar } from "../Avatar";
import { NotificationBell } from "./NotificationBell";

/** Breadcrumb: Org › Project › Pod — clickable (frontend spec §3.2). */
function Breadcrumb() {
  const { org } = useCurrentOrg();
  const params = useParams<{ projectId?: string; podId?: string }>();
  const projectId = params?.projectId;
  const podId = params?.podId;

  const { data: project } = useQuery({
    queryKey: qk.project(projectId ?? ""),
    queryFn: () => api.project(org!.slug, projectId!),
    enabled: !!org && !!projectId,
  });
  const { data: pod } = useQuery({
    queryKey: qk.pod(podId ?? ""),
    queryFn: () => api.pod(projectId!, podId!),
    enabled: !!projectId && !!podId,
  });

  return (
    <nav className="flex min-w-0 items-center gap-1.5 text-sm" aria-label="Breadcrumb">
      <Link href="/dashboard" className="shrink-0 font-semibold text-muted transition hover:text-primary">
        {org?.name ?? "…"}
      </Link>
      {project && (
        <>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/60" />
          <Link
            href={`/dashboard/projects/${project.id}`}
            className="truncate font-semibold text-muted transition hover:text-primary"
          >
            {project.name.split("—")[0].trim()}
          </Link>
        </>
      )}
      {pod && (
        <>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/60" />
          <span className="truncate font-bold text-ink">{pod.name}</span>
        </>
      )}
    </nav>
  );
}

export function TopBar() {
  const { setPaletteOpen, sidebarCollapsed } = useUi();
  const { data: user } = useSession();
  const palette = useFeature("command-palette");

  return (
    <header
      className={`fixed right-0 top-0 z-30 flex h-[var(--topbar-h)] items-center justify-between gap-4 border-b border-line bg-white/85 px-4 backdrop-blur-xl transition-[left] duration-300 md:px-6 left-0 ${
        sidebarCollapsed ? "md:left-[var(--sidebar-w-collapsed)]" : "md:left-[var(--sidebar-w)]"
      }`}
    >
      <Breadcrumb />

      <div className="flex shrink-0 items-center gap-2.5">
        {palette.enabled && (
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 text-sm text-muted transition hover:border-primary hover:text-primary"
            aria-label="Search (Cmd+K)"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search…</span>
            <span className="kbd hidden sm:inline">⌘K</span>
          </button>
        )}

        <NotificationBell />

        <Link href="/dashboard/profile" aria-label="My profile">
          <Avatar name={user?.display_name ?? "?"} src={user?.avatar_url} size="sm" />
        </Link>
      </div>
    </header>
  );
}
