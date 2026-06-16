"use client";

/**
 * Publisher page (dashboard) — opened by clicking a publisher on a marketplace
 * resource. Mirrors the marketing site's publisher page (navy hero, lime stats)
 * and adds Follow/Unfollow: following a publisher means you get an inbox
 * notification whenever they publish something new (backend: notify_followers).
 */

import { use } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Loader2, Plus, Store } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { fmt, initials } from "@/lib/utils";
import { ResourceCard } from "@/components/ResourceCard";
import { useToast } from "@/components/Toast";

export default function PublisherPage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = use(params);
  const { openDetail } = useUi();
  const { data: me } = useSession();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: p, isError } = useQuery({
    queryKey: qk.publisher(username),
    queryFn: () => api.publisher(username),
  });

  const followMut = useMutation({
    mutationFn: () => (p?.following ? api.unfollowPublisher(username) : api.followPublisher(username)),
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: qk.publisher(username) });
      toast(res.following ? `Following ${p?.display_name} — you'll hear about new releases` : "Unfollowed");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (isError) {
    return (
      <div className="card mx-auto max-w-lg p-10 text-center">
        <p className="text-sm text-muted">That publisher doesn&rsquo;t exist.</p>
        <Link href="/dashboard/marketplace" className="btn btn-secondary btn-sm mt-4">Back to marketplace</Link>
      </div>
    );
  }
  if (!p) return <div className="h-64 animate-pulse rounded-3xl bg-surface" />;

  const list = p.resources;
  const totalInstalls = list.reduce((s, r) => s + (r.installs_count ?? 0), 0);
  const totalStars = list.reduce((s, r) => s + r.stars_count, 0);
  // Treat "still loading" as self too, so the Follow button never flashes on
  // your own page before the session resolves (you can't follow yourself).
  const canFollow = !!me && me.id !== p.id;

  return (
    <div className="space-y-10">
      <Link href="/dashboard/marketplace" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Marketplace
      </Link>

      {/* ===== Navy hero (mirrors website/publishers/[username]) ===== */}
      <section className="relative overflow-hidden rounded-3xl bg-navy text-white">
        <div
          className="pointer-events-none absolute -right-10 -top-10 h-60 w-60 rounded-full blur-3xl"
          style={{ background: "var(--color-primary)", opacity: 0.5 }}
        />
        <div className="relative p-8 md:p-10">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div className="flex items-center gap-5">
              {p.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={p.avatar_url} alt={p.display_name} className="h-20 w-20 shrink-0 rounded-2xl object-cover" />
              ) : (
                <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-lime text-2xl font-bold text-ink">
                  {initials(p.display_name)}
                </span>
              )}
              <div className="min-w-0">
                {/* !text-white: global .font-display/h1 rule forces ink, which would
                    win over the utility on this dark hero. */}
                <h1 className="font-display text-4xl font-semibold leading-tight !text-white">
                  {p.display_name}
                  {p.verified && <span className="ml-2 !text-lime" title="Think41-verified">✦</span>}
                </h1>
                <p className="mt-1.5 text-sm text-white/60">
                  @{p.username}{p.verified && " · Think41-verified"}
                </p>
              </div>
            </div>
            {canFollow ? (
              <button
                onClick={() => followMut.mutate()}
                disabled={followMut.isPending}
                className={`btn btn-sm shrink-0 ${p.following ? "btn-secondary" : "btn-lime"}`}
              >
                {followMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : p.following ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Plus className="h-3.5 w-3.5" />
                )}
                {p.following ? "Following" : "Follow"}
              </button>
            ) : me?.id === p.id ? (
              <Link href="/dashboard/profile" className="btn btn-secondary btn-sm shrink-0">This is you → profile</Link>
            ) : null}
          </div>

          {p.bio && <p className="mt-6 max-w-2xl text-base leading-relaxed text-white/80">{p.bio}</p>}

          <div className="mt-7 flex gap-10 border-t border-white/15 pt-5">
            {[
              [String(list.length), "resources"],
              [fmt(totalInstalls), "installs"],
              [fmt(totalStars), "stars"],
              [fmt(p.followers_count), "followers"],
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
        {list.length === 0 ? (
          <p className="mt-5 rounded-2xl border border-dashed border-line p-10 text-center text-sm text-muted">
            No public resources yet.
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
