import Link from "next/link";
import { SITE } from "@/lib/site";
import { getStarted } from "@/lib/redirects";
import { Logo } from "./Logo";

const columns = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/how-it-works" },
      { label: "Marketplace", href: "/marketplace" },
      { label: "Pricing", href: "/pricing" },
      { label: "Changelog", href: "/blog" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "Skills", href: "/marketplace?type=skill" },
      { label: "MCP servers", href: "/marketplace?type=mcp" },
      { label: "Notes", href: "/marketplace?type=note" },
      { label: "Publishers", href: "/publishers/think41" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Think41", href: "https://think41.com" },
      { label: "Blog", href: "/blog" },
      { label: "Privacy", href: "/blog" },
      { label: "Terms", href: "/blog" },
    ],
  },
];

export function Footer() {
  return (
    <footer className="bg-navy text-white">
      {/* CTA band */}
      <div className="shell pt-20">
        <div className="relative overflow-hidden rounded-[28px] bg-primary px-8 py-14 text-center sm:px-16">
          <div className="blob -right-10 -top-10 h-56 w-56" style={{ background: "var(--color-lime)", opacity: 0.35 }} />
          <h2 className="font-display relative mx-auto max-w-2xl text-3xl font-semibold text-white sm:text-4xl">
            Ready to organize your AI stack?
          </h2>
          <p className="relative mx-auto mt-3 max-w-md text-white/80">
            Free in v1. No card required. Be set up in minutes.
          </p>
          <Link href={getStarted()} className="btn btn-lime relative mt-7">
            Get started free →
          </Link>
        </div>
      </div>

      <div className="shell py-16">
        <div className="grid gap-12 md:grid-cols-[1.6fr_1fr_1fr_1fr]">
          <div>
            <Link href="/" className="flex items-center gap-2.5">
              <Logo className="h-8 w-8" />
              <span className="font-display text-xl font-semibold text-white">SkillShare</span>
            </Link>
            <p className="mt-4 max-w-xs text-[0.95rem] text-white/65">
              A structured marketplace for AI skills, MCP servers, and team
              knowledge — scoped to your org, your project, or the world.
            </p>
          </div>

          {columns.map((col) => (
            <div key={col.title}>
              <h3 className="text-xs font-bold uppercase tracking-wider text-lime">{col.title}</h3>
              <ul className="mt-5 space-y-3">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="text-[0.95rem] text-white/75 transition hover:text-white">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t border-white/15 pt-8 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-white/50">
            © {new Date().getFullYear()} {SITE.by}. SkillShare v1.0
          </p>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-lime" />
            <span className="text-sm text-white/60">Built by {SITE.by}</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
