import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { MarketplaceBrowser } from "@/components/MarketplaceBrowser";
import { HeroSearch } from "@/components/HeroSearch";
import { getMarketplaceStats, getResourcesPage, MARKETPLACE_PAGE_SIZE, fmt } from "@/lib/data";
import { getStarted } from "@/lib/redirects";

// ISR: regenerate at most once every 60s (spec §7) — no full SSR per request.
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Marketplace — browse AI skills, MCP servers & notes",
  description:
    "Browse every public skill, MCP server, and note on SkillShare by Think41. Discover and install resources published by Think41 and verified makers — no login required.",
  alternates: { canonical: "/" },
  robots: { index: true, follow: true },
};

export default async function Home() {
  // Aggregate counts for the hero, plus just the first page for the browser —
  // "Load more" fetches subsequent pages from the backend via a server action.
  const [stats, firstPage] = await Promise.all([
    getMarketplaceStats(),
    getResourcesPage({ limit: MARKETPLACE_PAGE_SIZE, offset: 0, sort: "installs" }),
  ]);

  // Counts presented as quiet inline chips (each links into a filtered view),
  // not a stark number grid.
  const chips: { glyph: string; n: number | string; label: string; href: string; color: string }[] = [
    { glyph: "◆", n: stats.skills, label: "skills", href: "/?type=skill", color: "text-primary" },
    { glyph: "▣", n: stats.mcp, label: "MCP servers", href: "/?type=mcp", color: "text-mcp" },
    { glyph: "▤", n: stats.notes, label: "notes", href: "/?type=note", color: "text-note" },
    { glyph: "↓", n: fmt(stats.total_installs), label: "installs", href: "#browse", color: "text-body" },
  ];

  return (
    <>
      {/* ===================== MARKETPLACE HERO (search-first) ===================== */}
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 -top-10 h-80 w-80" style={{ background: "rgba(209,255,0,0.20)" }} />
        <div className="blob -left-24 top-0 h-80 w-80" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 text-center md:py-20">
          <div className="reveal mx-auto inline-flex items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 shadow-sm">
            <span className="h-2 w-2 rounded-full bg-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-body">The open skill &amp; MCP registry · by Think41</span>
          </div>

          <h1 className="font-display reveal mx-auto mt-6 max-w-3xl text-4xl font-semibold sm:text-5xl md:text-[3.9rem]" style={{ animationDelay: "0.06s" }}>
            Find the skill your AI team <span className="hl">actually</span> needs.
          </h1>

          <p className="reveal mx-auto mt-5 max-w-xl text-lg leading-relaxed text-body" style={{ animationDelay: "0.12s" }}>
            Browse the open registry of skills, MCP servers, and notes — published
            by Think41 and verified makers. No login required.
          </p>

          <div className="reveal mt-8" style={{ animationDelay: "0.18s" }}>
            <HeroSearch />
          </div>

          {/* quiet stat chips — show the catalog without a stark number grid */}
          <div className="reveal mt-8 flex flex-wrap items-center justify-center gap-2.5" style={{ animationDelay: "0.24s" }}>
            {chips.map((c) => (
              <Link
                key={c.label}
                href={c.href}
                className="group inline-flex items-center gap-2 rounded-full border border-line bg-white px-4 py-2 text-sm transition hover:border-primary/40 hover:shadow-sm"
              >
                <span aria-hidden className={c.color}>{c.glyph}</span>
                <span className="font-display font-semibold text-ink">{c.n}</span>
                <span className="text-muted">{c.label}</span>
              </Link>
            ))}
          </div>

          <p className="reveal mt-6 text-sm text-muted" style={{ animationDelay: "0.3s" }}>
            New here?{" "}
            <Link href="/home" className="font-semibold text-primary link-underline">See why SkillShare →</Link>
            <span className="mx-2 text-line">·</span>
            Building a team?{" "}
            <Link href={getStarted()} className="font-semibold text-primary link-underline">Get started free →</Link>
          </p>
        </div>
      </section>

      {/* ===================== THE BROWSER (the point) =================== */}
      <section id="browse" className="shell scroll-mt-24 py-10 md:py-14">
        <Suspense fallback={<p className="text-sm font-medium text-muted">Loading registry…</p>}>
          <MarketplaceBrowser
            initialItems={firstPage.items}
            initialTotal={firstPage.total}
            pageSize={MARKETPLACE_PAGE_SIZE}
          />
        </Suspense>
      </section>
    </>
  );
}
