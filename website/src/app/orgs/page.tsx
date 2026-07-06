import type { Metadata } from "next";
import Link from "next/link";
import { getOrgs, initialsOf } from "@/lib/data";

export const metadata: Metadata = {
  title: "Organizations",
  description:
    "Browse organizations publishing skills, MCP servers, and team notes on SkillShare.",
  alternates: { canonical: "/orgs" },
};

export const revalidate = 60;

export default async function Orgs() {
  const orgs = await getOrgs();

  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob right-0 top-0 h-72 w-72" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 md:py-24">
          <span className="kicker">Organizations</span>
          <h1 className="font-display mt-4 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Teams publishing on SkillShare.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-body">
            Organizations that share their skills, MCP servers, and notes with
            the world. Follow the ones you want to keep up with.
          </p>
        </div>
      </section>

      <section className="shell py-14 md:py-20">
        {orgs.length > 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {orgs.map((o) => (
              <Link
                key={o.slug}
                href={`/orgs/${o.slug}`}
                className="card card-hover group flex h-full flex-col p-6"
              >
                <div className="flex items-center gap-4">
                  {o.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={o.logo_url}
                      alt=""
                      className="h-14 w-14 rounded-2xl object-cover"
                    />
                  ) : (
                    <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-lg font-bold text-white">
                      {initialsOf(o.name)}
                    </span>
                  )}
                  <div>
                    <h2 className="font-display text-2xl font-semibold leading-tight transition group-hover:text-primary">
                      {o.name}
                    </h2>
                    <p className="text-xs text-muted">@{o.slug}</p>
                  </div>
                </div>
                {o.description && (
                  <p className="mt-4 line-clamp-3 flex-1 text-[0.95rem] leading-relaxed text-body">
                    {o.description}
                  </p>
                )}
                <div className="mt-5 border-t border-line pt-4 text-xs text-muted">
                  {o.public_resources} public {o.public_resources === 1 ? "resource" : "resources"}
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <p className="text-body">No public organizations yet.</p>
        )}
      </section>
    </>
  );
}
