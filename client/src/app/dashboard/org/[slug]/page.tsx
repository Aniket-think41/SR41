"use client";

/**
 * Org page — a member-facing "org profile" reached by clicking an organization
 * on your profile. Mirrors the marketing site's publisher page
 * (website/src/app/publishers/[username]) — navy hero, lime stat row, and a
 * grid of everything the org has published to the marketplace.
 */

import { use } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Globe2, Loader2, Plus, Store } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { fmt, initials } from "@/lib/utils";
import { ResourceCard } from "@/components/ResourceCard";
import { useToast } from "@/components/Toast";

export default function OrgPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const { openDetail } = useUi();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: org, isError } = useQuery({
    queryKey: qk.org(slug),
    queryFn: () => api.org(slug),
  });

  const followMut = useMutation({
    mutationFn: () => (org?.following ? api.unfollowOrg(slug) : api.followOrg(slug)),
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: qk.org(slug) });
      toast(res.following ? `Following ${org?.name} — you'll hear about new releases` : "Unfollowed");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const { data: published } = useQuery({
    queryKey: qk.orgPublished(slug),
    queryFn: () => api.orgPublished(slug),
    enabled: !!org,
  });

  if (isError) {
    return (
      <div className="card mx-auto max-w-lg p-10 text-center">
        <p className="text-sm text-muted">You don&rsquo;t have access to this organization, or it doesn&rsquo;t exist.</p>
        <Link href="/dashboard/profile" className="btn btn-secondary btn-sm mt-4">Back to profile</Link>
      </div>
    );
  }

  if (!org) {
    return <div className="h-64 animate-pulse rounded-3xl bg-surface" />;
  }

  const list = published ?? [];
  const totalInstalls = list.reduce((s, r) => s + (r.installs_count ?? 0), 0);
  const totalStars = list.reduce((s, r) => s + r.stars_count, 0);

  return (
    <div className="space-y-10">
      <Link href="/dashboard/profile" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Back to profile
      </Link>

      {/* ===== Navy hero (mirrors the website publisher page) ===== */}
      <section className="relative overflow-hidden rounded-3xl bg-navy text-white">
        <div
          className="pointer-events-none absolute -right-10 -top-10 h-60 w-60 rounded-full blur-3xl"
          style={{ background: "var(--color-primary)", opacity: 0.5 }}
        />
        <div className="relative p-8 md:p-10">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="flex items-center gap-5">
              {org.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={org.logo_url} alt={org.name} className="h-20 w-20 shrink-0 rounded-2xl object-cover" />
              ) : (
                <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-lime text-2xl font-bold text-ink">
                  {initials(org.name)}
                </span>
              )}
              <div className="min-w-0">
                {/* !text-white: the global `.font-display`/`h1` rule forces ink and
                    would otherwise win over the utility on this dark hero. */}
                <h1 className="font-display text-4xl font-semibold leading-tight !text-white">{org.name}</h1>
                <p className="mt-1.5 text-sm text-white/60">
                  @{org.slug} · {org.plan} · you&rsquo;re {org.my_role === "ADMIN" ? "an admin" : "a member"}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => followMut.mutate()}
                disabled={followMut.isPending}
                className={`btn btn-sm ${org.following ? "btn-secondary" : "btn-lime"}`}
              >
                {followMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : org.following ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Plus className="h-3.5 w-3.5" />
                )}
                {org.following ? "Following" : "Follow"}
              </button>
              {org.my_role === "ADMIN" && (
                <Link href="/dashboard/org/settings" className="btn btn-secondary btn-sm">Manage →</Link>
              )}
            </div>
          </div>

          {org.description && <p className="mt-6 max-w-2xl text-base leading-relaxed text-white/80">{org.description}</p>}

          <div className="mt-7 flex gap-10 border-t border-white/15 pt-5">
            {[
              [String(list.length), "published"],
              [fmt(totalInstalls), "installs"],
              [fmt(totalStars), "stars"],
              [fmt(org.followers_count ?? 0), "followers"],
            ].map(([n, l]) => (
              <div key={l}>
                <div className="font-display text-3xl font-semibold !text-lime">{n}</div>
                <div className="text-xs uppercase tracking-wider text-white/60">{l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== Published resources ===== */}
      <section>
        <h2 className="kicker flex items-center gap-1.5">
          <Store className="h-3.5 w-3.5" /> Published resources
        </h2>
        {published === undefined ? (
          <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <div key={i} className="card h-40 animate-pulse bg-surface" />)}
          </div>
        ) : list.length === 0 ? (
          <p className="mt-5 flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line p-10 text-center text-sm text-muted">
            <Globe2 className="h-5 w-5" />
            {org.name} hasn&rsquo;t published anything to the marketplace yet.
          </p>
        ) : (
          <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((r) => (
              <ResourceCard key={r.id} resource={r} onOpen={openDetail} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
