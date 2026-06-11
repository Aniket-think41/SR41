"use client";

/**
 * My Public Resources — everything I've published to the marketplace
 * (frontend spec route map), with quick unpublish.
 */

import { useMemo } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Globe2, Store, EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useCurrentOrg, useFeature, useInvalidateResources, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import type { Resource } from "@/lib/types";
import { fmt, timeAgo } from "@/lib/utils";
import { TypeBadge } from "@/components/badges";
import { useToast } from "@/components/Toast";

export default function MyResourcesPage() {
  const { data: me } = useSession();
  const { openDetail } = useUi();
  const invalidate = useInvalidateResources();
  const { toast } = useToast();
  const username = me?.username ?? "";
  const { org } = useCurrentOrg();
  const publishing = useFeature("publishing");

  const { data: mine } = useQuery({
    queryKey: [...qk.profile(username), "resources"],
    queryFn: () => api.userResources(username, { sort: "stars" }),
    enabled: !!username,
  });

  const published = useMemo(() => (mine ?? []).filter((r) => r.is_public), [mine]);

  const unpublishMut = useMutation({
    mutationFn: (r: Resource) => api.unpublish(r.id),
    onSuccess: async (r) => {
      await invalidate();
      toast(`"${r.title}" removed from the marketplace`);
    },
  });

  return (
    <div className="mx-auto max-w-4xl">
      <p className="kicker flex items-center gap-1.5">
        <Globe2 className="h-3.5 w-3.5" /> Public presence
      </p>
      <h1 className="font-display mt-1 text-3xl font-semibold">My public resources</h1>
      <p className="mt-1.5 text-sm text-body">
        Published under <span className="font-bold text-ink">@{username}</span> — visible to everyone on the marketplace.
      </p>

      {!publishing.enabled && (
        <p className="card mt-6 border-dashed p-4 text-sm text-body">
          Marketplace publishing is currently <span className="font-bold text-ink">disabled for {org?.name}</span>
          {publishing.licensed ? " — an admin can re-enable it in settings." : " — it's a premium feature; activate a license in settings."}
        </p>
      )}

      {!me?.is_publisher && (
        <div className="card mt-6 border-dashed p-6 text-center">
          <p className="font-display text-lg font-semibold">Publisher mode is off.</p>
          <p className="mt-1 text-sm text-body">Turn it on from your profile to publish to the marketplace.</p>
          <Link href="/dashboard/profile" className="btn btn-primary btn-sm mt-4">Open my profile</Link>
        </div>
      )}

      <div className="mt-6 space-y-3">
        {published.map((r) => (
          <div key={r.id} className="card flex flex-wrap items-center gap-4 p-5">
            <button onClick={() => openDetail(r)} className="flex min-w-0 flex-1 items-center gap-4 text-left">
              <TypeBadge type={r.type} withLabel={false} />
              <span className="min-w-0">
                <span className="block truncate text-base font-bold text-ink">{r.title}</span>
                <span className="block truncate text-xs text-muted">
                  v{r.version} · ★ {fmt(r.stars_count)} · ↓ {fmt(r.installs_count ?? 0)} · updated {timeAgo(r.updated_at)}
                </span>
              </span>
            </button>
            <div className="flex shrink-0 gap-2">
              <Link href={`/dashboard/marketplace/${r.id}`} className="btn btn-secondary btn-sm">
                <Store className="h-3.5 w-3.5" /> View listing
              </Link>
              <button
                onClick={() => unpublishMut.mutate(r)}
                disabled={unpublishMut.isPending}
                className="btn btn-danger btn-sm"
              >
                <EyeOff className="h-3.5 w-3.5" /> Unpublish
              </button>
            </div>
          </div>
        ))}

        {me?.is_publisher && published.length === 0 && (
          <div className="rounded-2xl border border-dashed border-line bg-white/60 p-14 text-center">
            <p className="font-display text-xl font-semibold">Nothing published yet.</p>
            <p className="mt-1 text-sm text-body">
              Open any resource you authored and hit <span className="font-bold text-ink">Publish</span> to list it here.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
