/**
 * Marketplace data for the marketing site.
 *
 * Single source of truth is the backend's PUBLIC marketplace API
 * (`/api/public/*`, see backend/BACKEND_SPEC §3.6). When `API_URL` (or
 * `NEXT_PUBLIC_API_URL`) is set, every page fetches live with ISR
 * (revalidate 60s). When it's unset — e.g. a standalone marketing build with
 * no backend — we fall back to the bundled seed below, which mirrors the
 * backend seed (backend/scripts/seed.py) field-for-field.
 *
 * The shapes here match the backend wire format (client/src/lib/types.ts):
 * uppercase `type`, `title`/`description`, an embedded `author`, and
 * `stars_count`/`installs_count`/`updated_at`. That's the alignment — the
 * website, dashboard, CLI, and MCP all speak the same vocabulary.
 */

const API_BASE = (process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export type ResourceType = "SKILL" | "MCP" | "NOTE";

export type AttachmentKind = "link" | "image" | "video" | "file";

export interface Attachment {
  kind: AttachmentKind;
  url: string;
  title?: string | null;
  caption?: string | null;
}

/** Mirrors backend `user_out` (serialize.py). */
export interface Publisher {
  id: string;
  email?: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string;
  location?: string | null;
  website?: string | null;
  is_publisher: boolean;
  verified: boolean;
  created_at: string;
  updated_at?: string;
}

/** Mirrors backend `resource_out` (serialize.py). */
export interface Resource {
  id: string;
  type: ResourceType;
  title: string;
  description: string;
  content_md?: string | null;
  server_url?: string | null;
  config_json?: string | null;
  file_url?: string | null;
  version: string;
  tags: string[];
  attachments?: Attachment[];
  scope_type?: string;
  scope_id?: string | null;
  author_id: string;
  is_public?: boolean;
  stars_count: number;
  installs_count: number;
  created_at?: string;
  updated_at: string;
  scope_label?: string;
  author?: Publisher | null;
  starred_by_me?: boolean;
}

export const TYPE_META: Record<
  ResourceType,
  { label: string; glyph: string; color: string }
> = {
  SKILL: { label: "Skill", glyph: "◆", color: "var(--color-primary)" },
  MCP: { label: "MCP Server", glyph: "▣", color: "var(--color-mcp)" },
  NOTE: { label: "Note", glyph: "▤", color: "var(--color-note)" },
};

// ---------------------------------------------------------------------------
// Bundled fallback (used only when no API_URL is configured). Mirrors the
// backend seed so a standalone marketing build still renders real content.
// ---------------------------------------------------------------------------

const USERS: Record<string, Publisher> = {
  think41: {
    id: "u-think41",
    username: "think41",
    display_name: "Think41",
    avatar_url: null,
    bio: "The team behind SkillShare. Foundational skills and MCP servers, maintained and verified.",
    is_publisher: true,
    verified: true,
    created_at: "2025-09-01T00:00:00",
  },
  "ada-rao": {
    id: "u-ada",
    username: "ada-rao",
    display_name: "Ada Rao",
    avatar_url: null,
    bio: "Platform engineer. I build retrieval and code-review skills for fast-moving teams.",
    is_publisher: true,
    verified: true,
    created_at: "2025-10-01T00:00:00",
  },
  nilesh: {
    id: "u-nilesh",
    username: "nilesh",
    display_name: "Nilesh Gupta",
    avatar_url: null,
    bio: "Infra & observability. MCP servers that connect agents to real production systems.",
    is_publisher: true,
    verified: false,
    created_at: "2026-01-10T00:00:00",
  },
  "studio-mono": {
    id: "u-mono",
    username: "studio-mono",
    display_name: "Studio Mono",
    avatar_url: null,
    bio: "A two-person studio shipping design-system and frontend skills for AI agents.",
    is_publisher: true,
    verified: true,
    created_at: "2025-10-12T00:00:00",
  },
};

const byId = (id: string) => Object.values(USERS).find((u) => u.id === id) ?? null;

const SEED: Resource[] = [
  {
    id: "pr-reviewer", type: "SKILL", title: "PR Reviewer",
    description:
      "A reviewing skill that reads a diff and surfaces correctness bugs alongside reuse and simplification cleanups. Tunable by effort level, it leaves inline comments and a summary verdict. Built for teams that want consistent, high-signal reviews without a human on every PR.",
    version: "2.4.1", tags: ["code-review", "github", "quality"],
    author_id: "u-ada", stars_count: 921, installs_count: 12840, updated_at: "2026-05-20",
  },
  {
    id: "postgres-mcp", type: "MCP", title: "Postgres MCP",
    description:
      "An MCP server that exposes a Postgres database to your agents with a read-only safety boundary, schema introspection, and query timeouts. Connection strings stay server-side; agents get structured results, never raw credentials.",
    version: "1.8.0", tags: ["database", "postgres", "infra"],
    author_id: "u-nilesh", stars_count: 654, installs_count: 8120, updated_at: "2026-05-24",
  },
  {
    id: "design-system-kit", type: "SKILL", title: "Design System Kit",
    description:
      "Feed it your design tokens and this skill produces accessible, on-brand React components with motion and dark-mode baked in. It enforces your spacing scale and type ramp so generated UI never drifts from the system.",
    version: "3.1.2", tags: ["frontend", "react", "design"],
    author_id: "u-mono", stars_count: 510, installs_count: 6450, updated_at: "2026-05-18",
  },
  {
    id: "incident-runbook", type: "NOTE", title: "Incident Runbook",
    description:
      "A structured note capturing how the team runs incidents — severity definitions, the comms cadence, escalation contacts, and post-mortem template. Shared at the org level so every pod inherits the same playbook automatically.",
    version: "1.2.0", tags: ["sre", "process", "on-call"],
    attachments: [
      { kind: "video", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ", title: "Incident response walkthrough", caption: "15-min screen recording of a SEV2 drill." },
      { kind: "link", url: "https://www.atlassian.com/incident-management/handbook", title: "Atlassian Incident Handbook", caption: "Reference we based our severities on." },
      { kind: "file", url: "https://cdn.skillshare.think41.com/docs/postmortem-template.md", title: "postmortem-template.md", caption: null },
    ] as Attachment[],
    author_id: "u-think41", stars_count: 388, installs_count: 4300, updated_at: "2026-05-11",
  },
  {
    id: "semantic-search", type: "SKILL", title: "Semantic Search",
    description:
      "A retrieval skill that chunks documents, builds embeddings, and answers questions with citations. Pluggable vector store, re-ranking, and an evaluation harness so you can measure retrieval quality before you ship.",
    version: "2.0.6", tags: ["rag", "search", "embeddings"],
    author_id: "u-ada", stars_count: 742, installs_count: 9870, updated_at: "2026-05-22",
  },
  {
    id: "slack-mcp", type: "MCP", title: "Slack MCP",
    description:
      "An MCP server bridging agents to Slack. Scope it to specific channels, control read vs. write, and keep tokens server-side. Useful for status updates, triage bots, and digest generation.",
    version: "1.4.3", tags: ["slack", "messaging", "infra"],
    author_id: "u-nilesh", stars_count: 421, installs_count: 5610, updated_at: "2026-05-25",
  },
  {
    id: "changelog-writer", type: "SKILL", title: "Changelog Writer",
    description:
      "Reads merged pull requests over a range and writes a human changelog grouped by feature, fix, and chore. Pairs well with PR Reviewer for an end-to-end release flow.",
    version: "1.1.0", tags: ["release", "docs", "github"],
    author_id: "u-mono", stars_count: 277, installs_count: 3920, updated_at: "2026-05-09",
  },
  {
    id: "brand-voice", type: "NOTE", title: "Brand Voice",
    description:
      "A note defining how the company writes — voice, tone, banned phrases, and worked examples. Inherited org-wide so every skill that generates copy stays on-brand.",
    version: "1.0.4", tags: ["content", "brand", "writing"],
    author_id: "u-think41", stars_count: 196, installs_count: 2880, updated_at: "2026-05-06",
  },
].map((r) => ({
  ...r,
  type: r.type as ResourceType,
  is_public: true,
  scope_label: "PUBLIC",
  author: byId(r.author_id),
}));

// ---------------------------------------------------------------------------
// Data access — live API with ISR, falling back to the bundled seed.
// ---------------------------------------------------------------------------

async function apiGet<T>(path: string): Promise<T | null> {
  if (!API_BASE) return null;
  try {
    const res = await fetch(`${API_BASE}/api/public${path}`, {
      next: { revalidate: 60 },
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // backend unreachable → fall back to bundled seed
  }
}

export async function getResources(): Promise<Resource[]> {
  return (await apiGet<Resource[]>("/resources")) ?? SEED;
}

export async function getResource(id: string): Promise<Resource | undefined> {
  const live = await apiGet<Resource>(`/resources/${id}`);
  if (live) return live;
  return SEED.find((r) => r.id === id);
}

export interface PublisherProfile extends Publisher {
  resources: Resource[];
}

export async function getPublisher(username: string): Promise<PublisherProfile | undefined> {
  const live = await apiGet<PublisherProfile>(`/publishers/${username}`);
  if (live) return live;
  const u = USERS[username];
  if (!u) return undefined;
  return { ...u, resources: SEED.filter((r) => r.author?.username === username) };
}

/** Unique publishers that have public resources — derived, since the public
 *  API has no "list all" endpoint. Drives sitemap + static params. */
export async function getPublishers(): Promise<Publisher[]> {
  const seen = new Map<string, Publisher>();
  for (const r of await getResources()) {
    if (r.author && !seen.has(r.author.username)) seen.set(r.author.username, r.author);
  }
  return [...seen.values()];
}

export async function latest(n: number): Promise<Resource[]> {
  const all = await getResources();
  return [...all].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, n);
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const fmt = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);

/** Marketing one-liner derived from the canonical description (no invented field). */
export const firstSentence = (text: string) => {
  const m = text.match(/^.*?[.!?](\s|$)/);
  return (m ? m[0] : text).trim();
};

/** Avatar initials from a display name (the wire model has no `initials`). */
export const initialsOf = (name: string) => {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
};

export const yearOf = (iso?: string) => (iso ? new Date(iso).getFullYear().toString() : "");
