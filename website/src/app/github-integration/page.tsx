import type { Metadata } from "next";
import Link from "next/link";
import { SectionHead } from "@/components/SectionHead";
import { getStarted } from "@/lib/redirects";

export const metadata: Metadata = {
  title: "GitHub Integration — Your repos are the source of truth",
  description:
    "Connect your organization's GitHub and let SkillShare discover, sync, and manage your skills, MCP servers, and notes automatically. Import public repos, keep private ones in sync, and search everything from the CLI.",
  alternates: { canonical: "/github-integration" },
};

export const revalidate = 60;

const RESOURCE_TYPES = [
  "Skill",
  "MCP",
  "Service",
  "CLI",
  "SDK",
  "API",
  "Template",
  "Agent",
  "Prompt Collection",
  "Workflow",
  "Documentation",
  "Library",
  "Plugin",
];

const SYNC_MODES = [
  {
    k: "Read only",
    d: "GitHub → SkillShare. Repos flow in and stay up to date; edits happen in Git.",
    arrow: "→",
  },
  {
    k: "Write only",
    d: "SkillShare → GitHub. Manage resources here and push changes out to repos.",
    arrow: "←",
  },
  {
    k: "Bidirectional",
    d: "GitHub ⇄ SkillShare. Whatever you change in either place is reflected in the other.",
    arrow: "⇄",
  },
  {
    k: "Manual",
    d: "Nothing happens automatically — you click Sync when you're ready.",
    arrow: "•",
  },
];

const DETECT = [
  ["awesome-mcp-server", "MCP"],
  ["skillshare-cli", "Skill"],
  ["terraform-gcp", "Template"],
  ["backend-auth-service", "Service"],
];

export default function GithubIntegration() {
  return (
    <>
      {/* HERO */}
      <section className="relative overflow-hidden bg-surface">
        <div className="blob -left-20 top-0 h-96 w-96" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">Integrations · GitHub</span>
          <h1 className="font-display mt-4 max-w-4xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Your repos are the <span className="hl">source of truth</span>.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-body">
            Connect your organization&apos;s GitHub and SkillShare turns your
            repositories into a living catalog. It{" "}
            <strong className="text-ink">discovers</strong> skills, MCP servers,
            and notes automatically, keeps them{" "}
            <strong className="text-ink">in sync</strong>, and lets your team{" "}
            <strong className="text-ink">manage everything</strong> straight
            from Git.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href={getStarted()} className="btn btn-primary">Connect GitHub →</Link>
            <Link href="/pricing" className="btn btn-secondary">See plans</Link>
          </div>
          <p className="mt-4 text-sm text-muted">
            Available on <strong className="text-ink">Pro</strong> and{" "}
            <strong className="text-ink">Enterprise</strong> organizations.
          </p>
        </div>
      </section>

      {/* THREE GOALS */}
      <section>
        <div className="shell py-20 md:py-28">
          <SectionHead
            kicker="What it does"
            title={<>Discover. Synchronize. Manage.</>}
            intro="One integration, three jobs. SkillShare finds what's already in your repos, keeps it consistent in both directions, and lets you run your catalog from GitHub if that's where your team lives."
          />

          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {[
              ["Discover", "Point us at your GitHub org and we scan every repo — public and private — reading READMEs, manifests, and topics to figure out what each one is."],
              ["Synchronize", "A README edit updates a description. A new release cuts a new version. New topics become tags. Changes flow the way you configure — one direction or both."],
              ["Manage", "Prefer Git over a database? Edit skill.yaml and README.md in the repo and SkillShare becomes the UI. Or create a fresh repo from a template in one click."],
            ].map(([t, d], i) => (
              <div key={t} className="card p-8">
                <span className="font-display text-5xl font-bold text-primary">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="font-display mt-4 text-2xl font-semibold text-ink">{t}</h3>
                <p className="mt-2 text-body">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* AUTO-DETECTION */}
      <section className="bg-navy text-white">
        <div className="shell py-20 md:py-28">
          <SectionHead
            invert
            kicker="Automatic detection"
            title={<>We read your repos so you don&apos;t have to.</>}
            intro="Instead of asking you to hand-create every resource, the parser inspects each repository — README, package.json, pyproject.toml, Dockerfile, skill.yaml, mcp.json — and classifies it. Missing metadata? AI drafts a clean summary, tags, and use cases."
          />

          <div className="mt-12 overflow-hidden rounded-[24px] border border-white/15">
            {DETECT.map(([repo, kind], i) => (
              <div
                key={repo}
                className={`flex items-center justify-between gap-4 px-6 py-5 sm:px-8 ${i > 0 ? "border-t border-white/10" : ""}`}
              >
                <code className="code text-sm text-white/85 sm:text-base">{repo}</code>
                <span aria-hidden className="text-white/40">detected as</span>
                <span className="tag !bg-lime !text-ink font-semibold">{kind}</span>
              </div>
            ))}
          </div>

          <div className="mt-10">
            <p className="text-sm font-medium uppercase tracking-wider text-lime">Recognized resource types</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {RESOURCE_TYPES.map((t) => (
                <span key={t} className="rounded-full border border-white/20 bg-white/5 px-3 py-1 text-sm text-white/80">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* SYNC MODES */}
      <section>
        <div className="shell py-20 md:py-28">
          <SectionHead
            kicker="Sync, your way"
            title={<>You decide which direction the truth flows.</>}
            intro="Every repository gets its own sync mode. Mirror in read-only, push out write-only, keep both sides live, or sync only when you say so."
          />

          <div className="mt-12 grid gap-5 sm:grid-cols-2">
            {SYNC_MODES.map((m) => (
              <div key={m.k} className="card card-hover p-8">
                <div className="flex items-center gap-3">
                  <span className="font-display text-3xl text-primary">{m.arrow}</span>
                  <h3 className="font-display text-2xl font-semibold text-ink">{m.k}</h3>
                </div>
                <p className="mt-3 text-body">{m.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PUBLIC / PRIVATE STRATEGY */}
      <section className="bg-surface">
        <div className="shell py-20 md:py-28">
          <SectionHead
            kicker="Public & private, together"
            title={<>One catalog. Two audiences.</>}
            intro="Keep a public repo with the polished, shippable resources and a private repo with drafts, roadmaps, and internal notes. Your organization sees the merged view; the world sees only what's public."
          />

          <div className="mt-12 grid gap-5 md:grid-cols-2">
            <div className="card p-8">
              <span className="tag">Public repo</span>
              <h3 className="font-display mt-4 text-2xl font-semibold text-ink">Visible to everyone</h3>
              <ul className="mt-4 space-y-2 text-body">
                {["README & docs", "Examples", "Published manifest", "Public metadata & images"].map((x) => (
                  <li key={x} className="flex gap-2"><span className="text-primary">✓</span>{x}</li>
                ))}
              </ul>
            </div>
            <div className="card p-8">
              <span className="tag !bg-note/10 !text-note">Private repo</span>
              <h3 className="font-display mt-4 text-2xl font-semibold text-ink">Organization only</h3>
              <ul className="mt-4 space-y-2 text-body">
                {["Development notes & roadmap", "Draft versions", "Design docs", "Internal assets"].map((x) => (
                  <li key={x} className="flex gap-2"><span className="text-note">•</span>{x}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* CLI / MCP */}
      <section className="bg-navy text-white">
        <div className="shell py-20 md:py-28">
          <SectionHead
            invert
            kicker="From your terminal & your agent"
            title={<>Search GitHub without leaving your flow.</>}
            intro="The GitHub integration reaches into the SkillShare CLI and MCP too. Ask your agent to pull every resource for a repo, or search connected repos straight from the command line."
          />

          <div className="mt-12 overflow-hidden rounded-[20px] border border-white/15 bg-black/30">
            <div className="flex items-center gap-2 border-b border-white/10 px-5 py-3">
              <span className="h-3 w-3 rounded-full bg-white/20" />
              <span className="h-3 w-3 rounded-full bg-white/20" />
              <span className="h-3 w-3 rounded-full bg-white/20" />
            </div>
            <pre className="code overflow-x-auto px-6 py-6 text-sm leading-relaxed text-white/85">
{`$ skillshare github search "vector database"
  acme/vecdb-mcp        MCP      ★ 342
  acme/pg-backup-cli    Skill    ★ 88

$ skillshare github resources acme/payment-service
  → 3 skills · 1 MCP · 2 notes attached

# ...or just ask your agent:
"fetch all skillshare resources for the acme/payment repo"`}
            </pre>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section>
        <div className="shell py-20 md:py-28">
          <div className="card p-10 text-center md:p-16">
            <h2 className="font-display mx-auto max-w-2xl text-3xl font-semibold text-ink sm:text-4xl">
              Turn your GitHub into a catalog.
            </h2>
            <p className="mx-auto mt-4 max-w-md text-body">
              Connect an organization on a Pro or Enterprise plan and let
              SkillShare do the discovery.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link href={getStarted()} className="btn btn-primary">Connect GitHub →</Link>
              <Link href="/how-it-works" className="btn btn-secondary">How it works</Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
