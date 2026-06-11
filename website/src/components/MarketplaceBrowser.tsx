"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Resource, ResourceType } from "@/lib/data";
import { ResourceCard } from "./ResourceCard";

type Filter = ResourceType | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "SKILL", label: "◆ Skills" },
  { key: "MCP", label: "▣ MCP Servers" },
  { key: "NOTE", label: "▤ Notes" },
];

const SORTS = [
  { key: "installs", label: "Most installed" },
  { key: "stars", label: "Most starred" },
  { key: "updated", label: "Recently updated" },
] as const;

const VALID: Filter[] = ["all", "SKILL", "MCP", "NOTE"];

export function MarketplaceBrowser({ items }: { items: Resource[] }) {
  // Read initial type from the URL on the client so the page stays static + ISR.
  const params = useSearchParams();
  const urlType = (params.get("type") ?? "all").toUpperCase();
  const initialType = (VALID as string[]).includes(urlType) ? (urlType as Filter) : "all";

  const [filter, setFilter] = useState<Filter>(initialType);
  const [sort, setSort] = useState<(typeof SORTS)[number]["key"]>("installs");
  const [q, setQ] = useState("");

  const list = useMemo(() => {
    let out: Resource[] = items.filter((r) => filter === "all" || r.type === filter);
    if (q.trim()) {
      const needle = q.toLowerCase();
      out = out.filter(
        (r) =>
          r.title.toLowerCase().includes(needle) ||
          r.description.toLowerCase().includes(needle) ||
          r.tags.some((t) => t.includes(needle))
      );
    }
    return [...out].sort((a, b) =>
      sort === "updated"
        ? b.updated_at.localeCompare(a.updated_at)
        : sort === "stars"
          ? b.stars_count - a.stars_count
          : b.installs_count - a.installs_count
    );
  }, [items, filter, sort, q]);

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
                  : "bg-white text-body hover:text-primary"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex items-center gap-2 rounded-full border border-line bg-white px-4 py-2">
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
            onChange={(e) => setSort(e.target.value as typeof sort)}
            className="rounded-full border border-line bg-white px-4 py-2.5 text-sm font-medium text-ink"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      <p className="mt-5 text-sm font-medium text-muted">
        {list.length} {list.length === 1 ? "resource" : "resources"}
      </p>

      {list.length > 0 ? (
        <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((r) => (
            <ResourceCard key={r.id} r={r} />
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-dashed border-line p-16 text-center">
          <p className="font-display text-2xl font-semibold">Nothing matches.</p>
          <p className="mt-2 text-body">Try a different filter or search term.</p>
        </div>
      )}
    </div>
  );
}
