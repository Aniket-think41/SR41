"use client";

/**
 * "Attached repositories" for a scope (org / team / pod). Renders ONLY when the
 * org has a connected GitHub integration. Attach one or more repos; resources in
 * the scope whose visibility matches auto-sync to them. Admins manage; everyone
 * in scope sees the list.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Github, Loader2, Trash2, RefreshCw, Plus, Globe, Lock, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { useCurrentOrg, useIntegration } from "@/lib/hooks";
import { useToast } from "@/components/Toast";

const VIS = [
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
  const isAdmin = org?.my_role === "ADMIN";

  const [repo, setRepo] = useState("");
  const [visibility, setVisibility] = useState<"all" | "public" | "private">("all");
  const [autoSync, setAutoSync] = useState(true);

  const key = ["org", slug, "scope-links", scopeType, scopeId] as const;
  const links = useQuery({
    queryKey: key,
    queryFn: () => api.githubScopeLinks(slug, { scope_type: scopeType, scope_id: scopeId }),
    enabled: !!slug && !!scopeId && !!gh.data?.connected,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["org", slug, "scope-links"] });

  const attach = useMutation({
    mutationFn: () =>
      api.githubAttachScope(slug, { scope_type: scopeType, scope_id: scopeId, repo_full_name: repo.trim(), visibility, auto_sync: autoSync }),
    onSuccess: () => { invalidate(); setRepo(""); toast("Repository attached"); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const detach = useMutation({
    mutationFn: (id: string) => api.githubDetachScope(slug, id),
    onSuccess: () => { invalidate(); toast("Detached"); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const sync = useMutation({
    mutationFn: (id: string) => api.githubScopeSync(slug, id),
    onSuccess: (r) => { invalidate(); toast(`Pushed ${r.pushed} resource${r.pushed === 1 ? "" : "s"}`); },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  // The whole surface is hidden unless GitHub is connected for the org.
  if (!gh.data?.connected) return null;

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2">
        <Github className="h-4 w-4 text-ink" />
        <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
      </div>
      <p className="mt-1 text-sm text-body">
        Attach GitHub repos to this {scopeType === "POD" ? "pod" : scopeType === "PROJECT" ? "team" : "organization"}.
        New resources added here auto-sync to them — no per-resource repo link needed. You can attach several.
      </p>

      {isAdmin && (
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="min-w-[14rem] flex-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Repository (owner/repo)</span>
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="acme/skills" className="field mt-1.5 w-full font-mono" />
          </label>
          <label>
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Route</span>
            <select value={visibility} onChange={(e) => setVisibility(e.target.value as typeof visibility)} className="field mt-1.5">
              {VIS.map((v) => <option key={v.key} value={v.key}>{v.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5 pb-2.5 text-xs text-muted">
            <input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} /> Auto-sync
          </label>
          <button onClick={() => attach.mutate()} disabled={repo.trim().length < 3 || attach.isPending} className="btn btn-primary">
            {attach.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Attach
          </button>
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
                  <a href={l.repo_url ?? "#"} target="_blank" rel="noopener noreferrer" className="truncate text-sm font-semibold text-ink hover:text-primary">
                    {l.repo_full_name}
                  </a>
                  <span className={`tag inline-flex items-center gap-1 ${l.visibility === "public" ? "!bg-primary-50 !text-primary" : l.visibility === "private" ? "!bg-surface-2 !text-muted" : "!bg-surface-2 !text-body"}`}>
                    {l.visibility === "public" ? <Globe className="h-3 w-3" /> : l.visibility === "private" ? <Lock className="h-3 w-3" /> : <Layers className="h-3 w-3" />}
                    {l.visibility}
                  </span>
                  {l.auto_sync && <span className="tag !bg-[var(--color-success)]/10 !text-[var(--color-success)]">auto-sync</span>}
                </div>
              </div>
              {isAdmin && (
                <div className="flex shrink-0 gap-1">
                  <button onClick={() => sync.mutate(l.id)} disabled={sync.isPending} className="btn btn-secondary btn-sm" title="Push all matching resources now">
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => { if (confirm("Detach this repository?")) detach.mutate(l.id); }} disabled={detach.isPending} className="btn btn-secondary btn-sm !text-[var(--color-danger)]" title="Detach">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
