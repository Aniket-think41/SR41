"use client";

/**
 * ResourceCard (frontend spec §5.1) — same visual language as the
 * marketing site's card. Variants: default grid card, compact list row.
 * Inherited resources get a scope badge + read-only lock indicator.
 */

import { Star, Lock } from "lucide-react";
import type { Resource } from "@/lib/types";
import { fmt, timeAgo } from "@/lib/utils";
import { Avatar } from "./Avatar";
import { ScopeBadge, TypeBadge } from "./badges";

export function ResourceCard({
  resource: r,
  onOpen,
  onToggleStar,
  showScopeBadge = false,
  readOnly = false,
  compact = false,
}: {
  resource: Resource;
  onOpen: (r: Resource) => void;
  onToggleStar?: (r: Resource) => void;
  showScopeBadge?: boolean;
  readOnly?: boolean;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <button
        onClick={() => onOpen(r)}
        className="card flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:border-primary/40"
      >
        <TypeBadge type={r.type} withLabel={false} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold text-ink">{r.title}</span>
          <span className="block truncate text-xs text-muted">{r.description}</span>
        </span>
        {showScopeBadge && r.scope_label && <ScopeBadge scope={r.scope_label} />}
        <span className="shrink-0 text-xs text-muted">★ {fmt(r.stars_count)}</span>
      </button>
    );
  }

  return (
    <article className="card card-hover group relative flex h-full min-w-0 flex-col p-5">
      {onToggleStar && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleStar(r);
          }}
          className={`absolute right-4 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full border bg-white transition ${
            r.starred_by_me
              ? "border-primary text-primary"
              : "border-line text-muted opacity-0 hover:border-primary hover:text-primary group-hover:opacity-100"
          }`}
          title={r.starred_by_me ? "Unstar" : "Star"}
          aria-label={r.starred_by_me ? "Unstar" : "Star"}
        >
          <Star className="h-3.5 w-3.5" fill={r.starred_by_me ? "currentColor" : "none"} />
        </button>
      )}

      <button onClick={() => onOpen(r)} className="flex min-w-0 flex-1 cursor-pointer flex-col text-left">
        <div className="flex flex-wrap items-center gap-2 pr-8">
          <TypeBadge type={r.type} />
          {showScopeBadge && r.scope_label && <ScopeBadge scope={r.scope_label} />}
          {readOnly && (
            <span className="flex items-center gap-1 text-[0.68rem] font-semibold text-muted" title="Inherited — read-only here">
              <Lock className="h-3 w-3" /> inherited
            </span>
          )}
          <span className="text-xs text-muted">v{r.version}</span>
        </div>

        <h3 className="font-display mt-3 break-words text-lg font-semibold leading-snug transition group-hover:text-primary">
          {r.title}
        </h3>
        <p className="mt-1.5 line-clamp-2 flex-1 break-words text-[0.85rem] leading-relaxed text-body">
          {r.description}
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {r.tags.slice(0, 3).map((t) => (
            <span key={t} className="text-xs text-muted">#{t}</span>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-line pt-3.5">
          <span className="flex min-w-0 items-center gap-2">
            <Avatar name={r.author?.display_name ?? "?"} src={r.author?.avatar_url} size="xs" />
            <span className="truncate text-xs font-medium text-ink">
              {r.author?.display_name}
              {r.author?.verified && (
                <span className="ml-1 text-primary" title="Think41-verified">✦</span>
              )}
            </span>
          </span>
          <span className="shrink-0 text-xs text-muted">
            ★ {fmt(r.stars_count)} · {timeAgo(r.updated_at)}
          </span>
        </div>
      </button>
    </article>
  );
}
