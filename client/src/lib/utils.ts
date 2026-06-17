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

/**
 * Recognize what a link/file attachment points to, so notes can carry sheets,
 * slides, docs, PDFs, etc. and the UI shows the right label. `key` maps to an
 * icon in the component layer (utils stays icon-free).
 */
export type LinkClassKey =
  | "sheet" | "doc" | "slides" | "drive" | "pdf" | "office" | "figma" | "notion" | "github" | "link";

export function classifyLink(url: string): { label: string; key: LinkClassKey } {
  const u = (url || "").trim().toLowerCase();
  const ext = u.split(/[?#]/)[0].split(".").pop() ?? "";
  if (/docs\.google\.com\/spreadsheets/.test(u)) return { label: "Google Sheet", key: "sheet" };
  if (/docs\.google\.com\/presentation/.test(u)) return { label: "Google Slides", key: "slides" };
  if (/docs\.google\.com\/document/.test(u)) return { label: "Google Doc", key: "doc" };
  if (/drive\.google\.com/.test(u)) return { label: "Google Drive", key: "drive" };
  if (/figma\.com/.test(u)) return { label: "Figma", key: "figma" };
  if (/notion\.(so|site)/.test(u)) return { label: "Notion", key: "notion" };
  if (/github\.com|githubusercontent\.com/.test(u)) return { label: "GitHub", key: "github" };
  if (ext === "pdf") return { label: "PDF", key: "pdf" };
  if (["xlsx", "xls", "csv", "ods", "numbers"].includes(ext)) return { label: "Spreadsheet", key: "sheet" };
  if (["pptx", "ppt", "odp", "key"].includes(ext)) return { label: "Slides", key: "slides" };
  if (["docx", "doc", "odt", "pages"].includes(ext)) return { label: "Document", key: "doc" };
  return { label: "Link", key: "link" };
}

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
