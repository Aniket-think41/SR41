import Link from "next/link";
import { getStarted } from "@/lib/redirects";

export interface LegalSection {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
}

/**
 * Shared layout for static legal/policy pages (privacy, terms). Content is
 * passed in as structured sections so a new policy page is just data.
 */
export function LegalPage({
  kicker,
  title,
  intro,
  updated,
  sections,
}: {
  kicker: string;
  title: string;
  intro: string;
  updated: string;
  sections: LegalSection[];
}) {
  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 -top-8 h-72 w-72" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-14 md:py-20">
          <span className="kicker">{kicker}</span>
          <h1 className="font-display mt-4 max-w-3xl text-4xl font-semibold sm:text-5xl md:text-6xl">
            {title}
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-body">{intro}</p>
          <p className="mt-4 text-sm text-muted">Last updated {updated}</p>
        </div>
      </section>

      <article className="shell max-w-3xl py-12 md:py-16">
        {sections.map((s) => (
          <section key={s.heading} className="mt-10 first:mt-0">
            <h2 className="font-display text-2xl font-semibold sm:text-3xl">{s.heading}</h2>
            {s.paragraphs?.map((p, i) => (
              <p key={i} className="mt-4 text-lg leading-relaxed text-body">{p}</p>
            ))}
            {s.bullets && (
              <ul className="mt-4 space-y-2.5">
                {s.bullets.map((b) => (
                  <li key={b} className="flex gap-3 text-lg leading-relaxed text-body">
                    <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}

        <div className="mt-14 rounded-[24px] border border-line bg-surface p-7 sm:p-8">
          <h2 className="font-display text-xl font-semibold">Questions?</h2>
          <p className="mt-2 text-body">
            Reach the team at{" "}
            <a href="mailto:hello@think41.com" className="font-semibold text-primary link-underline">hello@think41.com</a>.
            For product details, see{" "}
            <Link href="/home" className="font-semibold text-primary link-underline">why SkillShare</Link>{" "}
            or{" "}
            <Link href={getStarted()} className="font-semibold text-primary link-underline">get started free</Link>.
          </p>
        </div>
      </article>
    </>
  );
}
