"use client";

/**
 * ⌘K command palette (frontend spec §3.3) — searches resources, projects,
 * pods, and members in the current org, grouped by type with scope badges.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, FolderKanban, Boxes, CornerDownLeft } from "lucide-react";
import { api } from "@/lib/api";
import { useCurrentOrg, useFeature } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { ScopeBadge, TypeGlyph } from "../badges";
import { Avatar } from "../Avatar";

export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, openDetail } = useUi();
  const { org } = useCurrentOrg();
  const feature = useFeature("command-palette");
  const router = useRouter();
  const [q, setQ] = useState("");

  // Global ⌘K / Ctrl+K (disabled when the org turns the feature off)
  useEffect(() => {
    if (!feature.enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, setPaletteOpen, feature.enabled]);

  // clear the query whenever the palette closes — render-time adjust
  const [wasOpen, setWasOpen] = useState(paletteOpen);
  if (wasOpen !== paletteOpen) {
    setWasOpen(paletteOpen);
    if (!paletteOpen) setQ("");
  }

  const { data } = useQuery({
    queryKey: ["palette", org?.slug, q],
    queryFn: () => api.orgSearch(org!.slug, q),
    enabled: paletteOpen && !!org,
  });

  if (!paletteOpen || !feature.enabled) return null;

  const go = (href: string) => {
    setPaletteOpen(false);
    router.push(href);
  };

  const empty =
    data &&
    data.resources.length + data.projects.length + data.pods.length + data.members.length === 0;

  return (
    <div
      className="overlay-fade fixed inset-0 z-[90] flex items-start justify-center bg-navy/40 p-4 pt-[12vh] backdrop-blur-[2px]"
      onClick={() => setPaletteOpen(false)}
      role="dialog"
      aria-modal
      aria-label="Search"
    >
      <div
        className="pop w-full max-w-xl overflow-hidden rounded-3xl border border-line bg-card shadow-[0_40px_80px_-20px_rgba(10,8,64,0.45)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <Search className="h-4 w-4 shrink-0 text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search resources, projects, pods, members…"
            className="w-full bg-transparent text-[0.95rem] text-ink outline-none placeholder:text-muted"
          />
          <span className="kbd shrink-0">esc</span>
        </div>

        <div className="thin-scroll max-h-[55vh] overflow-y-auto p-2">
          {data?.resources && data.resources.length > 0 && (
            <Section label="Resources">
              {data.resources.map((r) => (
                <button
                  key={r.id}
                  onClick={() => {
                    setPaletteOpen(false);
                    openDetail(r);
                  }}
                  className="palette-row flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-surface"
                >
                  <TypeGlyph type={r.type} className="w-4 text-center text-sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-ink">{r.title}</span>
                    <span className="block truncate text-xs text-muted">{r.tags.map((t) => `#${t}`).join(" ")}</span>
                  </span>
                  {r.scope_label && <ScopeBadge scope={r.scope_label} />}
                </button>
              ))}
            </Section>
          )}

          {data?.projects && data.projects.length > 0 && (
            <Section label="Projects">
              {data.projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => go(`/dashboard/projects/${p.id}`)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-surface"
                >
                  <FolderKanban className="h-4 w-4 text-primary" />
                  <span className="flex-1 truncate text-sm font-semibold text-ink">{p.name}</span>
                  <CornerDownLeft className="h-3.5 w-3.5 text-muted/50" />
                </button>
              ))}
            </Section>
          )}

          {data?.pods && data.pods.length > 0 && (
            <Section label="Pods">
              {data.pods.map((p) => (
                <button
                  key={p.id}
                  onClick={() => go(`/dashboard/projects/${p.project_id}/pods/${p.id}`)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-surface"
                >
                  <Boxes className="h-4 w-4 text-[var(--color-scope-pod)]" />
                  <span className="flex-1 truncate text-sm font-semibold text-ink">{p.name}</span>
                  <span className="tag">{p.purpose_tag}</span>
                </button>
              ))}
            </Section>
          )}

          {data?.members && data.members.length > 0 && (
            <Section label="Members">
              {data.members.map((u) => (
                <button
                  key={u.id}
                  onClick={() => go(`/dashboard/members`)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-surface"
                >
                  <Avatar name={u.display_name} src={u.avatar_url} size="xs" />
                  <span className="flex-1 truncate text-sm font-semibold text-ink">{u.display_name}</span>
                  <span className="text-xs text-muted">@{u.username}</span>
                </button>
              ))}
            </Section>
          )}

          {empty && (
            <p className="px-4 py-10 text-center text-sm text-muted">
              Nothing matches <span className="font-bold text-ink">&ldquo;{q}&rdquo;</span> in this org.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-1">
      <p className="px-3 pb-1 pt-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">{label}</p>
      {children}
    </div>
  );
}
