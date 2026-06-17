"use client";

/**
 * In-app marketplace (frontend spec §4.4) — left filter panel (type, tags,
 * publisher, sort), resource grid right. Detail opens a full page for parity
 * with the public site.
 */

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Search, Store } from "lucide-react";
import { api, type ResourceQuery } from "@/lib/api";
import { useInvalidateResources } from "@/lib/hooks";
import type { Resource, ResourceType } from "@/lib/types";
import { TYPE_META } from "@/lib/utils";
import { ResourceCard } from "@/components/ResourceCard";
import { FeatureGate } from "@/components/FeatureGate";

const SORTS = [
  { key: "relevance", label: "Relevance" },
  { key: "stars", label: "Most starred" },
  { key: "installs", label: "Most installed" },
  { key: "newest", label: "Newest" },
  { key: "updated", label: "Recently updated" },
] as const;

export default function MarketplacePage() {
  return (
    <FeatureGate feature="marketplace" title="The public marketplace">
      <MarketplaceBrowser />
    </FeatureGate>
  );
}

function MarketplaceBrowser() {
  const router = useRouter();
  const invalidate = useInvalidateResources();
  const [type, setType] = useState<ResourceType | "ALL">("ALL");
  const [tag, setTag] = useState<string | null>(null);
  const [publisher, setPublisher] = useState<string | null>(null);
  const [sort, setSort] = useState<ResourceQuery["sort"]>("relevance");
  const [q, setQ] = useState("");

  const { data: all } = useQuery({
    queryKey: ["public", "resources", "all"],
    queryFn: () => api.publicResources({ sort: "stars" }),
  });

  // "Relevance" only ranks when there's a query; with no query, lead with the
  // most-starred resources rather than an arbitrary order.
  const effectiveSort = sort === "relevance" && !q ? "stars" : sort;
  const params: ResourceQuery = { q: q || undefined, type: type === "ALL" ? undefined : type, tag: tag ?? undefined, sort: effectiveSort };
  const { data: list, isLoading } = useQuery({
    queryKey: ["public", "resources", params],
    queryFn: () => api.publicResources(params),
    placeholderData: keepPreviousData,
  });

  const filtered = useMemo(
    () => (list ?? []).filter((r) => !publisher || r.author?.username === publisher),
    [list, publisher]
  );

  const allTags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of all ?? []) for (const t of r.tags) counts.set(t, (counts.get(t) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [all]);

  const publishers = useMemo(() => {
    const seen = new Map<string, string>();
    for (const r of all ?? []) if (r.author) seen.set(r.author.username, r.author.display_name);
    return [...seen.entries()];
  }, [all]);

  const starMut = useMutation({
    mutationFn: (r: Resource) => (r.starred_by_me ? api.unstar(r.id) : api.star(r.id)),
    onSuccess: invalidate,
  });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker flex items-center gap-1.5">
            <Store className="h-3.5 w-3.5" /> Public marketplace
          </p>
          <h1 className="font-display mt-1 text-3xl font-semibold">
            Skills the whole world <span className="hl">shares</span>.
          </h1>
          <p className="mt-1.5 text-sm text-body">
            Browse public skills, MCP servers, and notes — add any of them to your org.
          </p>
        </div>
        <label className="flex items-center gap-2 rounded-full border border-line bg-white px-4 py-2">
          <Search className="h-3.5 w-3.5 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the marketplace…"
            className="w-56 bg-transparent text-sm outline-none placeholder:text-muted"
          />
        </label>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        {/* Filter panel */}
        <aside className="space-y-6 lg:sticky lg:top-[calc(var(--topbar-h)+1.5rem)] lg:self-start">
          <div>
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">Type</p>
            <div className="flex flex-wrap gap-1.5 lg:flex-col lg:items-start">
              {(["ALL", "SKILL", "MCP", "NOTE"] as const).map((t) => (
                <button key={t} onClick={() => setType(t)} className={`pill !py-1.5 text-xs ${type === t ? "pill-active" : ""}`}>
                  {t === "ALL" ? "All types" : `${TYPE_META[t].glyph} ${TYPE_META[t].label}s`}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">Tags</p>
            <div className="flex flex-wrap gap-1.5">
              {allTags.map(([t, n]) => (
                <button
                  key={t}
                  onClick={() => setTag(tag === t ? null : t)}
                  className={`tag transition ${tag === t ? "!bg-primary !text-white" : "hover:bg-primary-50 hover:text-primary"}`}
                >
                  #{t} <span className="opacity-60">{n}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">Publisher</p>
            <select value={publisher ?? ""} onChange={(e) => setPublisher(e.target.value || null)} className="field !py-2 text-sm">
              <option value="">All publishers</option>
              {publishers.map(([u, name]) => (
                <option key={u} value={u}>{name}</option>
              ))}
            </select>
          </div>

          <div>
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">Sort</p>
            <select value={sort} onChange={(e) => setSort(e.target.value as ResourceQuery["sort"])} className="field !py-2 text-sm">
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
        </aside>

        {/* Grid */}
        <div>
          <p className="mb-3 text-sm font-medium text-muted">
            {isLoading ? "Loading…" : `${filtered.length} public ${filtered.length === 1 ? "resource" : "resources"}`}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((r) => (
              <ResourceCard
                key={r.id}
                resource={{ ...r, scope_label: undefined }}
                onOpen={() => router.push(`/dashboard/marketplace/${r.id}`)}
                onToggleStar={(x) => starMut.mutate(x)}
              />
            ))}
          </div>
          {!isLoading && filtered.length === 0 && (
            <div className="rounded-2xl border border-dashed border-line bg-white/60 p-16 text-center">
              <p className="font-display text-xl font-semibold">Nothing matches.</p>
              <p className="mt-1 text-sm text-body">Try a different filter or search term.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
