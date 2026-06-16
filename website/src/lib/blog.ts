/**
 * Blog + changelog for the marketing site.
 *
 * Source of truth is the backend (`/api/public/blog`, `/blog/{slug}`, and
 * `/changelog`), where posts carry a draft|published status and are managed by
 * a platform admin. When `API_URL` is unset (a standalone marketing build with
 * no backend), the helpers fall back to the bundled seed below — which mirrors
 * the backend content seed (backend/scripts/seed.py → seed_content).
 */

import { publicGet } from "./api";

export type Block =
  | { type: "p"; text: string }
  | { type: "h2"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "quote"; text: string };

export type PostTag = "Release" | "Feature" | "Guide" | "Story";

export interface BlogPost {
  slug: string;
  title: string;
  /** ISO date (YYYY-MM-DD) */
  date: string;
  tag: PostTag;
  excerpt: string;
  readingMinutes: number;
  author: { name: string; role: string };
  /** Optional one-line standfirst shown under the title on the post page. */
  standfirst?: string;
  featured?: boolean;
  body: Block[];
}

export interface ChangelogEntry {
  date: string;
  tag: PostTag;
  title: string;
  body: string;
}

export const TAG_STYLE: Record<PostTag, string> = {
  Release: "bg-primary-50 text-primary",
  Feature: "bg-[#e7f0ff] text-mcp",
  Guide: "bg-[#fdece5] text-note",
  Story: "bg-surface-2 text-body",
};

// Bundled fallback — used only when no API_URL is configured. Mirrors the
// backend content seed field-for-field.
const SEED_POSTS: BlogPost[] = [
  {
    slug: "proactive-notifications",
    title: "Your team's new skills now find you",
    date: "2026-06-12",
    tag: "Feature",
    excerpt:
      "Notifications land the moment a skill, MCP server, or note is published in a scope you belong to — in the dashboard, the CLI, and right inside your AI agent.",
    readingMinutes: 4,
    featured: true,
    author: { name: "Ada Rao", role: "Product, SkillShare" },
    standfirst:
      "Discovery shouldn't depend on someone remembering to Slack you a link.",
    body: [
      {
        type: "p",
        text: "The hardest part of a shared registry was never publishing — it was discovery. Someone on your pod ships a brilliant pr-reviewer skill and you find out three weeks later, by accident. We fixed that.",
      },
      {
        type: "h2",
        text: "Scoped to what you can actually see",
      },
      {
        type: "p",
        text: "When a resource is added or published in a scope you belong to, you get a notification. Membership decides the reach: your org, your projects, and your pods — never anything outside what you already have access to. You're never notified about your own actions.",
      },
      {
        type: "ul",
        items: [
          "Dashboard: a bell with an unread count and one-click deep links.",
          "CLI: `skillshare inbox` — newest first, with a ready-to-run install command.",
          "MCP: your agent calls `check_updates` at the start of a conversation and tells you what's new before you ask.",
        ],
      },
      {
        type: "quote",
        text: "The point is that the registry comes to you. You should hear about a new team MCP from your own agent, not from a forwarded message.",
      },
      {
        type: "h2",
        text: "Install in one step",
      },
      {
        type: "p",
        text: "Every notification carries an install command and a link straight to the resource. See it, run it, done — whether you live in the dashboard, the terminal, or an AI agent.",
      },
    ],
  },
  {
    slug: "contribute-back-local-scan",
    title: "Push the skills you already have",
    date: "2026-06-12",
    tag: "Feature",
    excerpt:
      "Scan your machine for local skills, MCP servers, and notes that aren't on the platform yet — preview them with secrets redacted, then push with one approval.",
    readingMinutes: 5,
    featured: true,
    author: { name: "Ada Rao", role: "Product, SkillShare" },
    standfirst: "The best skills are the ones already sitting in your dotfiles.",
    body: [
      {
        type: "p",
        text: "Most teams already have great skills — they're just trapped in someone's local Claude Code config, a Cursor setup, or a CLAUDE.md no one else has read. Contribute-back surfaces them.",
      },
      {
        type: "h2",
        text: "Detect, redact, preview, push",
      },
      {
        type: "ul",
        items: [
          "Detectors read Claude Code (primary), Cursor, Codex, and Claude Desktop — pluggable, so more sources slot in over time.",
          "Secrets are redacted before anything leaves your machine. API keys, tokens, and credentials in MCP configs never get uploaded.",
          "You see a full redacted preview, and nothing is pushed without your explicit approval.",
          "Dismiss something once and it stays dismissed — synced to your account, so it won't nag you on another machine.",
        ],
      },
      {
        type: "quote",
        text: "Never auto-upload. MCP configs are full of credentials — the redact-and-preview step is non-negotiable, and it's enforced server-side too.",
      },
      {
        type: "h2",
        text: "Works from the CLI and your agent",
      },
      {
        type: "p",
        text: "Run `skillshare scan` to list candidates and `skillshare push --org <slug>` to contribute them. Or just mention a local skill to your AI agent — it can scan, draft the title and description from the redacted content, show you the preview, and push once you say yes.",
      },
    ],
  },
  {
    slug: "org-inheritance",
    title: "Define a skill once, inherit it everywhere",
    date: "2026-05-12",
    tag: "Guide",
    excerpt:
      "Org → project → pod inheritance means you maintain a resource in one place and every team below it gets the update automatically. Here's the mental model.",
    readingMinutes: 3,
    author: { name: "Marco Reyes", role: "Engineering, SkillShare" },
    body: [
      {
        type: "p",
        text: "Copy-paste is how skill libraries rot. A resource gets duplicated into five pods, one of them fixes a bug, and now you have five subtly different versions. Inheritance is the cure.",
      },
      {
        type: "h2",
        text: "Three levels, one source of truth",
      },
      {
        type: "ul",
        items: [
          "Org — the root. Define a resource here and everyone inherits it.",
          "Project — a body of work that groups related pods.",
          "Pod — a team. Inherits everything above it and adds its own.",
        ],
      },
      {
        type: "p",
        text: "Resolve a pod's library and you get its own resources plus everything inherited from its project and org — deduplicated, always current. Update the org-level definition and the change flows downward with no manual sync.",
      },
    ],
  },
  {
    slug: "why-a-registry",
    title: "Why your AI team needs a registry, not a folder",
    date: "2026-04-22",
    tag: "Story",
    excerpt:
      "Skills, MCP servers, and notes are real artifacts with versions, owners, and permissions. Treating them like loose files is why they drift. A registry treats them like what they are.",
    readingMinutes: 4,
    author: { name: "Ada Rao", role: "Product, SkillShare" },
    body: [
      {
        type: "p",
        text: "When AI tooling was a novelty, a shared folder of prompts was fine. It isn't anymore. Your skills encode how your team works, your MCP servers hold real credentials, and your notes are institutional memory.",
      },
      {
        type: "h2",
        text: "What a registry gives you that a folder can't",
      },
      {
        type: "ul",
        items: [
          "Versions and provenance — who published what, and when.",
          "Permissions scoped to org, project, and pod membership.",
          "Discovery that comes to you, instead of tribal knowledge.",
          "One vocabulary across the dashboard, CLI, MCP, and marketplace.",
        ],
      },
      {
        type: "p",
        text: "That last point matters most: the website, dashboard, CLI, and MCP all speak the same model. A skill is the same object everywhere you touch it. That's the difference between a tool you check and infrastructure your team relies on.",
      },
    ],
  },
];

const SEED_CHANGELOG: ChangelogEntry[] = [
  {
    date: "2026-06-12",
    tag: "Feature",
    title: "Notifications + contribute-back",
    body: "Get notified when team resources are published, and push your local skills/MCP/notes back to the platform — secrets redacted, preview first.",
  },
  {
    date: "2026-05-27",
    tag: "Release",
    title: "Public marketplace is live",
    body: "Browse every public skill, MCP server, and note without an account. Generated share cards included.",
  },
  {
    date: "2026-05-12",
    tag: "Feature",
    title: "Org-level inheritance",
    body: "Define a resource once at the org level and every project and pod inherits it automatically.",
  },
  {
    date: "2026-04-30",
    tag: "Feature",
    title: "Think41-verified publishers",
    body: "Verified makers now get a badge across the marketplace and their profile.",
  },
];

/** Published posts, newest first. Live from the backend with a seed fallback. */
export async function allPosts(): Promise<BlogPost[]> {
  const live = await publicGet<BlogPost[]>("/blog");
  if (live) return live;
  return [...SEED_POSTS].sort((a, b) => b.date.localeCompare(a.date));
}

export async function getPost(slug: string): Promise<BlogPost | undefined> {
  const live = await publicGet<BlogPost>(`/blog/${slug}`);
  if (live) return live;
  return SEED_POSTS.find((p) => p.slug === slug);
}

/** Published changelog entries, newest first. */
export async function getChangelog(): Promise<ChangelogEntry[]> {
  const live = await publicGet<ChangelogEntry[]>("/changelog");
  if (live) return live;
  return [...SEED_CHANGELOG].sort((a, b) => b.date.localeCompare(a.date));
}

export function prettyDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${months[m - 1]} ${d}, ${y}`;
}
