import type { Metadata } from "next";
import Link from "next/link";
import { SectionHead } from "@/components/SectionHead";
import { getStarted } from "@/lib/redirects";

export const metadata: Metadata = {
  title: "How it works — Org mode & Public mode",
  description:
    "SkillShare runs in two modes. Org mode organizes your team's skills by project and pod with automatic inheritance. Public mode publishes your work to the world.",
  alternates: { canonical: "/how-it-works" },
};

export default function HowItWorks() {
  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob -left-20 top-0 h-96 w-96" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">How it works</span>
          <h1 className="font-display mt-4 max-w-4xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Two modes. One registry.
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-body">
            SkillShare works the same whether you&apos;re a solo builder or a
            500-person org. Keep things private and structured in{" "}
            <strong className="text-ink">Org mode</strong>, or share with the
            world in <strong className="text-ink">Public mode</strong>.
          </p>
        </div>
      </section>

      {/* ORG MODE */}
      <section>
        <div className="shell py-20 md:py-28">
          <SectionHead
            kicker="Org mode · private & structured"
            title={<>Define once. Inherited everywhere.</>}
            intro="Your org is a tree. Resources defined at a higher level flow down automatically — so a skill you publish org-wide is instantly available to every project and pod beneath it."
          />

          {/* inheritance visual */}
          <div className="mt-12 overflow-hidden rounded-[24px] border border-line shadow-[0_24px_48px_-32px_rgba(115,90,229,0.35)]">
            <div className="grid md:grid-cols-4">
              {[
                { k: "Org", d: "Root scope. The skills everyone shares.", c: "bg-primary text-white", t: "text-white", b: "text-white/75" },
                { k: "Project", d: "Groups related pods.", c: "bg-white", t: "", b: "text-body" },
                { k: "Pod", d: "A team. Inherits all of the above.", c: "bg-white", t: "", b: "text-body" },
                { k: "Resources", d: "Skills · MCP · notes, in scope.", c: "bg-white", t: "", b: "text-body" },
              ].map((col, i) => (
                <div
                  key={col.k}
                  className={`relative flex flex-col gap-3 p-8 ${col.c} ${i > 0 ? "border-t border-line md:border-l md:border-t-0" : ""}`}
                >
                  <span className={`text-sm font-bold ${col.t || "text-muted"}`}>{String(i + 1).padStart(2, "0")}</span>
                  <h3 className={`font-display text-2xl font-semibold ${col.t}`}>{col.k}</h3>
                  <p className={col.b}>{col.d}</p>
                  {i < 3 && (
                    <span aria-hidden className={`absolute right-2 top-1/2 hidden -translate-y-1/2 text-2xl md:block ${col.t || "text-muted"}`}>→</span>
                  )}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3 bg-navy px-8 py-4 text-white">
              <span aria-hidden>↳</span>
              <span className="text-sm font-medium">
                A skill added at <span className="text-lime">Org</span> is inherited by every Project, Pod, and member — no duplication.
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* PUBLIC MODE */}
      <section className="bg-navy text-white">
        <div className="shell py-20 md:py-28">
          <SectionHead
            invert
            kicker="Public mode · share with the world"
            title={<>Publish, get discovered, build a name.</>}
            intro="Flip a resource to public and it lands on the open marketplace. Anyone can browse, install, and star it — and you build a reputation as a Think41-verified publisher."
          />

          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {[
              ["Publish", "Mark any skill, MCP, or note as public from your dashboard."],
              ["Get discovered", "It appears on the marketplace, indexed and shareable with a generated card."],
              ["Grow", "Installs and stars accrue to your publisher profile."],
            ].map(([t, d], i) => (
              <div key={t} className="rounded-[20px] border border-white/15 bg-white/5 p-8 backdrop-blur">
                <span className="font-display text-5xl font-bold text-lime">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="font-display mt-4 text-2xl font-semibold text-white">{t}</h3>
                <p className="mt-2 text-white/70">{d}</p>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap gap-3">
            <Link href={getStarted()} className="btn btn-lime">Become a publisher →</Link>
            <Link href="/" className="btn btn-secondary !border-white/30 !bg-transparent !text-white hover:!bg-white hover:!text-navy">
              Browse the marketplace
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
