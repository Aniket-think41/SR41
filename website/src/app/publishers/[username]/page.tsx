import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getPublisher,
  getPublishers,
  fmt,
  initialsOf,
  yearOf,
} from "@/lib/data";
import { ResourceCard } from "@/components/ResourceCard";
import { followPublisher } from "@/lib/redirects";

export const revalidate = 60;

export async function generateStaticParams() {
  return (await getPublishers()).map((p) => ({ username: p.username }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ username: string }>;
}): Promise<Metadata> {
  const { username } = await params;
  const p = await getPublisher(username);
  if (!p) return { title: "Publisher not found" };

  // Spec §6: title = "Publisher name on SkillShare", canonical URL.
  return {
    title: `${p.display_name} on SkillShare`,
    description: p.bio,
    alternates: { canonical: `/publishers/${p.username}` },
    openGraph: {
      title: `${p.display_name} on SkillShare`,
      description: p.bio,
      type: "profile",
    },
  };
}

export default async function PublisherProfile({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;
  const p = await getPublisher(username);
  if (!p) notFound();

  const list = p.resources;
  const totalInstalls = list.reduce((s, r) => s + r.installs_count, 0);
  const totalStars = list.reduce((s, r) => s + r.stars_count, 0);

  return (
    <>
      <section className="relative overflow-hidden bg-navy text-white">
        <div className="blob -right-10 -top-10 h-72 w-72" style={{ background: "var(--color-primary)", opacity: 0.5 }} />
        <div className="shell relative py-16 md:py-20">
          <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
            <div className="flex items-center gap-5">
              <span className="flex h-20 w-20 items-center justify-center rounded-2xl bg-lime text-2xl font-bold text-ink">
                {initialsOf(p.display_name)}
              </span>
              <div>
                <h1 className="font-display text-5xl font-semibold text-white md:text-6xl">
                  {p.display_name}
                  {p.verified && <span className="ml-2 text-lime">✦</span>}
                </h1>
                <p className="mt-2 text-sm text-white/60">
                  @{p.username}{p.created_at && ` · joined ${yearOf(p.created_at)}`}
                  {p.verified && " · Think41-verified"}
                </p>
              </div>
            </div>
            <Link href={followPublisher()} className="btn btn-lime">Follow →</Link>
          </div>

          <p className="mt-8 max-w-2xl text-lg text-white/80">{p.bio}</p>

          <div className="mt-8 flex gap-10 border-t border-white/15 pt-6">
            {[
              [String(list.length), "resources"],
              [fmt(totalInstalls), "installs"],
              [fmt(totalStars), "stars"],
            ].map(([n, l]) => (
              <div key={l}>
                <div className="font-display text-3xl font-semibold text-lime">{n}</div>
                <div className="text-xs uppercase tracking-wider text-white/60">{l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="shell py-14 md:py-20">
        <h2 className="kicker">Published resources</h2>
        {list.length > 0 ? (
          <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((r) => (
              <ResourceCard key={r.id} r={r} />
            ))}
          </div>
        ) : (
          <p className="mt-6 text-body">No public resources yet.</p>
        )}
      </section>
    </>
  );
}
