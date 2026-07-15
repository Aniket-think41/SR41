"use client";

/**
 * Integration config / credentials page. Reached by clicking a card on the
 * Integrations grid. Before a connection exists it shows the connect form (add
 * credentials); once connected it shows the config surface — account summary,
 * sync mode, GitHub repo browser (discover → import), and disconnect.
 */

import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Github, Plug, Check, Loader2, Search, Star, Lock, ExternalLink,
  Trash2, KeyRound, PackagePlus,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useIntegration } from "@/lib/hooks";
import type { GithubRepo, IntegrationProvider } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { FeatureGate } from "@/components/FeatureGate";

const SYNC_MODES = [
  { key: "manual", label: "Manual", hint: "Nothing syncs automatically — you trigger it." },
  { key: "read_only", label: "Read only", hint: "GitHub → SkillShare. Repos flow in." },
  { key: "write_only", label: "Write only", hint: "SkillShare → GitHub. Push changes out." },
  { key: "bidirectional", label: "Bidirectional", hint: "Keep both sides in sync." },
] as const;

function ProviderIcon({ icon, className = "" }: { icon: string; className?: string }) {
  const Icon = icon === "github" ? Github : Plug;
  return <Icon className={className || "h-6 w-6"} />;
}

/* ------------------------------ connect form ------------------------------ */

function ConnectForm({ provider, slug, isAdmin }: { provider: IntegrationProvider; slug: string; isAdmin: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [account, setAccount] = useState("");

  const connect = useMutation({
    mutationFn: () => api.connectIntegration(slug, provider.key, { token: token.trim(), account: account.trim() || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.integration(slug, provider.key) });
      qc.invalidateQueries({ queryKey: qk.integrationProviders(slug) });
      setToken("");
      toast(`${provider.name} connected`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (!isAdmin) {
    return (
      <div className="card p-8 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-2 text-muted">
          <Lock className="h-5 w-5" />
        </span>
        <p className="mt-4 text-sm text-body">
          {provider.name} isn&apos;t connected yet. Ask an organization admin to connect it.
        </p>
      </div>
    );
  }

  return (
    <div className="card max-w-xl p-8">
      <div className="flex items-center gap-2 text-ink">
        <KeyRound className="h-5 w-5 text-primary" />
        <h2 className="font-display text-lg font-semibold">Connect {provider.name}</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-body">
        Paste a {provider.auth_type === "pat" ? "Personal Access Token" : "credential"}. It&apos;s validated,
        then encrypted at rest — SkillShare never shows it again.
      </p>

      <div className="mt-6 space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            {provider.auth_type === "pat" ? "Personal Access Token" : "Token"}
          </span>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ghp_…"
            autoComplete="off"
            className="field mt-1.5 w-full font-mono"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">
            GitHub org / user <span className="font-normal normal-case">(optional — scopes discovery)</span>
          </span>
          <input
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            placeholder="acme"
            className="field mt-1.5 w-full"
          />
        </label>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={() => connect.mutate()}
          disabled={token.trim().length < 10 || connect.isPending}
          className="btn btn-primary"
        >
          {connect.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Connect
        </button>
        {provider.docs_url && (
          <a href={provider.docs_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm">
            How to create a token <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </div>
  );
}

/* ------------------------------ repo browser ------------------------------ */

function RepoBrowser({ slug, orgId }: { slug: string; orgId: string | undefined }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");

  const search = useQuery({
    queryKey: ["org", slug, "integration", "github", "search", submitted],
    queryFn: () => api.githubIntegrationSearch(slug, submitted),
    enabled: submitted !== "" || true, // initial empty query lists recent repos
  });

  const importRepo = useMutation({
    mutationFn: (repo: GithubRepo) =>
      api.githubImport({ url: repo.html_url ?? repo.full_name, scope_type: "ORG", scope_id: orgId ?? null }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["org", slug, "resources"] });
      const n = res.created?.length ?? 0;
      toast(n ? `Imported ${n} resource${n === 1 ? "" : "s"}` : "Nothing new to import from that repo");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="card p-6">
      <h3 className="font-display text-lg font-semibold text-ink">Browse repositories</h3>
      <p className="mt-1 text-sm text-body">Search your connected repos and import detected resources into the org.</p>

      <form
        className="mt-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(q.trim());
        }}
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search repositories…"
            className="field w-full pl-9"
          />
        </div>
        <button type="submit" className="btn btn-secondary">Search</button>
      </form>

      <div className="mt-4 space-y-2">
        {search.isLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading repositories…
          </div>
        ) : !search.data?.length ? (
          <p className="py-6 text-sm text-muted">No repositories found.</p>
        ) : (
          search.data.map((repo) => (
            <div key={repo.full_name} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <a
                    href={repo.html_url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="truncate text-sm font-semibold text-ink hover:text-primary"
                  >
                    {repo.full_name}
                  </a>
                  {repo.private && <Lock className="h-3 w-3 shrink-0 text-muted" />}
                  {repo.language && <span className="shrink-0 text-xs text-muted">{repo.language}</span>}
                  <span className="flex shrink-0 items-center gap-0.5 text-xs text-muted">
                    <Star className="h-3 w-3" /> {repo.stars}
                  </span>
                </div>
                {repo.description && <p className="mt-0.5 truncate text-xs text-body">{repo.description}</p>}
              </div>
              <button
                onClick={() => importRepo.mutate(repo)}
                disabled={importRepo.isPending}
                className="btn btn-secondary btn-sm shrink-0"
                title="Detect and import resources from this repo"
              >
                {importRepo.isPending && importRepo.variables?.full_name === repo.full_name ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <PackagePlus className="h-3.5 w-3.5" />
                )}
                Import
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* ------------------------------ connected view ------------------------------ */

function ConnectedView({ provider, slug, orgId, isAdmin }: { provider: IntegrationProvider; slug: string; orgId: string | undefined; isAdmin: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const conn = provider.connection!;
  const syncMode = (conn.config?.sync_mode as string) ?? "manual";

  const setMode = useMutation({
    mutationFn: (mode: string) => api.updateIntegrationConfig(slug, provider.key, { sync_mode: mode }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.integration(slug, provider.key) }),
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const disconnect = useMutation({
    mutationFn: () => api.disconnectIntegration(slug, provider.key),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.integration(slug, provider.key) });
      qc.invalidateQueries({ queryKey: qk.integrationProviders(slug) });
      toast(`${provider.name} disconnected`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="space-y-6">
      {/* connection summary */}
      <div className="card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="tag !bg-[var(--color-success)]/10 !text-[var(--color-success)] inline-flex items-center gap-1">
                <Check className="h-3 w-3" /> Connected
              </span>
              {conn.account_label && <span className="text-sm font-semibold text-ink">{conn.account_label}</span>}
            </div>
            <p className="mt-2 text-xs text-muted">
              Token ending <span className="font-mono text-ink">••••{conn.token_hint}</span>
              {conn.updated_at && <> · updated {new Date(conn.updated_at).toLocaleDateString()}</>}
            </p>
          </div>
          {isAdmin && (
            <button
              onClick={() => {
                if (confirm(`Disconnect ${provider.name}? Stored credentials will be deleted.`)) disconnect.mutate();
              }}
              disabled={disconnect.isPending}
              className="btn btn-secondary btn-sm !text-[var(--color-danger)]"
            >
              {disconnect.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* sync mode */}
      <div className="card p-6">
        <h3 className="font-display text-lg font-semibold text-ink">Sync mode</h3>
        <p className="mt-1 text-sm text-body">Choose which direction changes flow between GitHub and SkillShare.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {SYNC_MODES.map((m) => {
            const active = syncMode === m.key;
            return (
              <button
                key={m.key}
                onClick={() => isAdmin && setMode.mutate(m.key)}
                disabled={!isAdmin || setMode.isPending}
                className={`rounded-xl border p-4 text-left transition ${
                  active ? "border-primary bg-primary-50" : "border-line hover:border-primary/40"
                } ${!isAdmin ? "cursor-default" : ""}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ink">{m.label}</span>
                  {active && <Check className="h-4 w-4 text-primary" />}
                </div>
                <p className="mt-1 text-xs text-muted">{m.hint}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* repo browser (github) */}
      {provider.key === "github" && <RepoBrowser slug={slug} orgId={orgId} />}
    </div>
  );
}

/* ------------------------------ page ------------------------------ */

function Config({ providerKey }: { providerKey: string }) {
  const { org } = useCurrentOrg();
  const { data: provider, isLoading, isError } = useIntegration(providerKey);
  const isAdmin = org?.my_role === "ADMIN";

  return (
    <div className="space-y-6">
      <Link href="/dashboard/org/integrations" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Integrations
      </Link>

      {isLoading ? (
        <div className="card h-40 animate-pulse bg-surface-2/40" />
      ) : isError || !provider ? (
        <div className="card p-8 text-center text-sm text-body">This integration isn&apos;t available for your organization.</div>
      ) : (
        <>
          <header className="flex items-start gap-4">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2 text-ink">
              <ProviderIcon icon={provider.icon} className="h-7 w-7" />
            </span>
            <div>
              <h1 className="font-display text-2xl font-semibold text-ink">{provider.name}</h1>
              {provider.category && <p className="text-sm text-muted">{provider.category}</p>}
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-body">{provider.description}</p>
            </div>
          </header>

          {provider.connected ? (
            <ConnectedView provider={provider} slug={org!.slug} orgId={org?.id} isAdmin={!!isAdmin} />
          ) : (
            <ConnectForm provider={provider} slug={org!.slug} isAdmin={!!isAdmin} />
          )}
        </>
      )}
    </div>
  );
}

export default function IntegrationConfigPage({ params }: { params: Promise<{ provider: string }> }) {
  const { provider } = use(params);
  return (
    <FeatureGate feature="integrations" title="Integrations">
      <Config providerKey={provider} />
    </FeatureGate>
  );
}
