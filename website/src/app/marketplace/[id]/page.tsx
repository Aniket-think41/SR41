import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getResource,
  getResources,
  TYPE_META,
  fmt,
  firstSentence,
  initialsOf,
  resourceOwner,
  ownerHref,
} from "@/lib/data";
import { addToOrg, saveResource } from "@/lib/redirects";
import { Attachments } from "@/components/Attachments";

export const revalidate = 60;

// Pre-render every known resource at build time (spec §7 — static + ISR).
export async function generateStaticParams() {
  return (await getResources()).map((r) => ({ id: r.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const r = await getResource(id);
  if (!r) return { title: "Resource not found" };

  // Spec §6: title = resource name, description = resource description,
  // og:image = generated card (opengraph-image.tsx in this segment).
  return {
    title: r.title,
    description: r.description,
    alternates: { canonical: `/marketplace/${r.id}` },
    openGraph: {
      title: `${r.title} — ${TYPE_META[r.type].label} on SkillShare`,
      description: r.description,
      type: "article",
    },
  };
}

export default async function ResourceDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const r = await getResource(id);
  if (!r) notFound();

  // Org-published resources are attributed to the org; personal ones to the author.
  const owner = resourceOwner(r);
  const ownerLink = owner ? ownerHref(owner) : null;
  const meta = TYPE_META[r.type];
  const related = (await getResources()).filter((x) => x.type === r.type && x.id !== r.id).slice(0, 3);
  const lead = firstSentence(r.description);

  const fdate = new Date(r.updated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <article>
      {/* breadcrumb */}
      <div className="bg-surface">
        <div className="shell flex items-center gap-2 py-4 text-sm">
          <Link href="/marketplace" className="font-medium text-muted hover:text-primary">marketplace</Link>
          <span className="text-muted">/</span>
          <span className="font-medium text-ink">{r.id}</span>
        </div>
      </div>

      <div className="shell grid gap-12 py-14 md:grid-cols-[1.6fr_1fr] md:py-20">
        {/* Main */}
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="tag bg-primary-50 text-primary">
              <span aria-hidden>{meta.glyph}</span> {meta.label}
            </span>
            <span className="text-sm text-muted">v{r.version}</span>
            <span className="text-sm text-muted">updated {fdate}</span>
          </div>

          <h1 className="font-display mt-5 text-5xl font-semibold md:text-6xl">{r.title}</h1>
          <p className="mt-4 text-xl text-body">{lead}</p>

          <div className="mt-10 border-t border-line pt-8">
            <h2 className="kicker">Overview</h2>
            <p className="mt-4 text-lg leading-relaxed text-body">{r.description}</p>
          </div>

          <Attachments items={r.attachments} />


          <div className="mt-8">
            <h2 className="kicker">Tags</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {r.tags.map((t) => (
                <Link key={t} href={`/marketplace?type=${r.type}`} className="tag transition hover:bg-primary-50 hover:text-primary">
                  #{t}
                </Link>
              ))}
            </div>
          </div>

          {/* install snippet */}
          <div className="mt-8">
            <h2 className="kicker">Add to your project</h2>
            <div className="mt-3 flex items-center justify-between rounded-xl bg-navy p-4 text-white">
              <code className="code text-sm">skillshare import {r.id}</code>
              <span className="text-xs text-white/50">copy</span>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <aside className="space-y-6">
          <div className="card p-6">
            {/* "Add to my org" — logged-in only; routes through login w/ redirect (spec §5) */}
            <Link href={addToOrg(r.id)} className="btn btn-primary w-full">Add to my org →</Link>
            <Link href={saveResource(r.id)} className="btn btn-secondary mt-3 w-full">☆ Sign in to save</Link>

            <dl className="mt-6 space-y-3 border-t border-line pt-6">
              {[["Installs", `↓ ${fmt(r.installs_count)}`], ["Stars", `★ ${fmt(r.stars_count)}`], ["Version", r.version]].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between">
                  <dt className="text-sm text-muted">{k}</dt>
                  <dd className="text-sm font-semibold text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Published by — the org for org-scoped resources, else the author */}
          {owner && (() => {
            const body = (
              <>
                <h2 className="kicker">Published by</h2>
                <div className="mt-3 flex items-center gap-3">
                  <span
                    className={`flex h-11 w-11 items-center justify-center rounded-full text-sm font-bold text-white ${
                      owner.kind === "org" ? "bg-ink" : "bg-primary"
                    }`}
                  >
                    {initialsOf(owner.name)}
                  </span>
                  <div>
                    <p className="font-display text-lg font-semibold">
                      {owner.name}{owner.verified && <span className="ml-1 text-primary">✦</span>}
                    </p>
                    <p className="text-sm text-muted">
                      {owner.kind === "org" ? "Organization" : owner.handle ? `@${owner.handle}` : ""}
                    </p>
                  </div>
                </div>
              </>
            );
            return ownerLink ? (
              <Link href={ownerLink} className="card card-hover block p-6">{body}</Link>
            ) : (
              <div className="card p-6">{body}</div>
            );
          })()}
        </aside>
      </div>

      {/* Related */}
      {related.length > 0 && (
        <section className="bg-surface">
          <div className="shell py-16">
            <h2 className="font-display text-3xl font-semibold">More {meta.label.toLowerCase()}s</h2>
            <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {related.map((x) => (
                <Link key={x.id} href={`/marketplace/${x.id}`} className="card card-hover group block p-6">
                  <span className="tag bg-primary-50 text-primary">
                    {TYPE_META[x.type].glyph} {TYPE_META[x.type].label}
                  </span>
                  <h3 className="font-display mt-3 text-xl font-semibold group-hover:text-primary">{x.title}</h3>
                  <p className="mt-2 line-clamp-2 text-[0.95rem] text-body">{x.description}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}
    </article>
  );
}
