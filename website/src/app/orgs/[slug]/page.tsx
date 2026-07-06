import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { getOrg, getOrgs, fmt, initialsOf, yearOf } from "@/lib/data";
import { ResourceCard } from "@/components/ResourceCard";
import { followOrg } from "@/lib/redirects";

export const revalidate = 60;

export async function generateStaticParams() {
  return (await getOrgs()).map((o) => ({ slug: o.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const org = await getOrg(slug);
  if (!org) return { title: "Organization not found" };

  return {
    title: `${org.name} on SkillShare`,
    description: org.description ?? `${org.name} on SkillShare`,
    alternates: { canonical: `/orgs/${org.slug}` },
    openGraph: {
      title: `${org.name} on SkillShare`,
      description: org.description ?? undefined,
      type: "profile",
    },
  };
}

export default async function OrgProfilePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const org = await getOrg(slug);
  if (!org) notFound();

  const list = org.resources ?? [];
  const totalInstalls = list.reduce((s, r) => s + r.installs_count, 0);
  const totalStars = list.reduce((s, r) => s + r.stars_count, 0);

  return (
    <>
      <section className="relative overflow-hidden bg-navy text-white">
        <div className="blob -right-10 -top-10 h-72 w-72" style={{ background: "var(--color-primary)", opacity: 0.5 }} />
        <div className="shell relative py-16 md:py-20">
          <div className="flex flex-col gap-8 md:flex-row md:items-end md:justify-between">
            <div className="flex items-center gap-5">
              {org.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={org.logo_url} alt="" className="h-20 w-20 rounded-2xl object-cover" />
              ) : (
                <span className="flex h-20 w-20 items-center justify-center rounded-2xl bg-lime text-2xl font-bold text-ink">
                  {initialsOf(org.name)}
                </span>
              )}
              <div>
                <h1 className="font-display text-5xl font-semibold text-white md:text-6xl">
                  {org.name}
                </h1>
                <p className="mt-2 text-sm text-white/60">
                  @{org.slug}
                  {org.created_at && ` · joined ${yearOf(org.created_at)}`}
                </p>
              </div>
            </div>
            <Link href={followOrg(org.slug)} className="btn btn-lime">
              {org.following ? "Following" : "Follow"} →
            </Link>
          </div>

          {org.description && (
            <p className="mt-8 max-w-2xl text-lg text-white/80">{org.description}</p>
          )}

          <div className="mt-8 flex gap-10 border-t border-white/15 pt-6">
            {[
              [String(list.length), "resources"],
              [fmt(org.followers_count), "followers"],
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
        <h2 className="kicker">Public resources</h2>
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
