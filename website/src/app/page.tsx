import Link from "next/link";
import { HeroDiagram } from "@/components/HeroDiagram";
import { SectionHead } from "@/components/SectionHead";
import { ResourceCard } from "@/components/ResourceCard";
import { latest } from "@/lib/data";
import { getStarted } from "@/lib/redirects";

const logos = ["acme", "northwind", "globex", "initech", "umbrella", "hooli"];

const steps = [
  {
    n: "01",
    title: "Create your org",
    body: "Spin up an organization in seconds. It's the root of everything — every project, pod, and resource lives inside it.",
  },
  {
    n: "02",
    title: "Build projects & pods",
    body: "Structure work the way your team actually thinks. Projects hold pods; pods hold the people and the resources they share.",
  },
  {
    n: "03",
    title: "Add resources",
    body: "Publish skills, MCP servers, and notes. Define them once at the org level and every pod inherits them automatically.",
  },
];

const orgRows = [
  ["Org", "The root. Billing, members, and the skills everyone shares.", "bg-primary"],
  ["Project", "A body of work. Groups related pods together.", "bg-primary/70"],
  ["Pod", "A team. Inherits everything above it, adds its own.", "bg-note"],
  ["Resources", "Skills · MCP servers · notes — the things you actually use.", "bg-mcp"],
];

export default function Home() {
  const preview = latest(6);

  return (
    <>
      {/* ============================== HERO ============================== */}
      <section className="relative overflow-hidden">
        <div className="blob -left-32 top-0 h-[28rem] w-[28rem]" style={{ background: "var(--color-primary-50)" }} />
        <div className="blob right-0 top-20 h-[22rem] w-[22rem]" style={{ background: "rgba(209,255,0,0.25)" }} />
        <div className="shell relative grid gap-14 py-16 md:grid-cols-[1.05fr_0.95fr] md:items-center md:py-24">
          <div>
            <div className="reveal inline-flex items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 shadow-sm">
              <span className="h-2 w-2 rounded-full bg-primary" />
              <span className="text-xs font-bold uppercase tracking-wider text-body">Skill & MCP registry · by Think41</span>
            </div>

            <h1 className="font-display reveal mt-6 text-5xl font-semibold sm:text-6xl md:text-[4.2rem]" style={{ animationDelay: "0.08s" }}>
              The skill and MCP registry your AI team{" "}
              <span className="hl">actually</span> needs.
            </h1>

            <p className="reveal mt-6 max-w-xl text-lg leading-relaxed text-body" style={{ animationDelay: "0.16s" }}>
              SkillShare by Think41 is a structured marketplace for AI skills, MCP
              servers, and team knowledge — scoped to your org, your project, or
              the world.
            </p>

            <div className="reveal mt-8 flex flex-wrap gap-3" style={{ animationDelay: "0.24s" }}>
              <Link href={getStarted()} className="btn btn-primary">
                Get started free <span aria-hidden>→</span>
              </Link>
              <Link href="/marketplace" className="btn btn-secondary">
                Explore the marketplace
              </Link>
            </div>

            <div className="reveal mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted" style={{ animationDelay: "0.3s" }}>
              <span className="flex items-center gap-1.5"><span className="text-primary">✓</span> Free tier · no card required</span>
              <span>◆ Skills · ▣ MCP · ▤ Notes</span>
            </div>
          </div>

          <div className="reveal" style={{ animationDelay: "0.2s" }}>
            <HeroDiagram />
          </div>
        </div>
      </section>

      {/* =========================== SOCIAL PROOF ========================= */}
      <section className="border-y border-line bg-surface py-9">
        <div className="shell flex flex-col gap-5 sm:flex-row sm:items-center">
          <p className="shrink-0 text-xs font-bold uppercase tracking-wider text-muted">
            Trusted by teams shipping with AI
          </p>
          <div className="relative flex-1 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
            <div className="flex w-max animate-marquee gap-12">
              {[...logos, ...logos].map((l, i) => (
                <span key={i} className="font-display text-2xl font-semibold text-ink/25">{l}</span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* =========================== ORG MODE ============================= */}
      <section>
        <div className="shell grid gap-12 py-20 md:grid-cols-2 md:items-center md:py-28">
          <div>
            <SectionHead
              kicker="Org mode"
              title={<>One place for every skill your team builds.</>}
              intro="Organized by project, pod, and inherited automatically. Define a skill once at the org level and every pod gets it — no copy-paste, no drift."
            />
            <Link href={getStarted()} className="btn btn-primary mt-8">Create your org →</Link>
          </div>

          <ul className="space-y-3">
            {orgRows.map(([t, d, color], i) => (
              <li key={t} className="card flex items-start gap-4 p-5">
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${color} text-sm font-bold text-white`}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="font-display text-xl font-semibold">{t}</h3>
                  <p className="mt-1 text-[0.95rem] text-body">{d}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ========================== PUBLIC MODE =========================== */}
      <section className="bg-navy text-white">
        <div className="shell grid gap-12 py-20 md:grid-cols-2 md:items-center md:py-28">
          <div className="order-2 md:order-1">
            <div className="rounded-[24px] border border-white/15 bg-white/5 p-6 backdrop-blur">
              <div className="flex items-center gap-3 border-b border-white/10 pb-4">
                <span className="flex h-11 w-11 items-center justify-center rounded-full bg-lime text-sm font-bold text-ink">AR</span>
                <div>
                  <p className="font-display text-lg font-semibold text-white">Ada Rao <span className="text-lime">✦</span></p>
                  <p className="text-xs text-white/60">@ada-rao · Think41-verified</p>
                </div>
                <Link href="/publishers/ada-rao" className="ml-auto rounded-full border border-white/30 px-4 py-1.5 text-sm font-semibold text-white transition hover:bg-white hover:text-navy">
                  View →
                </Link>
              </div>
              <div className="mt-4 space-y-3">
                {["◆ pr-reviewer", "◆ semantic-search"].map((s) => (
                  <div key={s} className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 p-3.5">
                    <span className="text-sm font-medium text-white">{s}</span>
                    <span className="text-xs text-lime">● published</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="order-1 md:order-2">
            <SectionHead
              invert
              kicker="Public mode"
              title={<>Publish your skills and MCPs to the world.</>}
              intro="Share what you build and grow a reputation as a Think41-verified publisher. Your work lands on the public marketplace where anyone can discover, install, and star it."
            />
            <Link href={getStarted()} className="btn btn-lime mt-8">Become a publisher →</Link>
          </div>
        </div>
      </section>

      {/* ====================== MARKETPLACE PREVIEW ======================= */}
      <section>
        <div className="shell py-20 md:py-28">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <SectionHead
              kicker="Marketplace"
              title={<>The latest from the community.</>}
              intro="Browse skills, MCP servers, and notes published by Think41 and verified makers — no login required."
            />
            <Link href="/marketplace" className="btn btn-secondary shrink-0">See all →</Link>
          </div>

          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {preview.map((r) => (
              <ResourceCard key={r.id} r={r} />
            ))}
          </div>
        </div>
      </section>

      {/* =========================== HOW IT WORKS ========================= */}
      <section className="bg-surface">
        <div className="shell py-20 md:py-28">
          <SectionHead
            center
            kicker="How it works"
            title={<>From zero to organized in three steps.</>}
          />
          <div className="mt-14 grid gap-5 md:grid-cols-3">
            {steps.map((s) => (
              <div key={s.n} className="card flex flex-col p-8">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-50 font-display text-2xl font-bold text-primary">
                  {s.n}
                </span>
                <h3 className="font-display mt-6 text-2xl font-semibold">{s.title}</h3>
                <p className="mt-3 leading-relaxed text-body">{s.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-10 flex justify-center">
            <Link href={getStarted()} className="btn btn-primary">Start building →</Link>
          </div>
        </div>
      </section>

      {/* ========================== PRICING TEASER ======================== */}
      <section className="relative overflow-hidden">
        <div className="blob left-1/2 top-0 h-80 w-80 -translate-x-1/2" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-20 text-center md:py-28">
          <div className="inline-flex items-center gap-2 rounded-full bg-lime px-4 py-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-ink">Free tier · v1</span>
          </div>
          <h2 className="font-display mx-auto mt-6 max-w-3xl text-4xl font-semibold sm:text-5xl md:text-6xl">
            Start free. Scale when your org does.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-body">
            Everything you need to organize and publish, free in v1. Team and
            enterprise plans are coming soon.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link href={getStarted()} className="btn btn-primary">Get started free →</Link>
            <Link href="/pricing" className="btn btn-secondary">See pricing</Link>
          </div>
        </div>
      </section>
    </>
  );
}
