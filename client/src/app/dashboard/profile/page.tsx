"use client";

/**
 * My Profile — GitHub-style layout (user-requested addition to the spec):
 * identity column on the left (avatar, bio, meta, orgs, publisher toggle),
 * tabbed panel on the right (Overview with pinned resources + a lime
 * contribution graph, Resources, Stars).
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookMarked, Building2, Calendar, Globe2, Library, Link2, Loader2,
  Mail, MapPin, Pencil, Star, Store,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import type { Resource } from "@/lib/types";
import { fmt, monthYear, timeAgo, TYPE_META } from "@/lib/utils";
import { Avatar } from "@/components/Avatar";
import { ScopeBadge, TypeGlyph } from "@/components/badges";
import { useToast } from "@/components/Toast";

type Tab = "overview" | "resources" | "stars";

const TABS: { key: Tab; label: string; icon: typeof BookMarked }[] = [
  { key: "overview", label: "Overview", icon: BookMarked },
  { key: "resources", label: "Resources", icon: Library },
  { key: "stars", label: "Stars", icon: Star },
];

/* Deterministic activity heatmap (no backend telemetry yet — stable hash). */
function heatLevel(seed: string, i: number): number {
  let h = 2166136261;
  const s = `${seed}:${i}`;
  for (let j = 0; j < s.length; j++) {
    h ^= s.charCodeAt(j);
    h = Math.imul(h, 16777619);
  }
  const v = (h >>> 0) % 100;
  if (v < 46) return 0;
  if (v < 68) return 1;
  if (v < 84) return 2;
  if (v < 95) return 3;
  return 4;
}

const HEAT_COLORS = ["#eef0f3", "#eff8c0", "#e3ff65", "#c4e82a", "#94b502"];

function ContributionGraph({ seed }: { seed: string }) {
  const weeks = 26;
  return (
    <div className="thin-scroll overflow-x-auto">
      <div className="flex gap-[3px]" aria-label="Activity graph (last 6 months)">
        {Array.from({ length: weeks }).map((_, w) => (
          <div key={w} className="flex flex-col gap-[3px]">
            {Array.from({ length: 7 }).map((_, d) => {
              const lvl = heatLevel(seed, w * 7 + d);
              return (
                <span
                  key={d}
                  className="h-[11px] w-[11px] rounded-[3px]"
                  style={{ backgroundColor: HEAT_COLORS[lvl] }}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[0.65rem] text-muted">
        Less
        {HEAT_COLORS.map((c) => (
          <span key={c} className="h-[10px] w-[10px] rounded-[3px]" style={{ backgroundColor: c }} />
        ))}
        More
      </div>
    </div>
  );
}

function ResourceRow({ r, onOpen }: { r: Resource; onOpen: (r: Resource) => void }) {
  return (
    <button
      onClick={() => onOpen(r)}
      className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-surface"
    >
      <TypeGlyph type={r.type} className="w-5 text-center" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-ink">{r.title}</span>
        <span className="block truncate text-xs text-muted">{r.description}</span>
      </span>
      {r.scope_label && <ScopeBadge scope={r.scope_label} />}
      <span className="w-14 shrink-0 text-right text-xs text-muted">★ {fmt(r.stars_count)}</span>
    </button>
  );
}

export default function ProfilePage() {
  const { data: me } = useSession();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { openDetail } = useUi();
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState(false);

  const username = me?.username ?? "";
  const { data: profile } = useQuery({
    queryKey: qk.profile(username),
    queryFn: () => api.userProfile(username),
    enabled: !!username,
  });
  const { data: myResources } = useQuery({
    queryKey: [...qk.profile(username), "resources"],
    queryFn: () => api.userResources(username, { sort: "stars" }),
    enabled: !!username,
  });
  const { data: starred } = useQuery({
    queryKey: [...qk.profile(username), "starred"],
    queryFn: () => api.userStarred(username),
    enabled: !!username,
  });
  const { data: activity } = useQuery({
    queryKey: [...qk.profile(username), "activity"],
    queryFn: () => api.userActivity(username),
    enabled: !!username,
  });
  const { data: orgs } = useQuery({
    queryKey: [...qk.profile(username), "orgs"],
    queryFn: () => api.userOrgs(username),
    enabled: !!username,
  });

  // edit form state
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [location, setLocation] = useState("");
  const [website, setWebsite] = useState("");
  // hydrate the edit form once the profile loads — render-time adjust
  const [loadedId, setLoadedId] = useState<string | null>(null);
  if (profile && profile.id !== loadedId) {
    setLoadedId(profile.id);
    setDisplayName(profile.display_name);
    setBio(profile.bio);
    setLocation(profile.location ?? "");
    setWebsite(profile.website ?? "");
  }

  const saveMut = useMutation({
    mutationFn: () =>
      api.updateMe({ display_name: displayName.trim(), bio: bio.trim(), location: location.trim(), website: website.trim() }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me });
      await qc.invalidateQueries({ queryKey: qk.profile(username) });
      toast("Profile updated");
      setEditing(false);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const publisherMut = useMutation({
    mutationFn: (next: boolean) => api.updateMe({ is_publisher: next }),
    onSuccess: async (u) => {
      await qc.invalidateQueries({ queryKey: qk.me });
      await qc.invalidateQueries({ queryKey: qk.profile(username) });
      toast(u.is_publisher ? "Publisher mode on — you can publish to the marketplace" : "Publisher mode off");
    },
  });

  const pinned = useMemo(() => (myResources ?? []).slice(0, 4), [myResources]);

  if (!profile) {
    return <div className="card mx-auto h-96 max-w-4xl animate-pulse bg-surface" />;
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[290px_1fr]">
      {/* ============ Identity column ============ */}
      <aside>
        <Avatar name={profile.display_name} size="xl" className="ring-4 ring-white shadow-lg" />

        <h1 className="font-display mt-4 text-2xl font-semibold leading-tight">
          {profile.display_name}
          {profile.verified && <span className="ml-1.5 text-primary" title="Think41-verified">✦</span>}
        </h1>
        <p className="text-sm font-medium text-muted">@{profile.username}</p>

        {editing ? (
          <div className="card mt-4 space-y-3 p-4">
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="field !py-2 text-sm" placeholder="Display name" />
            <textarea value={bio} onChange={(e) => setBio(e.target.value)} className="field resize-y !py-2 text-sm" rows={3} placeholder="Bio" />
            <input value={location} onChange={(e) => setLocation(e.target.value)} className="field !py-2 text-sm" placeholder="Location" />
            <input value={website} onChange={(e) => setWebsite(e.target.value)} className="field !py-2 text-sm" placeholder="https://…" />
            <div className="flex gap-2">
              <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending} className="btn btn-primary btn-sm flex-1">
                {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
              </button>
              <button onClick={() => setEditing(false)} className="btn btn-secondary btn-sm">Cancel</button>
            </div>
          </div>
        ) : (
          <>
            <p className="mt-3 text-sm leading-relaxed text-body">{profile.bio || "No bio yet."}</p>
            <button onClick={() => setEditing(true)} className="btn btn-secondary btn-sm mt-4 w-full">
              <Pencil className="h-3.5 w-3.5" /> Edit profile
            </button>
          </>
        )}

        {/* Meta */}
        <ul className="mt-5 space-y-2 text-sm text-body">
          <li className="flex items-center gap-2"><Mail className="h-3.5 w-3.5 shrink-0 text-muted" /> {profile.email}</li>
          {profile.location && (
            <li className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5 shrink-0 text-muted" /> {profile.location}</li>
          )}
          {profile.website && (
            <li className="flex items-center gap-2">
              <Link2 className="h-3.5 w-3.5 shrink-0 text-muted" />
              <a href={profile.website} target="_blank" rel="noreferrer" className="font-semibold text-primary hover:underline">
                {profile.website.replace(/^https?:\/\//, "")}
              </a>
            </li>
          )}
          <li className="flex items-center gap-2">
            <Calendar className="h-3.5 w-3.5 shrink-0 text-muted" /> Joined {monthYear(profile.created_at)}
          </li>
        </ul>

        {/* Stats strip */}
        <div className="mt-5 flex items-center gap-4 border-y border-line py-3 text-sm">
          <span><strong className="text-ink">{profile.stats.resources}</strong> <span className="text-muted">resources</span></span>
          <span><strong className="text-ink">{fmt(profile.stats.stars_received)}</strong> <span className="text-muted">stars</span></span>
          <span><strong className="text-ink">{profile.stats.orgs}</strong> <span className="text-muted">orgs</span></span>
        </div>

        {/* Publisher toggle */}
        <div className="card mt-5 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-1.5 text-sm font-bold text-ink">
                <Store className="h-3.5 w-3.5 text-primary" /> Publisher mode
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Publish resources to the public marketplace under @{profile.username}.
              </p>
            </div>
            <button
              role="switch"
              aria-checked={profile.is_publisher}
              onClick={() => publisherMut.mutate(!profile.is_publisher)}
              disabled={publisherMut.isPending}
              className={`relative h-6 w-11 shrink-0 rounded-full transition ${profile.is_publisher ? "bg-primary" : "bg-line"}`}
            >
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-[left] ${profile.is_publisher ? "left-[22px]" : "left-0.5"}`}
              />
            </button>
          </div>
          {profile.is_publisher && (
            <Link href="/dashboard/my-resources" className="mt-3 block text-xs font-bold text-primary hover:underline">
              View my public resources →
            </Link>
          )}
        </div>

        {/* Organizations */}
        <div className="mt-5">
          <p className="mb-2 flex items-center gap-1.5 text-[0.65rem] font-bold uppercase tracking-wider text-muted">
            <Building2 className="h-3 w-3" /> Organizations
          </p>
          <div className="flex flex-wrap gap-2">
            {(orgs ?? []).map((o) => (
              <span key={o.id} title={`${o.name} · ${o.my_role}`}>
                <Avatar name={o.name} size="sm" className="!rounded-xl ring-1 ring-line" />
              </span>
            ))}
          </div>
        </div>
      </aside>

      {/* ============ Tabbed panel ============ */}
      <section className="min-w-0">
        <div className="flex gap-1 border-b border-line">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${
                tab === key ? "border-primary text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
              {key === "resources" && <span className="tag !px-2 !py-0">{myResources?.length ?? 0}</span>}
              {key === "stars" && <span className="tag !px-2 !py-0">{starred?.length ?? 0}</span>}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <div className="mt-6 space-y-8">
            {/* Pinned */}
            <div>
              <h2 className="mb-3 text-sm font-bold text-ink">Pinned</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {pinned.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => openDetail(r)}
                    className="card card-hover flex flex-col p-4 text-left"
                  >
                    <span className="flex items-center gap-2">
                      <TypeGlyph type={r.type} className="text-sm" />
                      <span className="truncate text-sm font-bold text-ink">{r.title}</span>
                      <span className="code ml-auto shrink-0 text-[0.65rem] text-muted">v{r.version}</span>
                    </span>
                    <span className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-body">{r.description}</span>
                    <span className="mt-3 flex items-center gap-3 text-[0.7rem] text-muted">
                      <span style={{ color: TYPE_META[r.type].color }}>● {TYPE_META[r.type].label}</span>
                      <span>★ {fmt(r.stars_count)}</span>
                      {r.is_public && <span className="flex items-center gap-0.5"><Globe2 className="h-3 w-3" /> public</span>}
                    </span>
                  </button>
                ))}
                {pinned.length === 0 && (
                  <p className="col-span-full rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">
                    Resources you author show up here.
                  </p>
                )}
              </div>
            </div>

            {/* Contribution graph */}
            <div>
              <h2 className="mb-3 text-sm font-bold text-ink">
                {profile.stats.resources + profile.stats.stars_given} contributions in the registry
              </h2>
              <div className="card p-5">
                <ContributionGraph seed={profile.username} />
              </div>
            </div>

            {/* Activity */}
            <div>
              <h2 className="mb-3 text-sm font-bold text-ink">Recent activity</h2>
              <ol className="card divide-y divide-line p-2">
                {(activity ?? []).slice(0, 6).map((a) => (
                  <li key={a.id} className="flex items-center gap-3 px-3 py-3 text-sm">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                    <span className="min-w-0 flex-1 truncate">
                      <span className="text-body">{a.verb}</span>{" "}
                      <span className="font-bold text-ink">{a.object_title}</span>
                      {a.meta && <span className="text-muted"> · {a.meta}</span>}
                    </span>
                    <span className="shrink-0 text-xs text-muted">{timeAgo(a.created_at)}</span>
                  </li>
                ))}
                {activity?.length === 0 && (
                  <li className="px-3 py-8 text-center text-sm text-muted">No activity yet.</li>
                )}
              </ol>
            </div>
          </div>
        )}

        {tab === "resources" && (
          <div className="card mt-6 p-2">
            {(myResources ?? []).map((r) => (
              <ResourceRow key={r.id} r={r} onOpen={openDetail} />
            ))}
            {myResources?.length === 0 && (
              <p className="px-3 py-12 text-center text-sm text-muted">You haven&rsquo;t authored any resources yet.</p>
            )}
          </div>
        )}

        {tab === "stars" && (
          <div className="card mt-6 p-2">
            {(starred ?? []).map((r) => (
              <ResourceRow key={r.id} r={r} onOpen={openDetail} />
            ))}
            {starred?.length === 0 && (
              <p className="px-3 py-12 text-center text-sm text-muted">Star resources to find them again fast.</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
