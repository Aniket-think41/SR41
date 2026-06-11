import type { Metadata } from "next";
import Link from "next/link";
import { getStarted } from "@/lib/redirects";

export const metadata: Metadata = {
  title: "Blog & Changelog",
  description:
    "Product updates, release notes, and writing from the SkillShare team at Think41.",
  alternates: { canonical: "/blog" },
};

const changelog = [
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

const TAG_STYLE: Record<string, string> = {
  Release: "bg-primary-50 text-primary",
  Feature: "bg-[#fdece5] text-note",
};

export default function Blog() {
  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 top-0 h-72 w-72" style={{ background: "rgba(209,255,0,0.25)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">Blog & changelog</span>
          <h1 className="font-display mt-4 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            What we&apos;re shipping.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-body">
            Long-form writing is coming soon. For now, here&apos;s the changelog.
          </p>
        </div>
      </section>

      <section className="shell py-16 md:py-20">
        <div className="space-y-5">
          {changelog.map((c) => (
            <article key={c.title} className="card grid gap-4 p-6 md:grid-cols-[180px_1fr] md:p-8">
              <div className="flex items-center gap-3 md:flex-col md:items-start">
                <span className="text-sm font-medium text-muted">{c.date}</span>
                <span className={`tag ${TAG_STYLE[c.tag]}`}>{c.tag}</span>
              </div>
              <div>
                <h2 className="font-display text-2xl font-semibold">{c.title}</h2>
                <p className="mt-2 text-body">{c.body}</p>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start gap-4 rounded-[24px] border border-dashed border-line bg-surface p-8 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-display text-2xl font-semibold">More writing soon.</h2>
            <p className="mt-1 text-body">Subscribe by getting started — updates land in your dashboard.</p>
          </div>
          <Link href={getStarted()} className="btn btn-primary shrink-0">Get started free →</Link>
        </div>
      </section>
    </>
  );
}
