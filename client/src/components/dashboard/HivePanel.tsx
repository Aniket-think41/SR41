"use client";

/**
 * Hive (HR/directory) integration UI. Two pieces the provider config page swaps
 * in when the provider is Hive:
 *
 *  - <HiveConnect>   the connect flow: pick a Hive tenant, then "Sign in with
 *                    Hive" (OAuth popup) or paste a short-lived token.
 *  - <HivePanel>     the connected surface: Fetch the directory into staging,
 *                    review the diff (people / projects / teams, with a
 *                    pending/applied/removed badge), then selectively Apply —
 *                    everyone, by team, by project, specific people — never on
 *                    connect and never with bulk mail. Offboard removes the
 *                    members the sync created for people who have left.
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2, RefreshCw, Users, FolderKanban, Boxes, UserPlus, UserMinus,
  Check, DownloadCloud, CircleDot,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import type { HiveStagedEntity } from "@/lib/types";
import { useToast } from "@/components/Toast";

/* ------------------------------ connect ------------------------------ */

export function HiveConnect({ slug, isAdmin }: { slug: string; isAdmin: boolean }) {
  const { toast } = useToast();
  const [tenant, setTenant] = useState("");
  const [mode, setMode] = useState<"oauth" | "service_token">("oauth");
  const [token, setToken] = useState("");
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: () => api.hiveOAuthStart(slug, tenant.trim()),
    onSuccess: (r) => {
      // Open Hive's authorize page in a new tab; on success it redirects back
      // to this page (the backend stores the token) — the user returns here.
      window.open(r.authorize_url, "_blank", "noopener");
      toast("Continue in the Hive tab, then return here");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const connectToken = useMutation({
    mutationFn: () =>
      api.connectIntegration(slug, "hive", { token: token.trim(), account: tenant.trim(), auth_method: "service_token" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.integration(slug, "hive") });
      toast("Hive connected");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (!isAdmin) {
    return <div className="card p-8 text-center text-sm text-body">Only an organization admin can connect Hive.</div>;
  }

  return (
    <div className="card space-y-5 p-6">
      <div>
        <label className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Hive tenant</label>
        <input
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
          placeholder="e.g. think41"
          className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
        />
        <p className="mt-1 text-xs text-muted">
          The tenant code of your Hive workspace. Connect with an HR / allocation-manager account so the
          sync can see everyone (including leavers) and all project allocations.
        </p>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setMode("oauth")}
          className={`btn btn-sm ${mode === "oauth" ? "btn-primary" : "btn-secondary"}`}
        >Sign in with Hive</button>
        <button
          onClick={() => setMode("service_token")}
          className={`btn btn-sm ${mode === "service_token" ? "btn-primary" : "btn-secondary"}`}
        >Paste a token</button>
      </div>

      {mode === "oauth" ? (
        <button
          onClick={() => start.mutate()}
          disabled={!tenant.trim() || start.isPending}
          className="btn btn-primary"
        >
          {start.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <DownloadCloud className="h-4 w-4" />}
          Authorize in browser
        </button>
      ) : (
        <div className="space-y-2">
          <textarea
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste a short-lived Hive access token"
            rows={3}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-xs text-ink"
          />
          <button
            onClick={() => connectToken.mutate()}
            disabled={!tenant.trim() || token.trim().length < 10 || connectToken.isPending}
            className="btn btn-primary"
          >
            {connectToken.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Connect
          </button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------ connected panel ------------------------------ */

const KIND_META = {
  employee: { label: "People", Icon: Users },
  project: { label: "Projects", Icon: FolderKanban },
  group: { label: "Teams", Icon: Boxes },
} as const;

const STATUS_BADGE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  applied: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  removed: "bg-rose-100 text-rose-800 dark:bg-rose-500/15 dark:text-rose-300",
  skipped: "bg-surface-2 text-muted",
};

export function HivePanel({ slug, isAdmin }: { slug: string; isAdmin: boolean }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const staged = useQuery({
    queryKey: ["org", slug, "hive-staged"],
    queryFn: () => api.hiveStaged(slug),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["org", slug, "hive-staged"] });
    qc.invalidateQueries({ queryKey: qk.integration(slug, "hive") });
  };

  const fetchNow = useMutation({
    mutationFn: () => api.hiveFetch(slug),
    onSuccess: (s) => {
      invalidate();
      toast(`Fetched ${s.members} people, ${s.projects} projects, ${s.groups} teams`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const apply = useMutation({
    mutationFn: (body: { scope?: string; refs?: string[]; offboard?: boolean }) =>
      api.hiveApply(slug, { create_structure: true, notify: false, ...body }),
    onSuccess: (r) => {
      invalidate();
      const bits = [
        r.members_added && `+${r.members_added} members`,
        r.projects_created && `${r.projects_created} projects`,
        r.pods_created && `${r.pods_created} pods`,
        r.offboarded && `offboarded ${r.offboarded}`,
      ].filter(Boolean);
      toast(bits.length ? `Imported: ${bits.join(", ")}` : "Nothing new to import");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const counts = staged.data?.counts;
  const groups = staged.data?.groups;
  const removed = counts?.removed ?? 0;

  return (
    <section className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">Directory sync</h2>
          <p className="text-sm text-muted">
            Fetch pulls your Hive directory here for review — nobody is added until you Apply, and imports send no mail.
          </p>
          {counts && (
            <div className="mt-2 flex gap-3 text-xs text-muted">
              <span><b className="text-ink">{counts.pending}</b> pending</span>
              <span><b className="text-ink">{counts.applied}</b> applied</span>
              <span><b className="text-ink">{removed}</b> to offboard</span>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          {isAdmin && (
            <button onClick={() => fetchNow.mutate()} disabled={fetchNow.isPending} className="btn btn-secondary btn-sm">
              {fetchNow.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Fetch from Hive
            </button>
          )}
          {isAdmin && (counts?.pending ?? 0) > 0 && (
            <button onClick={() => apply.mutate({ scope: "all" })} disabled={apply.isPending} className="btn btn-primary btn-sm">
              {apply.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
              Import everything
            </button>
          )}
          {isAdmin && removed > 0 && (
            <button
              onClick={() => apply.mutate({ scope: "members", offboard: true })}
              disabled={apply.isPending}
              className="btn btn-secondary btn-sm"
            >
              <UserMinus className="h-4 w-4" /> Offboard {removed}
            </button>
          )}
        </div>
      </div>

      {staged.isLoading ? (
        <div className="card h-40 animate-pulse bg-surface-2/40" />
      ) : !groups || (!groups.employee.length && !groups.project.length && !groups.group.length) ? (
        <div className="card p-8 text-center text-sm text-body">
          Nothing staged yet. Click <b>Fetch from Hive</b> to pull your directory for review.
        </div>
      ) : (
        (["employee", "project", "group"] as const).map((kind) => (
          <StagedGroup
            key={kind}
            kind={kind}
            rows={groups[kind]}
            isAdmin={isAdmin}
            busy={apply.isPending}
            onApply={(refs) =>
              apply.mutate({ scope: kind === "employee" ? "members" : kind === "project" ? "projects" : "groups", refs })
            }
          />
        ))
      )}
    </section>
  );
}

function StagedGroup({
  kind, rows, isAdmin, busy, onApply,
}: {
  kind: "employee" | "project" | "group";
  rows: HiveStagedEntity[];
  isAdmin: boolean;
  busy: boolean;
  onApply: (refs: string[]) => void;
}) {
  const { label, Icon } = KIND_META[kind];
  const [sel, setSel] = useState<Set<string>>(new Set());
  const pending = useMemo(() => rows.filter((r) => r.status === "pending"), [rows]);

  if (!rows.length) return null;
  const toggle = (ref: string) =>
    setSel((s) => {
      const n = new Set(s);
      if (n.has(ref)) n.delete(ref);
      else n.add(ref);
      return n;
    });

  return (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 font-semibold text-ink">
          <Icon className="h-4 w-4 text-muted" /> {label}
          <span className="text-xs font-normal text-muted">({rows.length})</span>
        </h3>
        {isAdmin && pending.length > 0 && (
          <div className="flex gap-2">
            {sel.size > 0 && (
              <button onClick={() => onApply([...sel])} disabled={busy} className="btn btn-primary btn-sm">
                Import selected ({sel.size})
              </button>
            )}
            <button onClick={() => onApply(pending.map((r) => r.external_ref))} disabled={busy} className="btn btn-secondary btn-sm">
              Import all {label.toLowerCase()}
            </button>
          </div>
        )}
      </div>
      <ul className="divide-y divide-line/60">
        {rows.map((r) => (
          <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
            {isAdmin && r.status === "pending" ? (
              <input
                type="checkbox"
                checked={sel.has(r.external_ref)}
                onChange={() => toggle(r.external_ref)}
                className="h-4 w-4 rounded border-line"
              />
            ) : (
              <CircleDot className="h-4 w-4 shrink-0 text-muted/50" />
            )}
            <span className="min-w-0 flex-1 truncate text-ink">{r.display_name}</span>
            {r.email && <span className="hidden truncate text-xs text-muted sm:block">{r.email}</span>}
            <span className={`rounded-full px-2 py-0.5 text-[0.65rem] font-medium ${STATUS_BADGE[r.status] ?? ""}`}>
              {r.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
