"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";
import { Resource, ResourceType } from "@/lib/data";
import { loadResourcesAction } from "@/app/marketplace-actions";
import { ResourceCard } from "./ResourceCard";

type Filter = ResourceType | "all";
type Sort = "installs" | "stars" | "updated";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "SKILL", label: "◆ Skills" },
  { key: "MCP", label: "▣ MCP Servers" },
  { key: "NOTE", label: "▤ Notes" },
];

const SORTS: { key: Sort; label: string }[] = [
  { key: "installs", label: "Most installed" },
  { key: "stars", label: "Most starred" },
  { key: "updated", label: "Recently updated" },
];

const VALID: Filter[] = ["all", "SKILL", "MCP", "NOTE"];
const DEFAULT_SORT: Sort = "installs";

// The query the server-rendered initial page represents, so we can skip a
// redundant first fetch when the URL carries no filter/search.
const keyOf = (filter: Filter, sort: Sort, q: string) =>
  `${filter === "all" ? "" : filter}|${q.trim()}|${sort}`;

export function MarketplaceBrowser({
  initialItems,
  initialTotal,
  pageSize,
}: {
  initialItems: Resource[];
  initialTotal: number;
  pageSize: number;
}) {
  // Read initial type/search from the URL on the client so the page stays
  // static + ISR (the hero search and footer quick-links push ?type / ?q).
  const params = useSearchParams();
  const urlTypeRaw = (params.get("type") ?? "all").toUpperCase();
  const urlType: Filter = (VALID as string[]).includes(urlTypeRaw) ? (urlTypeRaw as Filter) : "all";
  const urlQ = params.get("q") ?? "";

  const [filter, setFilter] = useState<Filter>(urlType);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [q, setQ] = useState(urlQ);

  // Re-sync controls when the URL changes (adjust-state-during-render pattern —
  // no effect, no cascading-render warning).
  const [seenType, setSeenType] = useState(urlType);
  if (seenType !== urlType) {
    setSeenType(urlType);
    setFilter(urlType);
  }
  const [seenQ, setSeenQ] = useState(urlQ);
  if (seenQ !== urlQ) {
    setSeenQ(urlQ);
    setQ(urlQ);
  }

  const [items, setItems] = useState<Resource[]>(initialItems);
  const [total, setTotal] = useState(initialTotal);
  const [isPending, startTransition] = useTransition();
  const [loadingMore, setLoadingMore] = useState(false);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  const [debouncedQ, setDebouncedQ] = useState(urlQ);
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(id);
  }, [q]);

  // Monotonic request id: ignore responses from a query that's since changed.
  const reqId = useRef(0);
  const firstRun = useRef(true);

  // Re-query page 1 whenever the filter / sort / (debounced) search changes.
  useEffect(() => {
    // The server-rendered initial page is the default query (all / installs /
    // no search). Skip the first fetch only when the active query matches it.
    if (firstRun.current) {
      firstRun.current = false;
      if (keyOf(filter, sort, debouncedQ) === keyOf("all", DEFAULT_SORT, "")) return;
    }
    const id = ++reqId.current;
    startTransition(async () => {
      const page = await loadResourcesAction({
        type: filter,
        q: debouncedQ,
        sort,
        limit: pageSize,
        offset: 0,
      });
      if (id !== reqId.current) return; // a newer query superseded this one
      setItems(page.items);
      setTotal(page.total);
    });
  }, [filter, sort, debouncedQ, pageSize]);

  async function loadMore() {
    const id = reqId.current;
    setLoadingMore(true);
    try {
      const page = await loadResourcesAction({
        type: filter,
        q: debouncedQ,
        sort,
        limit: pageSize,
        offset: items.length,
      });
      if (id !== reqId.current) return; // query changed mid-load — drop stale page
      setItems((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } finally {
      setLoadingMore(false);
    }
  }

  const hasMore = items.length < total;

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                filter === f.key
                  ? "bg-primary text-white shadow-[0_8px_20px_-8px_rgba(115,90,229,0.6)]"
                  : "bg-card text-body hover:text-primary"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex items-center gap-2 rounded-full border border-line bg-card px-4 py-2">
            <span aria-hidden className="text-muted">⌕</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search resources…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted sm:w-48"
            />
          </label>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="rounded-full border border-line bg-card px-4 py-2.5 text-sm font-medium text-ink"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      <p className="mt-5 text-sm font-medium text-muted">
        {hasMore
          ? `Showing ${items.length} of ${total} resources`
          : `${total} ${total === 1 ? "resource" : "resources"}`}
      </p>

      {items.length > 0 ? (
        <div
          className={`mt-4 grid gap-5 transition-opacity sm:grid-cols-2 lg:grid-cols-3 ${
            isPending ? "opacity-60" : ""
          }`}
        >
          {items.map((r) => (
            <ResourceCard key={r.id} r={r} />
          ))}
        </div>
      ) : isPending ? (
        <p className="mt-4 text-sm font-medium text-muted">Searching…</p>
      ) : (
        <div className="mt-4 rounded-2xl border border-dashed border-line p-16 text-center">
          <p className="font-display text-2xl font-semibold">Nothing matches.</p>
          <p className="mt-2 text-body">Try a different filter or search term.</p>
        </div>
      )}

      {hasMore && (
        <div className="mt-10 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore || isPending}
            className="btn btn-secondary disabled:opacity-60"
          >
            {loadingMore ? "Loading…" : `Load more (${total - items.length})`}
          </button>
        </div>
      )}
    </div>
  );
}
