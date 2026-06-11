import type { Metadata } from "next";
import { Suspense } from "react";
import { MarketplaceBrowser } from "@/components/MarketplaceBrowser";
import { getResources } from "@/lib/data";

// ISR: regenerate at most once every 60s (spec §7) — no full SSR per request.
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Marketplace — browse AI skills, MCP servers & notes",
  description:
    "Browse every public skill, MCP server, and note on SkillShare. Discover and install resources published by Think41 and verified makers — no login required.",
  alternates: { canonical: "/marketplace" },
  robots: { index: true, follow: true },
};

export default async function MarketplacePage() {
  const items = await getResources();
  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-10 top-0 h-72 w-72" style={{ background: "rgba(209,255,0,0.25)" }} />
        <div className="shell relative py-16 md:py-20">
          <span className="kicker">Marketplace</span>
          <h1 className="font-display mt-4 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Every public skill, MCP, and note.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-body">
            Browse the open registry. Sign in only when you want to save a
            resource or add it to your org.
          </p>
        </div>
      </section>

      <section className="shell py-12 md:py-16">
        <Suspense fallback={<p className="text-sm font-medium text-muted">Loading registry…</p>}>
          <MarketplaceBrowser items={items} />
        </Suspense>
      </section>
    </>
  );
}
