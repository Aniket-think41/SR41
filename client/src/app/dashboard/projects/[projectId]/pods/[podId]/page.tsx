"use client";

/**
 * Pod resource view — the core screen (frontend spec §4.1).
 * Scope tabs (All | Pod | Project | Org), type pills, live search,
 * inherited resources marked read-only, + Add Resource FAB.
 */

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Settings, Users } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useTerms } from "@/lib/hooks";
import { ResourceBrowser } from "@/components/ResourceBrowser";
import { Avatar } from "@/components/Avatar";

export default function PodDetail({
  params,
}: {
  params: Promise<{ projectId: string; podId: string }>;
}) {
  const { projectId, podId } = use(params);
  const terms = useTerms();

  const { data: pod } = useQuery({
    queryKey: qk.pod(podId),
    queryFn: () => api.pod(projectId, podId),
  });
  const { data: members } = useQuery({
    queryKey: [...qk.pod(podId), "members"],
    queryFn: () => api.podMembers(projectId, podId),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <p className="kicker">{terms.pod}</p>
            {pod?.purpose_tag && (
              <span className="tag bg-[var(--color-scope-pod-bg)] text-[var(--color-scope-pod)]">
                {pod.purpose_tag}
              </span>
            )}
          </div>
          <h1 className="font-display mt-1 text-3xl font-semibold">{pod?.name ?? "…"}</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-body">{pod?.description}</p>
        </div>

        <div className="flex items-center gap-3">
          {/* Member avatars */}
          <div className="flex items-center -space-x-2" title={`${members?.length ?? 0} members`}>
            {(members ?? []).slice(0, 4).map((m) => (
              <Avatar key={m.id} name={m.user?.display_name ?? "?"} src={m.user?.avatar_url} size="sm" className="ring-2 ring-surface" />
            ))}
            {(members?.length ?? 0) > 4 && (
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-[0.65rem] font-bold text-body ring-2 ring-surface">
                +{members!.length - 4}
              </span>
            )}
          </div>
          <Link
            href={`/dashboard/projects/${projectId}/pods/${podId}/settings`}
            className="btn btn-secondary btn-sm"
          >
            <Settings className="h-3.5 w-3.5" /> Settings
          </Link>
        </div>
      </div>

      {/* Inheritance hint */}
      <p className="flex items-center gap-2 rounded-2xl border border-line bg-white px-4 py-2.5 text-xs font-medium text-muted">
        <Users className="h-3.5 w-3.5 shrink-0 text-primary" />
        This {terms.pod.toLowerCase()} sees its own resources plus everything inherited from the{" "}
        {terms.project.toLowerCase()} and org — switch scope tabs to filter by origin.
      </p>

      <ResourceBrowser
        queryKey={["pod", podId, "resources"]}
        fetcher={(q) => api.podResources(podId, q)}
        withScopeTabs
        contextScope="POD"
        addScope={{ scope_type: "POD", scope_id: podId }}
        emptyHint={`Add the ${terms.pod.toLowerCase()}'s first skill, MCP server, or note — or check the ${terms.project} / Org tabs for inherited ones.`}
      />
    </div>
  );
}
