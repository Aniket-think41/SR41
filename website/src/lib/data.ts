/**
 * Mock content for the public marketplace. In production this is fetched
 * from the backend (the marketplace page uses ISR — revalidate every 60s).
 */

export type ResourceType = "skill" | "mcp" | "note";

export interface Publisher {
  username: string;
  name: string;
  bio: string;
  verified: boolean;
  initials: string;
  joined: string;
}

export interface Resource {
  id: string;
  name: string;
  type: ResourceType;
  summary: string;
  description: string;
  publisher: string; // username
  installs: number;
  stars: number;
  updated: string; // ISO
  tags: string[];
  version: string;
}

export const TYPE_META: Record<
  ResourceType,
  { label: string; glyph: string; color: string }
> = {
  skill: { label: "Skill", glyph: "◆", color: "var(--color-primary)" },
  mcp: { label: "MCP Server", glyph: "▣", color: "var(--color-mcp)" },
  note: { label: "Note", glyph: "▤", color: "var(--color-note)" },
};

export const publishers: Publisher[] = [
  {
    username: "think41",
    name: "Think41",
    bio: "The team behind SkillShare. Foundational skills and MCP servers, maintained and verified.",
    verified: true,
    initials: "T4",
    joined: "2025",
  },
  {
    username: "ada-rao",
    name: "Ada Rao",
    bio: "Platform engineer. I build retrieval and code-review skills for fast-moving teams.",
    verified: true,
    initials: "AR",
    joined: "2025",
  },
  {
    username: "nilesh",
    name: "Nilesh Gupta",
    bio: "Infra & observability. MCP servers that connect agents to real production systems.",
    verified: false,
    initials: "NG",
    joined: "2026",
  },
  {
    username: "studio-mono",
    name: "Studio Mono",
    bio: "A two-person studio shipping design-system and frontend skills for AI agents.",
    verified: true,
    initials: "SM",
    joined: "2025",
  },
];

export const resources: Resource[] = [
  {
    id: "pr-reviewer",
    name: "PR Reviewer",
    type: "skill",
    summary: "Reviews pull requests for correctness, reuse, and simplification.",
    description:
      "A reviewing skill that reads a diff and surfaces correctness bugs alongside reuse and simplification cleanups. Tunable by effort level, it leaves inline comments and a summary verdict. Built for teams that want consistent, high-signal reviews without a human on every PR.",
    publisher: "ada-rao",
    installs: 12840,
    stars: 921,
    updated: "2026-05-20",
    tags: ["code-review", "github", "quality"],
    version: "2.4.1",
  },
  {
    id: "postgres-mcp",
    name: "Postgres MCP",
    type: "mcp",
    summary: "Read-only Postgres access for agents — schema-aware, query-safe.",
    description:
      "An MCP server that exposes a Postgres database to your agents with a read-only safety boundary, schema introspection, and query timeouts. Connection strings stay server-side; agents get structured results, never raw credentials.",
    publisher: "nilesh",
    installs: 8120,
    stars: 654,
    updated: "2026-05-24",
    tags: ["database", "postgres", "infra"],
    version: "1.8.0",
  },
  {
    id: "design-system-kit",
    name: "Design System Kit",
    type: "skill",
    summary: "Generate on-brand React components from a token file.",
    description:
      "Feed it your design tokens and this skill produces accessible, on-brand React components with motion and dark-mode baked in. It enforces your spacing scale and type ramp so generated UI never drifts from the system.",
    publisher: "studio-mono",
    installs: 6450,
    stars: 510,
    updated: "2026-05-18",
    tags: ["frontend", "react", "design"],
    version: "3.1.2",
  },
  {
    id: "incident-runbook",
    name: "Incident Runbook",
    type: "note",
    summary: "The on-call playbook: severities, comms, and escalation paths.",
    description:
      "A structured note capturing how the team runs incidents — severity definitions, the comms cadence, escalation contacts, and post-mortem template. Shared at the org level so every pod inherits the same playbook automatically.",
    publisher: "think41",
    installs: 4300,
    stars: 388,
    updated: "2026-05-11",
    tags: ["sre", "process", "on-call"],
    version: "1.2.0",
  },
  {
    id: "semantic-search",
    name: "Semantic Search",
    type: "skill",
    summary: "Embed, index, and retrieve across your team's knowledge.",
    description:
      "A retrieval skill that chunks documents, builds embeddings, and answers questions with citations. Pluggable vector store, re-ranking, and an evaluation harness so you can measure retrieval quality before you ship.",
    publisher: "ada-rao",
    installs: 9870,
    stars: 742,
    updated: "2026-05-22",
    tags: ["rag", "search", "embeddings"],
    version: "2.0.6",
  },
  {
    id: "slack-mcp",
    name: "Slack MCP",
    type: "mcp",
    summary: "Let agents read channels and post with scoped permissions.",
    description:
      "An MCP server bridging agents to Slack. Scope it to specific channels, control read vs. write, and keep tokens server-side. Useful for status updates, triage bots, and digest generation.",
    publisher: "nilesh",
    installs: 5610,
    stars: 421,
    updated: "2026-05-25",
    tags: ["slack", "messaging", "infra"],
    version: "1.4.3",
  },
  {
    id: "changelog-writer",
    name: "Changelog Writer",
    type: "skill",
    summary: "Turn merged PRs into a clean, grouped changelog.",
    description:
      "Reads merged pull requests over a range and writes a human changelog grouped by feature, fix, and chore. Pairs well with PR Reviewer for an end-to-end release flow.",
    publisher: "studio-mono",
    installs: 3920,
    stars: 277,
    updated: "2026-05-09",
    tags: ["release", "docs", "github"],
    version: "1.1.0",
  },
  {
    id: "brand-voice",
    name: "Brand Voice",
    type: "note",
    summary: "Tone, do's and don'ts, and example copy for the whole org.",
    description:
      "A note defining how the company writes — voice, tone, banned phrases, and worked examples. Inherited org-wide so every skill that generates copy stays on-brand.",
    publisher: "think41",
    installs: 2880,
    stars: 196,
    updated: "2026-05-06",
    tags: ["content", "brand", "writing"],
    version: "1.0.4",
  },
];

export const byType = (t: ResourceType | "all") =>
  t === "all" ? resources : resources.filter((r) => r.type === t);

export const latest = (n: number) =>
  [...resources].sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, n);

export const getResource = (id: string) => resources.find((r) => r.id === id);

export const getPublisher = (username: string) =>
  publishers.find((p) => p.username === username);

export const resourcesByPublisher = (username: string) =>
  resources.filter((r) => r.publisher === username);

export const fmt = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;
