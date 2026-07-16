"use client";

/**
 * The unified resource library view (frontend spec §4.1) — scope tabs,
 * type filter pills, live search, responsive card grid, and the
 * + Add Resource FAB. Reused by pod / project / org screens.
 */

import { useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Search, Inbox } from "lucide-react";
import { api, type ResourceQuery } from "@/lib/api";
import { useInvalidateResources, useTerms } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import type { Resource, ResourceType, ScopeType } from "@/lib/types";
import { TYPE_META } from "@/lib/utils";
import { ResourceCard } from "./ResourceCard";

const SCOPE_TAB_KEYS = ["all", "pod", "project", "org"] as const;

const TYPE_PILLS: { key: ResourceType | "ALL"; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "SKILL", label: `${TYPE_META.SKILL.glyph} Skills` },
  { key: "MCP", label: `${TYPE_META.MCP.glyph} MCP` },
  { key: "NOTE", label: `${TYPE_META.NOTE.glyph} Notes` },
];

export function ResourceBrowser({
  queryKey,
  fetcher,
  withScopeTabs = false,
  /** the level this browser lives at — resources from above it render read-only */
  contextScope,
  addScope,
  emptyHint = "Add the first skill, MCP server, or note.",
}: {
  queryKey: readonly unknown[];
  fetcher: (q: ResourceQuery) => Promise<Resource[]>;
  withScopeTabs?: boolean;
  contextScope: ScopeType;
  addScope: { scope_type: ScopeType; scope_id: string | null };
  emptyHint?: string;
}) {
  const [scope, setScope] = useState<NonNullable<ResourceQuery["scope"]>>("all");
  const [type, setType] = useState<ResourceType | "ALL">("ALL");
  const [q, setQ] = useState("");
  const { openAdd, openDetail } = useUi();
  const invalidate = useInvalidateResources();
  const terms = useTerms();

  // scope tab labels honor org terminology (e.g. Pod → Team)
  const scopeTabs: { key: NonNullable<ResourceQuery["scope"]>; label: string }[] =
    SCOPE_TAB_KEYS.map((key) => ({
      key,
      label: key === "all" ? "All" : key === "pod" ? terms.pod : key === "project" ? terms.project : "Org",
    }));

  const params: ResourceQuery = {
    q: q || undefined,
    type: type === "ALL" ? undefined : type,
    scope: withScopeTabs ? scope : undefined,
  };

  const { data: list, isLoading } = useQuery({
    queryKey: [...queryKey, params],
    queryFn: () => fetcher(params),
    placeholderData: keepPreviousData,
  });

  const starMut = useMutation({
    mutationFn: (r: Resource) => (r.starred_by_me ? api.unstar(r.id) : api.star(r.id)),
    onSuccess: invalidate,
  });

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-col gap-3 rounded-2xl border border-line bg-card p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {withScopeTabs && (
            <>
              <div className="flex rounded-full border border-line bg-surface p-1">
                {scopeTabs.map((s) => (
                  <button
                    key={s.key}
                    onClick={() => setScope(s.key)}
                    className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition ${
                      scope === s.key ? "bg-card text-primary shadow-sm" : "text-muted hover:text-ink"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <span className="hidden h-5 w-px bg-line sm:block" />
            </>
          )}
          {TYPE_PILLS.map((p) => (
            <button
              key={p.key}
              onClick={() => setType(p.key)}
              className={`pill ${type === p.key ? "pill-active" : ""}`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 rounded-full border border-line bg-card px-4 py-2">
          <Search className="h-3.5 w-3.5 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter resources…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted lg:w-44"
          />
        </label>
      </div>

      <p className="mt-4 text-sm font-medium text-muted">
        {isLoading ? "Loading…" : `${list?.length ?? 0} ${(list?.length ?? 0) === 1 ? "resource" : "resources"}`}
      </p>

      {/* Grid */}
      {isLoading ? (
        <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton h-56" />
          ))}
        </div>
      ) : list && list.length > 0 ? (
        <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((r) => (
            <ResourceCard
              key={r.id}
              resource={r}
              onOpen={openDetail}
              onToggleStar={(x) => starMut.mutate(x)}
              showScopeBadge={withScopeTabs || r.scope_label !== contextScope}
              readOnly={withScopeTabs && r.scope_label !== undefined && r.scope_label !== contextScope}
            />
          ))}
        </div>
      ) : (
        <div className="mt-3 rounded-2xl border border-dashed border-line bg-card/60 p-16 text-center">
          <Inbox className="mx-auto h-8 w-8 text-muted/50" />
          <p className="font-display mt-3 text-xl font-semibold">
            {q || type !== "ALL" ? "Nothing matches." : "No resources yet."}
          </p>
          <p className="mt-1 text-sm text-body">
            {q || type !== "ALL" ? "Try a different filter or search term." : emptyHint}
          </p>
          {!q && type === "ALL" && (
            <button onClick={() => openAdd(addScope)} className="btn btn-primary btn-sm mt-5">
              <Plus className="h-4 w-4" /> Add resource
            </button>
          )}
        </div>
      )}

      {/* FAB (frontend spec §4.1) */}
      <button
        onClick={() => openAdd(addScope)}
        className="fixed bottom-20 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-white shadow-[0_16px_36px_-8px_rgba(115,90,229,0.7)] transition hover:-translate-y-1 hover:bg-primary-700 md:bottom-8 md:right-8"
        title="Add resource"
        aria-label="Add resource"
      >
        <Plus className="h-6 w-6" />
      </button>
    </div>
  );
}
