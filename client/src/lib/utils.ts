import type { ResourceType, ScopeType } from "./types";

export const fmt = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

export const longDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

export const monthYear = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long" });

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

/** Same glyph + color language as the website (website/src/lib/data.ts). */
export const TYPE_META: Record<
  ResourceType,
  { label: string; glyph: string; chip: string; color: string }
> = {
  SKILL: { label: "Skill", glyph: "◆", chip: "bg-primary-50 text-primary", color: "var(--color-primary)" },
  MCP: { label: "MCP Server", glyph: "▣", chip: "bg-[#e7f0ff] text-mcp", color: "var(--color-mcp)" },
  NOTE: { label: "Note", glyph: "▤", chip: "bg-[#fdece5] text-note", color: "var(--color-note)" },
};

/** Frontend spec §5.2 — Org blue · Project amber · Pod green · Public purple. */
export const SCOPE_META: Record<
  ScopeType,
  { label: string; chip: string; dot: string }
> = {
  ORG: { label: "Org", chip: "bg-[var(--color-scope-org-bg)] text-[var(--color-scope-org)]", dot: "bg-[var(--color-scope-org)]" },
  PROJECT: { label: "Project", chip: "bg-[var(--color-scope-project-bg)] text-[var(--color-scope-project)]", dot: "bg-[var(--color-scope-project)]" },
  POD: { label: "Pod", chip: "bg-[var(--color-scope-pod-bg)] text-[var(--color-scope-pod)]", dot: "bg-[var(--color-scope-pod)]" },
  PUBLIC: { label: "Public", chip: "bg-[var(--color-scope-public-bg)] text-[var(--color-scope-public)]", dot: "bg-[var(--color-scope-public)]" },
};
