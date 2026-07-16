"use client";

/**
 * "Attached repositories" for a scope (org / team / pod), shown in the scope's
 * SETTINGS. Renders only when GitHub is connected. Attach an EXISTING repo (from
 * a dropdown of the org's repos) or CREATE a new one (public/private), pick which
 * resources route to it and the sync direction, and attach several. A public
 * repo can only ever hold public resources (enforced here and server-side).
 * Managed by the scope's admin; the backend enforces the org⊃team⊃pod cascade.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Github, Loader2, Trash2, RefreshCw, Plus, Globe, Lock, Layers,
  ArrowRight, ArrowLeftRight, ArrowLeft,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { useCurrentOrg, useIntegration } from "@/lib/hooks";
import { useToast } from "@/components/Toast";

const DIRECTIONS = [
  { key: "push", label: "Push", hint: "SkillShare → GitHub", icon: ArrowRight },
  { key: "pull", label: "Pull", hint: "GitHub → SkillShare", icon: ArrowLeft },
  { key: "both", label: "Both", hint: "Keep in sync", icon: ArrowLeftRight },
] as const;

const ROUTES = [
  { key: "all", label: "All resources" },
  { key: "public", label: "Public only" },
  { key: "private", label: "Private only" },
] as const;

export function ScopeRepoLinks({
  scopeType,
  scopeId,
  title = "Attached repositories",
}: {
  scopeType: "ORG" | "PROJECT" | "POD";
  scopeId: string;
  title?: string;
}) {
  const { org } = useCurrentOrg();
  const gh = useIntegration("github");
  const { toast } = useToast();
  const qc = useQueryClient();
  const slug = org?.slug ?? "";
  const isAdmin = org?.my_role === "ADMIN"; // backend enforces scope-level; this just avoids showing dead controls

  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [repo, setRepo] = useState("");
  const [newName, setNewName] = useState("");
  const [newPrivate, setNewPrivate] = useState(true);
  const [route, setRoute] = useState<"all" | "public" | "private">("all");
  const [direction, setDirection] = useState<"push" | "pull" | "both">("push");

  const key = ["org", slug, "scope-links", scopeType, scopeId] as const;
  const links = useQuery({
    queryKey: key,
    queryFn: () => api.githubScopeLinks(slug, { scope_type: scopeType, scope_id: scopeId }),
    enabled: !!slug && !!scopeId && !!gh.data?.connected,
  });
  // Repos for the dropdown — fetched only when the attach form is open.
  const repos = useQuery({
    queryKey: ["org", slug, "gh-repos-picker"],
    queryFn: () => api.githubIntegrationRepos(slug),
    enabled: open && mode === "existing" && !!slug,
  });

  const selectedRepo = repos.data?.find((r) => r.full_name === repo);
  // A public target repo may only route public resources.
  const repoIsPublic = mode === "existing" ? selectedRepo?.private === false : !newPrivate;
  const effRoute: "all" | "public" | "private" = repoIsPublic ? "public" : route;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["org", slug, "scope-links"] });

  const attach = useMutation({
    mutationFn: () =>
      api.githubAttachScope(slug, {
        scope_type: scopeType,
        scope_id: scopeId,
        ...(mode === "existing" ? { repo_full_name: repo } : { create_repo_name: newName.trim(), create_private: newPrivate }),
        visibility: effRoute,
        sync_direction: direction,
      }),
    onSuccess: () => { invalidate(); setOpen(false); setRepo(""); setNewName(""); toast("Repository attached"); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const detach = useMutation({
    mutationFn: (id: string) => api.githubDetachScope(slug, id),
    onSuccess: () => { invalidate(); toast("Detached"); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const sync = useMutation({
    mutationFn: (id: string) => api.githubScopeSync(slug, id),
    onSuccess: (r) => { invalidate(); toast(`Pushed ${r.pushed}, imported ${r.imported ?? 0}`); },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (!gh.data?.connected) return null;

  const canSubmit = mode === "existing" ? !!repo : newName.trim().length >= 1;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Github className="h-4 w-4 text-ink" />
          <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
        </div>
        {isAdmin && !open && (
          <button onClick={() => setOpen(true)} className="btn btn-primary btn-sm"><Plus className="h-3.5 w-3.5" /> Attach repo</button>
        )}
      </div>
      <p className="mt-1 text-sm text-body">
        Attach GitHub repos to this {scopeType === "POD" ? "pod" : scopeType === "PROJECT" ? "team" : "organization"}.
        New resources here auto-sync per the direction you choose. A public repo only ever holds public resources.
      </p>

      {open && isAdmin && (
        <div className="mt-4 space-y-4 rounded-xl border border-line p-4">
          {/* existing vs new */}
          <div className="inline-flex overflow-hidden rounded-lg border border-line text-xs">
            {(["existing", "new"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)} className={`px-3 py-1.5 ${mode === m ? "bg-primary text-white" : "text-body hover:bg-surface"}`}>
                {m === "existing" ? "Choose existing" : "Create new"}
              </button>
            ))}
          </div>

          {mode === "existing" ? (
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">Repository</span>
              {repos.isLoading ? (
                <div className="mt-1.5 flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading your repos…</div>
              ) : (
                <select value={repo} onChange={(e) => setRepo(e.target.value)} className="field mt-1.5 w-full">
                  <option value="">Select a repository…</option>
                  {(repos.data ?? []).map((r) => (
                    <option key={r.full_name} value={r.full_name}>{r.full_name} {r.private ? "(private)" : "(public)"}</option>
                  ))}
                </select>
              )}
            </label>
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[12rem] flex-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">New repo name</span>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="team-skills" className="field mt-1.5 w-full font-mono" />
              </label>
              <div className="inline-flex overflow-hidden rounded-lg border border-line text-xs">
                <button onClick={() => setNewPrivate(true)} className={`px-3 py-1.5 ${newPrivate ? "bg-primary text-white" : "text-body hover:bg-surface"}`}>Private</button>
                <button onClick={() => setNewPrivate(false)} className={`px-3 py-1.5 ${!newPrivate ? "bg-primary text-white" : "text-body hover:bg-surface"}`}>Public</button>
              </div>
            </div>
          )}

          {/* route (which resources) */}
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Which resources</span>
            {repoIsPublic ? (
              <p className="mt-1.5 flex items-center gap-1.5 text-sm text-body"><Globe className="h-4 w-4 text-primary" /> Public repo → <strong className="text-ink">public resources only</strong></p>
            ) : (
              <div className="mt-1.5 inline-flex overflow-hidden rounded-lg border border-line text-xs">
                {ROUTES.map((r) => (
                  <button key={r.key} onClick={() => setRoute(r.key)} className={`px-3 py-1.5 ${route === r.key ? "bg-primary text-white" : "text-body hover:bg-surface"}`}>{r.label}</button>
                ))}
              </div>
            )}
          </div>

          {/* sync direction */}
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Sync direction</span>
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {DIRECTIONS.map((d) => {
                const active = direction === d.key;
                const Icon = d.icon;
                return (
                  <button key={d.key} onClick={() => setDirection(d.key)} className={`rounded-lg border p-2 text-left text-xs ${active ? "border-primary bg-primary-50" : "border-line hover:border-primary/40"}`}>
                    <span className="flex items-center gap-1 font-semibold text-ink"><Icon className="h-3.5 w-3.5" /> {d.label}</span>
                    <span className="text-muted">{d.hint}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={() => attach.mutate()} disabled={!canSubmit || attach.isPending} className="btn btn-primary btn-sm">
              {attach.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Attach
            </button>
            <button onClick={() => setOpen(false)} className="btn btn-secondary btn-sm">Cancel</button>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-2">
        {links.isLoading ? (
          <div className="flex items-center gap-2 py-3 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        ) : !links.data?.length ? (
          <p className="py-3 text-sm text-muted">No repositories attached yet.</p>
        ) : (
          links.data.map((l) => (
            <div key={l.id} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <a href={l.repo_url ?? "#"} target="_blank" rel="noopener noreferrer" className="truncate text-sm font-semibold text-ink hover:text-primary">{l.repo_full_name}</a>
                  <span className={`tag inline-flex items-center gap-1 ${l.repo_private ? "!bg-surface-2 !text-muted" : "!bg-primary-50 !text-primary"}`}>
                    {l.repo_private ? <Lock className="h-3 w-3" /> : <Globe className="h-3 w-3" />} {l.repo_private ? "private" : "public"}
                  </span>
                  <span className="tag !bg-surface-2 inline-flex items-center gap-1 !text-body"><Layers className="h-3 w-3" /> {l.visibility}</span>
                  <span className="tag !bg-[var(--color-success)]/10 !text-[var(--color-success)]">{l.sync_direction}</span>
                </div>
              </div>
              {isAdmin && (
                <div className="flex shrink-0 gap-1">
                  <button onClick={() => sync.mutate(l.id)} disabled={sync.isPending} className="btn btn-secondary btn-sm" title="Sync now"><RefreshCw className="h-3.5 w-3.5" /></button>
                  <button onClick={() => { if (confirm("Detach this repository?")) detach.mutate(l.id); }} disabled={detach.isPending} className="btn btn-secondary btn-sm !text-[var(--color-danger)]" title="Detach"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
