import type { Metadata } from "next";
import Link from "next/link";
import { allPosts, getChangelog, TAG_STYLE, prettyDate } from "@/lib/blog";
import { getStarted } from "@/lib/redirects";
import { GradientVideo } from "@/components/GradientVideo";

export const metadata: Metadata = {
  title: "Blog & Changelog",
  description:
    "Product updates, release notes, and writing from the SkillShare team at Think41.",
  alternates: { canonical: "/blog" },
};

export const revalidate = 60;

export default async function Blog() {
  const [all, changelog] = await Promise.all([allPosts(), getChangelog()]);
  const [lead, ...rest] = all;

  return (
    <>
      {/* ============================== HERO ============================== */}
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 top-0 h-72 w-72" style={{ background: "rgba(209,255,0,0.25)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">Blog & changelog</span>
          <h1 className="font-display mt-4 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            What we&apos;re shipping.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-body">
            Product updates, deep dives, and release notes from the team building
            the skill &amp; MCP registry.
          </p>
        </div>
      </section>

      {/* ============================ LEAD POST =========================== */}
      {lead && (
        <section className="shell pt-14 md:pt-20">
          <Link
            href={`/blog/${lead.slug}`}
            className="card card-hover group grid gap-8 overflow-hidden p-7 md:grid-cols-[1.1fr_1fr] md:p-9"
          >
            <div className="flex flex-col justify-center">
              <div className="flex items-center gap-3">
                <span className={`tag ${TAG_STYLE[lead.tag]}`}>{lead.tag}</span>
                <span className="text-sm text-muted">{prettyDate(lead.date)} · {lead.readingMinutes} min read</span>
              </div>
              <h2 className="font-display mt-4 text-3xl font-semibold leading-tight transition group-hover:text-primary sm:text-4xl">
                {lead.title}
              </h2>
              <p className="mt-3 text-lg leading-relaxed text-body">{lead.excerpt}</p>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
                Read the post →
              </span>
            </div>
            {/* decorative gradient panel in place of a hero image */}
            <div className="relative hidden min-h-[220px] items-end overflow-hidden rounded-[20px] p-6 md:flex">
              <GradientVideo />
              <div className="relative">
                <p className="font-display text-xl font-semibold text-white">{lead.author.name}</p>
                <p className="text-sm text-white/70">{lead.author.role}</p>
              </div>
            </div>
          </Link>
        </section>
      )}

      {/* =========================== POST GRID ============================ */}
      {rest.length > 0 && (
        <section className="shell py-14 md:py-20">
          <h2 className="kicker">More writing</h2>
          <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {rest.map((p) => (
              <Link
                key={p.slug}
                href={`/blog/${p.slug}`}
                className="card card-hover group flex h-full flex-col p-6"
              >
                <div className="flex items-center gap-2">
                  <span className={`tag ${TAG_STYLE[p.tag]}`}>{p.tag}</span>
                  <span className="text-xs text-muted">{p.readingMinutes} min</span>
                </div>
                <h3 className="font-display mt-4 text-2xl font-semibold leading-tight transition group-hover:text-primary">
                  {p.title}
                </h3>
                <p className="mt-2 line-clamp-3 flex-1 text-[0.95rem] leading-relaxed text-body">
                  {p.excerpt}
                </p>
                <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
                  <span className="text-xs font-medium text-ink">{p.author.name}</span>
                  <span className="text-xs text-muted">{prettyDate(p.date)}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* ============================ CHANGELOG =========================== */}
      <section className="bg-surface">
        <div className="shell py-14 md:py-20">
          <h2 className="kicker">Changelog</h2>
          <h3 className="font-display mt-3 text-3xl font-semibold sm:text-4xl">Recently shipped.</h3>
          <div className="mt-8 space-y-5">
            {changelog.map((c) => (
              <article key={c.title} className="card grid gap-4 p-6 md:grid-cols-[180px_1fr] md:p-8">
                <div className="flex items-center gap-3 md:flex-col md:items-start">
                  <span className="text-sm font-medium text-muted">{prettyDate(c.date)}</span>
                  <span className={`tag ${TAG_STYLE[c.tag]}`}>{c.tag}</span>
                </div>
                <div>
                  <h4 className="font-display text-2xl font-semibold">{c.title}</h4>
                  <p className="mt-2 text-body">{c.body}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="mt-12 flex flex-col items-start gap-4 rounded-[24px] border border-dashed border-line bg-card p-8 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-display text-2xl font-semibold">More writing soon.</h3>
              <p className="mt-1 text-body">Subscribe by getting started — updates land in your dashboard.</p>
            </div>
            <Link href={getStarted()} className="btn btn-primary shrink-0">Get started free →</Link>
          </div>
        </div>
      </section>
    </>
  );
}
