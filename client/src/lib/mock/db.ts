/**
 * In-memory mock database, persisted to localStorage.
 *
 * Seed content intentionally matches website/src/lib/data.ts so the
 * marketing site and the dashboard tell one continuous story. When the
 * real backend ships, this whole folder is deleted and lib/api/http.ts
 * flips to the network transport — nothing else changes.
 */

import type {
  Activity,
  FeatureFlag,
  Feedback,
  Invitation,
  Notification,
  Organization,
  OrgMember,
  Payment,
  Pod,
  PodMember,
  Project,
  ProjectMember,
  Resource,
  User,
} from "../types";

/**
 * Global feature-flag catalog (BACKEND SPEC §3.8). Premium flags need an
 * org license; the rest can be toggled per org by admins.
 */
export const FEATURES: FeatureFlag[] = [
  {
    key: "marketplace",
    name: "Public marketplace",
    description: "Browse the public marketplace and import resources into the org.",
    premium: false,
    default_enabled: true,
  },
  {
    key: "publishing",
    name: "Marketplace publishing",
    description: "Let members publish org resources to the public marketplace.",
    min_plan: "PRO",
    premium: true,
    default_enabled: true,
  },
  {
    key: "command-palette",
    name: "Command palette (⌘K)",
    description: "Org-wide instant search across resources, projects, pods, and members.",
    premium: false,
    default_enabled: true,
  },
  {
    key: "activity-feed",
    name: "Activity feed",
    description: "The who-did-what timeline on the dashboard home.",
    premium: false,
    default_enabled: true,
  },
  {
    key: "notifications",
    name: "Notifications",
    description: "Notify members when resources are added or published in scopes they belong to (inbox in CLI, MCP, and the dashboard bell).",
    premium: false,
    default_enabled: true,
  },
  {
    key: "custom-terminology",
    name: "Custom terminology",
    description: "Rename Projects and Pods to match how your org works — e.g. call pods “Teams”.",
    min_plan: "PRO",
    premium: true,
    default_enabled: true,
  },
  {
    key: "integrations",
    name: "Integrations",
    description: "Connect external tools like GitHub to discover, sync, and manage resources straight from your repositories.",
    min_plan: "PRO",
    premium: true,
    default_enabled: true,
  },
];

export interface Db {
  users: User[];
  organizations: Organization[];
  org_members: OrgMember[];
  projects: Project[];
  project_members: ProjectMember[];
  pods: Pod[];
  pod_members: PodMember[];
  resources: Resource[];
  resource_stars: { id: string; resource_id: string; user_id: string }[];
  /** profile pins (GitHub-style), ordered by position */
  resource_pins: { id: string; resource_id: string; user_id: string; position: number }[];
  /** publisher follows: follower_id follows publisher_id */
  follows: { id: string; follower_id: string; publisher_id: string }[];
  /** org follows (watches): follower_id follows org_id */
  org_follows: { id: string; follower_id: string; org_id: string }[];
  invitations: Invitation[];
  activities: Activity[];
  notifications: Notification[];
  /** product feedback submitted from the dashboard / CLI / MCP */
  feedback: Feedback[];
  /** billing payments (spec §5) — populated by a paid webhook in real mode */
  payments: Payment[];
  /** per-org feature overrides (absent key → catalog default) */
  org_features: { id: string; org_id: string; key: string; enabled: boolean }[];
  /** per-org integration connections (Integrations section). No secret token in
   *  mock — only a masked hint + config, mirroring the client-safe wire shape. */
  org_integrations: {
    id: string;
    org_id: string;
    provider_key: string;
    status: "connected" | "error" | "disconnected";
    auth_method: string;
    account_label: string | null;
    account_type: string | null;
    account_url: string | null;
    account_avatar: string | null;
    token_hint: string | null;
    scopes: string[];
    capabilities: string[];
    config: Record<string, unknown>;
    last_error: string | null;
    last_synced_at: string | null;
    connected_by: string;
    created_at: string;
    updated_at: string;
  }[];
  /** resource ⇄ GitHub repo links (publish/attach layer). */
  resource_repo_links: {
    id: string;
    org_id: string;
    resource_id: string;
    provider_key: string;
    repo_full_name: string;
    repo_url: string | null;
    path: string;
    visibility: "public" | "private";
    managed: boolean;
    direction: string;
    last_pushed_at: string | null;
    last_pulled_at: string | null;
    created_at: string;
  }[];
  /** CLI/MCP device-login sessions awaiting approval on /activate */
  device_auths: {
    id: string;
    device_code: string;
    user_code: string;
    client_name: string;
    status: "pending" | "approved" | "denied";
    user_id: string | null;
  }[];
  /** id of the signed-in user, null when logged out */
  session_user_id: string | null;
}

const STORAGE_KEY = "skillshare.mockdb.v9"; // v9: plans/entitlements, review, billing

const t = (iso: string) => new Date(iso).toISOString();

const seedUsers: User[] = [
  {
    id: "u-aniket",
    email: "aniket.lnu@think41.com",
    username: "aniket",
    display_name: "Aniket Kumar",
    avatar_url: null,
    bio: "Full-stack engineer at Think41. Building SkillShare — the registry itself.",
    location: "Bengaluru, IN",
    website: "https://think41.com",
    is_publisher: true,
    verified: true,
    plan: "ENTERPRISE",
    is_admin: true, // platform admin (review queue, feedback moderation, plan grants)
    created_at: t("2025-09-12"),
    updated_at: t("2026-05-01"),
  },
  {
    id: "u-think41",
    email: "platform@think41.com",
    username: "think41",
    display_name: "Think41",
    avatar_url: null,
    bio: "The team behind SkillShare. Foundational skills and MCP servers, maintained and verified.",
    is_publisher: true,
    verified: true,
    plan: "ENTERPRISE",
    created_at: t("2025-06-01"),
    updated_at: t("2026-05-01"),
  },
  {
    id: "u-ada",
    email: "ada@example.com",
    username: "ada-rao",
    display_name: "Ada Rao",
    avatar_url: null,
    bio: "Platform engineer. I build retrieval and code-review skills for fast-moving teams.",
    is_publisher: true,
    verified: true,
    plan: "PRO",
    created_at: t("2025-07-15"),
    updated_at: t("2026-04-20"),
  },
  {
    id: "u-nilesh",
    email: "nilesh@example.com",
    username: "nilesh",
    display_name: "Nilesh Gupta",
    avatar_url: null,
    bio: "Infra & observability. MCP servers that connect agents to real production systems.",
    is_publisher: true,
    verified: false,
    plan: "FREE",
    created_at: t("2026-01-10"),
    updated_at: t("2026-05-10"),
  },
  {
    id: "u-mono",
    email: "hello@studiomono.dev",
    username: "studio-mono",
    display_name: "Studio Mono",
    avatar_url: null,
    bio: "A two-person studio shipping design-system and frontend skills for AI agents.",
    is_publisher: true,
    verified: true,
    plan: "FREE",
    created_at: t("2025-08-02"),
    updated_at: t("2026-05-02"),
  },
  {
    id: "u-priya",
    email: "priya@think41.com",
    username: "priya",
    display_name: "Priya Sharma",
    avatar_url: null,
    bio: "Product engineer, Atlas team.",
    is_publisher: false,
    plan: "FREE",
    created_at: t("2025-10-05"),
    updated_at: t("2026-04-28"),
  },
  {
    id: "u-dev",
    email: "dev@think41.com",
    username: "devraj",
    display_name: "Dev Raj",
    avatar_url: null,
    bio: "Agent infrastructure, Forge team.",
    is_publisher: false,
    plan: "FREE",
    created_at: t("2025-11-21"),
    updated_at: t("2026-05-12"),
  },
];

const seedOrgs: Organization[] = [
  {
    id: "org-think41",
    name: "Think41",
    slug: "think41",
    logo_url: null,
    description: "AI-native product studio. Home of SkillShare.",
    is_public: false,
    owner_id: "u-aniket",
    plan: "PREMIUM", // licensed — premium flags unlockable
    terminology: { project: "Project", pod: "Team" }, // pods read as "Teams" here
    created_at: t("2025-09-12"),
  },
  {
    id: "org-mono",
    name: "Studio Mono",
    slug: "studio-mono",
    logo_url: null,
    description: "Design-system and frontend skills for AI agents.",
    is_public: false,
    owner_id: "u-mono",
    plan: "FREE", // premium flags show locked — switch orgs to see it
    created_at: t("2025-08-02"),
  },
];

const seedOrgMembers: OrgMember[] = [
  { id: "om-1", org_id: "org-think41", user_id: "u-aniket", role: "ADMIN", joined_at: t("2025-09-12"), last_active: t("2026-06-05") },
  { id: "om-2", org_id: "org-think41", user_id: "u-priya", role: "MEMBER", joined_at: t("2025-10-05"), last_active: t("2026-06-04") },
  { id: "om-3", org_id: "org-think41", user_id: "u-dev", role: "MEMBER", joined_at: t("2025-11-21"), last_active: t("2026-06-03") },
  { id: "om-4", org_id: "org-think41", user_id: "u-think41", role: "ADMIN", joined_at: t("2025-09-12"), last_active: t("2026-06-01") },
  { id: "om-5", org_id: "org-mono", user_id: "u-mono", role: "ADMIN", joined_at: t("2025-08-02"), last_active: t("2026-06-02") },
  { id: "om-6", org_id: "org-mono", user_id: "u-aniket", role: "MEMBER", joined_at: t("2026-02-14"), last_active: t("2026-06-05") },
];

const seedProjects: Project[] = [
  {
    id: "proj-atlas",
    org_id: "org-think41",
    name: "Atlas — Customer Platform",
    description: "The customer-facing platform: retrieval, dashboards, and the public API.",
    tags: ["platform", "rag", "api"],
    visibility: "ORG",
    created_by: "u-aniket",
    created_at: t("2025-10-01"),
  },
  {
    id: "proj-forge",
    org_id: "org-think41",
    name: "Forge — Internal Tooling",
    description: "Agent infrastructure, CI skills, and the internal developer platform.",
    tags: ["devex", "agents", "ci"],
    visibility: "ORG",
    created_by: "u-dev",
    created_at: t("2025-11-15"),
  },
  {
    id: "proj-mono-ds",
    org_id: "org-mono",
    name: "Mono Design System",
    description: "Token pipelines and component generation skills.",
    tags: ["design", "frontend"],
    visibility: "ORG",
    created_by: "u-mono",
    created_at: t("2025-09-01"),
  },
];

const seedProjectMembers: ProjectMember[] = [
  { id: "pm-1", project_id: "proj-atlas", user_id: "u-aniket", role: "LEAD" },
  { id: "pm-2", project_id: "proj-atlas", user_id: "u-priya", role: "MEMBER" },
  { id: "pm-3", project_id: "proj-forge", user_id: "u-dev", role: "LEAD" },
  { id: "pm-4", project_id: "proj-forge", user_id: "u-aniket", role: "MEMBER" },
  { id: "pm-5", project_id: "proj-mono-ds", user_id: "u-mono", role: "LEAD" },
  { id: "pm-6", project_id: "proj-mono-ds", user_id: "u-aniket", role: "MEMBER" },
];

const seedPods: Pod[] = [
  {
    id: "pod-retrieval",
    project_id: "proj-atlas",
    name: "Retrieval Pod",
    description: "Owns search, embeddings, and answer quality across Atlas.",
    purpose_tag: "rag",
    created_by: "u-aniket",
    created_at: t("2025-10-08"),
  },
  {
    id: "pod-frontend",
    project_id: "proj-atlas",
    name: "Frontend Pod",
    description: "Dashboards, design system, and the component pipeline.",
    purpose_tag: "frontend",
    created_by: "u-priya",
    created_at: t("2025-10-20"),
  },
  {
    id: "pod-dx",
    project_id: "proj-forge",
    name: "DX Pod",
    description: "Developer experience: CI skills, release automation, agent tooling.",
    purpose_tag: "devex",
    created_by: "u-dev",
    created_at: t("2025-11-20"),
  },
  {
    id: "pod-tokens",
    project_id: "proj-mono-ds",
    name: "Tokens Pod",
    description: "Design-token extraction and validation.",
    purpose_tag: "design",
    created_by: "u-mono",
    created_at: t("2025-09-10"),
  },
];

const seedPodMembers: PodMember[] = [
  { id: "pdm-1", pod_id: "pod-retrieval", user_id: "u-aniket", role: "OWNER" },
  { id: "pdm-2", pod_id: "pod-retrieval", user_id: "u-priya", role: "MEMBER" },
  { id: "pdm-3", pod_id: "pod-frontend", user_id: "u-priya", role: "OWNER" },
  { id: "pdm-4", pod_id: "pod-frontend", user_id: "u-aniket", role: "MEMBER" },
  { id: "pdm-5", pod_id: "pod-dx", user_id: "u-dev", role: "OWNER" },
  { id: "pdm-6", pod_id: "pod-dx", user_id: "u-aniket", role: "MEMBER" },
  { id: "pdm-7", pod_id: "pod-tokens", user_id: "u-mono", role: "OWNER" },
];

const SKILL_MD = (name: string, body: string) => `# ${name}

${body}

## Usage

\`\`\`bash
claude skill add ${name.toLowerCase().replace(/\s+/g, "-")}
\`\`\`

## Inputs

- \`target\` — what to operate on
- \`effort\` — low | medium | high

## Behavior

1. Reads the target context.
2. Applies the skill prompt with the configured effort.
3. Returns a structured result with citations.
`;

/**
 * Public marketplace resources — same eight as website/src/lib/data.ts,
 * so the marketing site preview and the in-app marketplace agree.
 */
const seedPublicResources: Resource[] = [
  {
    id: "pr-reviewer",
    type: "SKILL",
    title: "PR Reviewer",
    description:
      "A reviewing skill that reads a diff and surfaces correctness bugs alongside reuse and simplification cleanups. Tunable by effort level, it leaves inline comments and a summary verdict. Built for teams that want consistent, high-signal reviews without a human on every PR.",
    content_md: SKILL_MD("PR Reviewer", "Reviews pull requests for correctness, reuse, and simplification."),
    file_url: "https://cdn.skillshare.think41.com/packages/pr-reviewer-2.4.1.skill",
    version: "2.4.1",
    tags: ["code-review", "github", "quality"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-ada",
    is_public: true,
    stars_count: 921,
    installs_count: 12840,
    created_at: t("2025-11-02"),
    updated_at: t("2026-05-20"),
  },
  {
    id: "postgres-mcp",
    type: "MCP",
    title: "Postgres MCP",
    description:
      "An MCP server that exposes a Postgres database to your agents with a read-only safety boundary, schema introspection, and query timeouts. Connection strings stay server-side; agents get structured results, never raw credentials.",
    content_md: "Read-only Postgres access for agents — schema-aware, query-safe.",
    server_url: "https://mcp.nilesh.dev/postgres",
    config_json: JSON.stringify(
      { mcpServers: { postgres: { url: "https://mcp.nilesh.dev/postgres", transport: "http", scopes: ["read"] } } },
      null,
      2
    ),
    file_url: null,
    version: "1.8.0",
    tags: ["database", "postgres", "infra"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-nilesh",
    is_public: true,
    stars_count: 654,
    installs_count: 8120,
    created_at: t("2026-01-18"),
    updated_at: t("2026-05-24"),
  },
  {
    id: "design-system-kit",
    type: "SKILL",
    title: "Design System Kit",
    description:
      "Feed it your design tokens and this skill produces accessible, on-brand React components with motion and dark-mode baked in. It enforces your spacing scale and type ramp so generated UI never drifts from the system.",
    content_md: SKILL_MD("Design System Kit", "Generate on-brand React components from a token file."),
    file_url: "https://cdn.skillshare.think41.com/packages/design-system-kit-3.1.2.skill",
    version: "3.1.2",
    tags: ["frontend", "react", "design"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-mono",
    is_public: true,
    stars_count: 510,
    installs_count: 6450,
    created_at: t("2025-10-12"),
    updated_at: t("2026-05-18"),
  },
  {
    id: "incident-runbook",
    type: "NOTE",
    title: "Incident Runbook",
    description:
      "A structured note capturing how the team runs incidents — severity definitions, the comms cadence, escalation contacts, and post-mortem template. Shared at the org level so every pod inherits the same playbook automatically.",
    content_md: `# Incident Runbook

The on-call playbook: severities, comms, and escalation paths.

## Severities

- **SEV1** — customer-facing outage. Page the on-call lead immediately.
- **SEV2** — degraded service, no data loss. Respond within 30 minutes.
- **SEV3** — internal tooling broken. Next business day.

## Comms cadence

1. Open an incident channel: \`#inc-YYYYMMDD-short-name\`.
2. Post a status update every 30 minutes, even if it's "still digging".
3. When resolved, schedule the post-mortem within 48 hours.

> Blameless by default. The system failed, not the person.
`,
    file_url: null,
    version: "1.2.0",
    tags: ["sre", "process", "on-call"],
    attachments: [
      { kind: "video", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ", title: "Incident response walkthrough", caption: "15-min screen recording of a SEV2 drill." },
      { kind: "link", url: "https://www.atlassian.com/incident-management/handbook", title: "Atlassian Incident Handbook", caption: "Reference we based our severities on." },
      { kind: "file", url: "https://cdn.skillshare.think41.com/docs/postmortem-template.md", title: "postmortem-template.md", caption: null },
    ],
    scope_type: "ORG",
    scope_id: "org-think41",
    author_id: "u-think41",
    is_public: true,
    stars_count: 388,
    installs_count: 4300,
    created_at: t("2025-12-01"),
    updated_at: t("2026-05-11"),
  },
  {
    id: "semantic-search",
    type: "SKILL",
    title: "Semantic Search",
    description:
      "A retrieval skill that chunks documents, builds embeddings, and answers questions with citations. Pluggable vector store, re-ranking, and an evaluation harness so you can measure retrieval quality before you ship.",
    content_md: SKILL_MD("Semantic Search", "Embed, index, and retrieve across your team's knowledge."),
    file_url: "https://cdn.skillshare.think41.com/packages/semantic-search-2.0.6.skill",
    version: "2.0.6",
    tags: ["rag", "search", "embeddings"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-ada",
    is_public: true,
    stars_count: 742,
    installs_count: 9870,
    created_at: t("2025-11-20"),
    updated_at: t("2026-05-22"),
  },
  {
    id: "slack-mcp",
    type: "MCP",
    title: "Slack MCP",
    description:
      "An MCP server bridging agents to Slack. Scope it to specific channels, control read vs. write, and keep tokens server-side. Useful for status updates, triage bots, and digest generation.",
    content_md: "Let agents read channels and post with scoped permissions.",
    server_url: "https://mcp.nilesh.dev/slack",
    config_json: JSON.stringify(
      { mcpServers: { slack: { url: "https://mcp.nilesh.dev/slack", transport: "http", channels: ["#eng", "#status"] } } },
      null,
      2
    ),
    file_url: null,
    version: "1.4.3",
    tags: ["slack", "messaging", "infra"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-nilesh",
    is_public: true,
    stars_count: 421,
    installs_count: 5610,
    created_at: t("2026-02-05"),
    updated_at: t("2026-05-25"),
  },
  {
    id: "changelog-writer",
    type: "SKILL",
    title: "Changelog Writer",
    description:
      "Reads merged pull requests over a range and writes a human changelog grouped by feature, fix, and chore. Pairs well with PR Reviewer for an end-to-end release flow.",
    content_md: SKILL_MD("Changelog Writer", "Turn merged PRs into a clean, grouped changelog."),
    file_url: "https://cdn.skillshare.think41.com/packages/changelog-writer-1.1.0.skill",
    version: "1.1.0",
    tags: ["release", "docs", "github"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-mono",
    is_public: true,
    stars_count: 277,
    installs_count: 3920,
    created_at: t("2026-01-05"),
    updated_at: t("2026-05-09"),
  },
  {
    id: "brand-voice",
    type: "NOTE",
    title: "Brand Voice",
    description:
      "A note defining how the company writes — voice, tone, banned phrases, and worked examples. Inherited org-wide so every skill that generates copy stays on-brand.",
    content_md: `# Brand Voice

Tone, do's and don'ts, and example copy for the whole org.

## Voice

Confident, concrete, a little playful. We explain like a sharp colleague, not a brochure.

## Don'ts

- No "unleash", "supercharge", "revolutionize".
- No exclamation marks in product UI.
- Never promise what the roadmap hasn't shipped.

## Worked example

**Before:** "Unleash the power of AI skills!!"
**After:** "Define a skill once. Every pod inherits it."
`,
    file_url: null,
    version: "1.0.4",
    tags: ["content", "brand", "writing"],
    scope_type: "ORG",
    scope_id: "org-think41",
    author_id: "u-think41",
    is_public: true,
    stars_count: 196,
    installs_count: 2880,
    created_at: t("2025-12-15"),
    updated_at: t("2026-05-06"),
  },
];

/** Org / project / pod internal resources — the daily-driver content. */
const seedInternalResources: Resource[] = [
  {
    id: "res-handbook",
    type: "NOTE",
    title: "Engineering Handbook",
    description: "How we ship at Think41 — branching, reviews, release trains, and the definition of done.",
    content_md: `# Engineering Handbook

## Branching

Trunk-based. Short-lived feature branches, squash merges, no long-running release branches.

## Reviews

Every PR gets one human review **or** a PR Reviewer skill pass at \`effort=high\`. SEV-touching code always gets both.

## Definition of done

- Tests pass.
- Docs updated.
- Feature flagged if user-facing.
`,
    file_url: null,
    version: "2.1.0",
    tags: ["process", "engineering"],
    scope_type: "ORG",
    scope_id: "org-think41",
    author_id: "u-aniket",
    is_public: false,
    stars_count: 14,
    created_at: t("2025-10-02"),
    updated_at: t("2026-05-28"),
  },
  {
    id: "res-github-mcp",
    type: "MCP",
    title: "GitHub MCP",
    description: "Org-wide GitHub access for agents: issues, PRs, and checks. Tokens stay server-side.",
    content_md: "Connect agents to the Think41 GitHub org.",
    server_url: "https://mcp.internal.think41.com/github",
    config_json: JSON.stringify(
      { mcpServers: { github: { url: "https://mcp.internal.think41.com/github", transport: "http", org: "think41" } } },
      null,
      2
    ),
    file_url: null,
    version: "1.3.0",
    tags: ["github", "infra"],
    scope_type: "ORG",
    scope_id: "org-think41",
    author_id: "u-dev",
    is_public: false,
    stars_count: 9,
    created_at: t("2025-11-25"),
    updated_at: t("2026-05-15"),
  },
  {
    id: "res-atlas-conventions",
    type: "NOTE",
    title: "Atlas API Conventions",
    description: "REST conventions for the Atlas public API — naming, pagination, errors, and versioning.",
    content_md: `# Atlas API Conventions

## Naming

Plural nouns, kebab-case paths, camelCase JSON.

## Pagination

Cursor-based: \`?cursor=...&limit=50\`. Responses carry \`next_cursor\`.

## Errors

Same envelope as SkillShare: \`{ "error": { "code", "message", "status" } }\`.
`,
    file_url: null,
    version: "1.4.0",
    tags: ["api", "conventions"],
    scope_type: "PROJECT",
    scope_id: "proj-atlas",
    author_id: "u-aniket",
    is_public: false,
    stars_count: 7,
    created_at: t("2025-10-15"),
    updated_at: t("2026-05-20"),
  },
  {
    id: "res-atlas-pg",
    type: "MCP",
    title: "Atlas Postgres MCP",
    description: "Read-only access to the Atlas staging database for retrieval experiments.",
    content_md: "Staging-only. Production access is never exposed to agents.",
    server_url: "https://mcp.internal.think41.com/atlas-pg",
    config_json: JSON.stringify(
      { mcpServers: { "atlas-pg": { url: "https://mcp.internal.think41.com/atlas-pg", transport: "http", database: "atlas_staging" } } },
      null,
      2
    ),
    file_url: null,
    version: "0.9.2",
    tags: ["postgres", "staging"],
    scope_type: "PROJECT",
    scope_id: "proj-atlas",
    author_id: "u-priya",
    is_public: false,
    stars_count: 4,
    created_at: t("2026-01-08"),
    updated_at: t("2026-05-30"),
  },
  {
    id: "res-eval-harness",
    type: "SKILL",
    title: "Retrieval Eval Harness",
    description: "Scores retrieval quality against the golden question set before every index change ships.",
    content_md: SKILL_MD("Retrieval Eval Harness", "Run the golden-set evaluation and report precision/recall deltas."),
    file_url: "https://cdn.skillshare.think41.com/packages/retrieval-eval-harness-0.6.0.skill",
    version: "0.6.0",
    tags: ["rag", "evals", "quality"],
    scope_type: "POD",
    scope_id: "pod-retrieval",
    author_id: "u-aniket",
    is_public: false,
    stars_count: 6,
    created_at: t("2026-02-12"),
    updated_at: t("2026-06-01"),
  },
  {
    id: "res-chunking",
    type: "NOTE",
    title: "Chunking Strategies",
    description: "What we learned shipping three chunkers: heading-aware beats fixed-size, tables need their own path.",
    content_md: `# Chunking Strategies

## TL;DR

Heading-aware chunking with 15% overlap won on every metric. Fixed-size 512 is the floor, not the default.

## Tables

Extract tables separately and embed a generated natural-language summary alongside the raw cells.
`,
    file_url: null,
    version: "1.1.0",
    tags: ["rag", "embeddings"],
    scope_type: "POD",
    scope_id: "pod-retrieval",
    author_id: "u-priya",
    is_public: false,
    stars_count: 5,
    created_at: t("2026-03-02"),
    updated_at: t("2026-05-26"),
  },
  {
    id: "res-component-gen",
    type: "SKILL",
    title: "Component Generator",
    description: "Generates Atlas dashboard components from our token file — wraps the public Design System Kit with house rules.",
    content_md: SKILL_MD("Component Generator", "On-brand Atlas components from design tokens."),
    file_url: null,
    version: "0.3.1",
    tags: ["frontend", "design"],
    scope_type: "POD",
    scope_id: "pod-frontend",
    author_id: "u-priya",
    is_public: false,
    stars_count: 3,
    created_at: t("2026-03-20"),
    updated_at: t("2026-05-22"),
  },
  {
    id: "res-release-skill",
    type: "SKILL",
    title: "Release Train Conductor",
    description: "Cuts the weekly release: changelog, tags, deploy checklist, and the announcement draft.",
    content_md: SKILL_MD("Release Train Conductor", "Automate the weekly release train end to end."),
    file_url: null,
    version: "1.0.0",
    tags: ["release", "ci"],
    scope_type: "POD",
    scope_id: "pod-dx",
    author_id: "u-dev",
    is_public: false,
    stars_count: 8,
    created_at: t("2026-01-30"),
    updated_at: t("2026-06-02"),
  },
  {
    id: "res-mono-tokens",
    type: "SKILL",
    title: "Token Extractor",
    description: "Pulls design tokens out of Figma files and validates them against the schema.",
    content_md: SKILL_MD("Token Extractor", "Figma → tokens.json, validated."),
    file_url: null,
    version: "2.2.0",
    tags: ["design", "figma"],
    scope_type: "POD",
    scope_id: "pod-tokens",
    author_id: "u-mono",
    is_public: false,
    stars_count: 2,
    created_at: t("2025-09-15"),
    updated_at: t("2026-05-10"),
  },
];

const seedStars = [
  { id: "st-1", resource_id: "pr-reviewer", user_id: "u-aniket" },
  { id: "st-2", resource_id: "semantic-search", user_id: "u-aniket" },
  { id: "st-3", resource_id: "incident-runbook", user_id: "u-aniket" },
  { id: "st-4", resource_id: "postgres-mcp", user_id: "u-priya" },
];

// A couple of resources the demo user has pinned to their profile.
const seedPins = [
  { id: "pin-1", resource_id: "pr-reviewer", user_id: "u-aniket", position: 0 },
  { id: "pin-2", resource_id: "res-eval-harness", user_id: "u-aniket", position: 1 },
];

// The demo user already follows Ada Rao, so the publisher page shows "Following".
const seedFollows = [{ id: "fol-1", follower_id: "u-aniket", publisher_id: "u-ada" }];

// A couple of org watchers so the org page shows a non-zero follower count.
const seedOrgFollows = [
  { id: "ofl-1", follower_id: "u-ada", org_id: "org-think41" },
  { id: "ofl-2", follower_id: "u-nilesh", org_id: "org-think41" },
];

const seedActivities: Activity[] = [
  { id: "act-1", user_id: "u-aniket", org_id: "org-think41", verb: "updated", object_type: "resource", object_id: "res-eval-harness", object_title: "Retrieval Eval Harness", meta: "v0.6.0", created_at: t("2026-06-01T10:24:00Z") },
  { id: "act-2", user_id: "u-dev", org_id: "org-think41", verb: "updated", object_type: "resource", object_id: "res-release-skill", object_title: "Release Train Conductor", meta: "v1.0.0", created_at: t("2026-06-02T08:00:00Z") },
  { id: "act-3", user_id: "u-priya", org_id: "org-think41", verb: "updated", object_type: "resource", object_id: "res-atlas-pg", object_title: "Atlas Postgres MCP", created_at: t("2026-05-30T15:40:00Z") },
  { id: "act-4", user_id: "u-aniket", org_id: "org-think41", verb: "updated", object_type: "resource", object_id: "res-handbook", object_title: "Engineering Handbook", meta: "v2.1.0", created_at: t("2026-05-28T09:12:00Z") },
  { id: "act-5", user_id: "u-priya", org_id: "org-think41", verb: "created", object_type: "resource", object_id: "res-component-gen", object_title: "Component Generator", created_at: t("2026-03-20T11:00:00Z") },
  { id: "act-6", user_id: "u-aniket", org_id: "org-think41", verb: "starred", object_type: "resource", object_id: "incident-runbook", object_title: "Incident Runbook", created_at: t("2026-05-12T13:30:00Z") },
  { id: "act-7", user_id: "u-think41", org_id: "org-think41", verb: "published", object_type: "resource", object_id: "brand-voice", object_title: "Brand Voice", created_at: t("2026-05-06T10:00:00Z") },
];

// Notifications addressed to the demo user (u-aniket) — things teammates added
// or published in scopes aniket belongs to. Mirrors the backend's fan-out (F1).
const seedNotifications: Notification[] = [
  { id: "ntf-1", actor_id: "u-priya", org_id: "org-think41", scope_type: "ORG", scope_id: "org-think41", verb: "published", object_type: "resource", object_id: "brand-voice", object_title: "Brand Voice", read_at: null, created_at: t("2026-06-14T09:30:00Z"), deep_link: "/dashboard/marketplace/brand-voice", install_command: "skillshare pull brand-voice" },
  { id: "ntf-2", actor_id: "u-dev", org_id: "org-think41", scope_type: "POD", scope_id: "pod-dx", verb: "created", object_type: "resource", object_id: "res-release-skill", object_title: "Release Train Conductor", read_at: null, created_at: t("2026-06-12T08:05:00Z"), deep_link: "/dashboard/org/resources?open=res-release-skill", install_command: "skillshare pull res-release-skill" },
  { id: "ntf-3", actor_id: "u-priya", org_id: "org-think41", scope_type: "ORG", scope_id: "org-think41", verb: "created", object_type: "resource", object_id: "res-component-gen", object_title: "Component Generator", read_at: t("2026-06-10T12:00:00Z"), created_at: t("2026-06-09T11:00:00Z"), deep_link: "/dashboard/org/resources?open=res-component-gen", install_command: "skillshare pull res-component-gen" },
];

const seedInvitations: Invitation[] = [
  {
    id: "inv-1",
    org_id: "org-think41",
    email: "maya@think41.com",
    role: "MEMBER",
    token: "tok-maya-1",
    expires_at: t("2026-06-20"),
    accepted_at: null,
  },
];

/** Two resources awaiting a public-listing decision (spec §3), so the review
 *  queues aren't empty in the demo. One PUBLIC item (→ platform-admin queue),
 *  one org-owned item published by a non-admin member (→ org-admin queue). */
const seedReviewQueue: Resource[] = [
  {
    id: "review-public-1",
    type: "SKILL",
    title: "Changelog Writer",
    description: "Turns a range of commits into a clean, categorized changelog entry.",
    content_md: "# Changelog Writer\n\nGroups commits by type and drafts release notes.",
    file_url: null,
    version: "0.2.0",
    tags: ["release", "changelog", "git"],
    scope_type: "PUBLIC",
    scope_id: null,
    author_id: "u-ada",
    is_public: true,
    approval_status: "pending",
    review_note: null,
    stars_count: 0,
    installs_count: 0,
    created_at: t("2026-06-30"),
    updated_at: t("2026-06-30"),
  },
  {
    id: "review-org-1",
    type: "NOTE",
    title: "Atlas Onboarding Notes",
    description: "How the Atlas team runs its retrieval evals — proposed for the public marketplace.",
    content_md: "# Atlas Onboarding\n\nInternal notes the team wants to share publicly.",
    file_url: null,
    version: "1.0.0",
    tags: ["onboarding", "atlas"],
    scope_type: "ORG",
    scope_id: "org-think41",
    visibility: "ORG",
    author_id: "u-priya", // a MEMBER, not an org admin → needs admin approval
    is_public: true,
    approval_status: "pending",
    review_note: null,
    stars_count: 0,
    installs_count: 0,
    created_at: t("2026-07-01"),
    updated_at: t("2026-07-01"),
  },
];

const seedFeedback: Feedback[] = [
  {
    id: "fb-seed-1",
    user_id: "u-priya",
    target_type: "platform",
    target_id: null,
    rating: 5,
    category: "praise",
    message: "The command palette is incredibly fast. Love it.",
    source: "dashboard",
    status: "open",
    public_status: "pending",
    created_at: t("2026-06-28"),
    updated_at: t("2026-06-28"),
  },
  {
    id: "fb-seed-2",
    user_id: "u-dev",
    target_type: "platform",
    target_id: null,
    rating: 3,
    category: "idea",
    message: "Would love keyboard shortcuts for publishing.",
    source: "cli",
    status: "open",
    public_status: "pending",
    created_at: t("2026-06-29"),
    updated_at: t("2026-06-29"),
  },
];

/** Public read paths only surface approved+public resources (spec §3), but
 *  most seed rows predate the review workflow — default them to "approved". */
const withApproval = (r: Resource): Resource => ({
  approval_status: "approved",
  review_note: null,
  ...r,
});

export function seed(): Db {
  return {
    users: structuredClone(seedUsers),
    organizations: structuredClone(seedOrgs),
    org_members: structuredClone(seedOrgMembers),
    projects: structuredClone(seedProjects),
    project_members: structuredClone(seedProjectMembers),
    pods: structuredClone(seedPods),
    pod_members: structuredClone(seedPodMembers),
    resources: structuredClone(
      [...seedPublicResources, ...seedInternalResources, ...seedReviewQueue].map(withApproval)
    ),
    resource_stars: structuredClone(seedStars),
    resource_pins: structuredClone(seedPins),
    follows: structuredClone(seedFollows),
    org_follows: structuredClone(seedOrgFollows),
    invitations: structuredClone(seedInvitations),
    activities: structuredClone(seedActivities),
    notifications: structuredClone(seedNotifications),
    feedback: structuredClone(seedFeedback),
    payments: [],
    org_features: [],
    org_integrations: [],
    resource_repo_links: [],
    device_auths: [],
    // Mock mode only: start signed in as the demo user so the dashboard shows
    // data without a login round-trip. (When NEXT_PUBLIC_API_URL points at a
    // real backend, the mock db isn't used and real auth applies.)
    session_user_id: "u-aniket",
  };
}

let db: Db | null = null;

export function getDb(): Db {
  if (db) return db;
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        db = JSON.parse(raw) as Db;
        return db;
      }
    } catch {
      /* corrupted storage → reseed */
    }
  }
  db = seed();
  return db;
}

export function saveDb() {
  if (db && typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
    } catch {
      /* storage full / private mode — in-memory only */
    }
  }
}

export function resetDb() {
  db = seed();
  saveDb();
}

export const uid = (prefix: string) =>
  `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
