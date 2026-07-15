"use client";

/**
 * Integration config / credentials page. Reached from the Integrations grid.
 *
 * Not connected → the connect flow: choose a method (Classic PAT today), see its
 * recommended permissions, paste the token. Connected → the config surface:
 * account metadata, granted capabilities (each feature enables/disables on the
 * connection's detected scopes), a Sync button that re-checks the token and
 * unlocks newly-granted permissions, sync mode, and the GitHub repo browser.
 * Admin-only actions; a non-admin sees a read-only notice.
 */

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Github, Plug, Check, Loader2, Search, Star, Lock, ExternalLink,
  Trash2, KeyRound, PackagePlus, RefreshCw, ShieldCheck, CircleSlash,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useIntegration } from "@/lib/hooks";
import type { GithubRepo, IntegrationAuthMethod, IntegrationProvider } from "@/lib/types";
import { useToast } from "@/components/Toast";
import { FeatureGate } from "@/components/FeatureGate";

const SYNC_MODES = [
  { key: "manual", label: "Manual", hint: "Nothing syncs automatically — you trigger it.", needs: null as string | null },
  { key: "read_only", label: "Read only", hint: "GitHub → SkillShare. Repos flow in.", needs: null },
  { key: "write_only", label: "Write only", hint: "SkillShare → GitHub. Push changes out.", needs: "write" },
  { key: "bidirectional", label: "Bidirectional", hint: "Keep both sides in sync.", needs: "write" },
] as const;

function ProviderIcon({ icon, className = "" }: { icon: string; className?: string }) {
  const Icon = icon === "github" ? Github : Plug;
  return <Icon className={className || "h-6 w-6"} />;
}

const shortDate = (s: string | null) =>
  s ? new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";
const longDate = (s: string | null) => (s ? new Date(s).toLocaleString() : "—");

/** One aligned metadata cell: the value is trimmed to a single line; the full
 *  text shows in a tooltip pinned above on hover (long dates/scopes never break
 *  the grid). */
function MetaItem({ label, value, full, mono }: { label: string; value: string; full?: string; mono?: boolean }) {
  const tip = full ?? value;
  return (
    <div className="group/meta relative min-w-0">
      <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono" : ""}`} title={tip}>{value}</dd>
      <span className="pointer-events-none absolute bottom-full left-0 z-20 mb-1 hidden max-w-[16rem] whitespace-normal break-words rounded-lg bg-ink px-2 py-1 text-[0.7rem] font-normal normal-case text-white shadow-lg group-hover/meta:block">
        {tip}
      </span>
    </div>
  );
}

/* ------------------------------ connect flow ------------------------------ */

function ConnectFlow({ provider, slug, isAdmin }: { provider: IntegrationProvider; slug: string; isAdmin: boolean }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const methods = provider.auth_methods ?? [];
  const available = methods.filter((m) => m.available);
  const [methodKey, setMethodKey] = useState(available[0]?.key ?? "classic_pat");
  const method: IntegrationAuthMethod | undefined = methods.find((m) => m.key === methodKey) ?? available[0];
  const [token, setToken] = useState("");
  const [account, setAccount] = useState("");

  const connect = useMutation({
    mutationFn: () =>
      api.connectIntegration(slug, provider.key, {
        token: token.trim(),
        account: account.trim() || undefined,
        auth_method: methodKey,
      }),
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
    <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
      {/* method chooser */}
      <div className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Choose how to connect</h2>
        {methods.map((m) => {
          const selected = m.key === methodKey;
          return (
            <button
              key={m.key}
              onClick={() => m.available && setMethodKey(m.key)}
              disabled={!m.available}
              className={`w-full rounded-2xl border p-4 text-left transition ${
                selected ? "border-primary bg-primary-50" : "border-line hover:border-primary/40"
              } ${!m.available ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-ink">{m.name}</span>
                {!m.available ? (
                  <span className="tag">Coming soon</span>
                ) : selected ? (
                  <Check className="h-4 w-4 text-primary" />
                ) : null}
              </div>
              <p className="mt-1 text-xs text-muted">{m.hint}</p>
            </button>
          );
        })}
      </div>

      {/* selected method form */}
      <div className="card p-8">
        <div className="flex items-center gap-2 text-ink">
          <KeyRound className="h-5 w-5 text-primary" />
          <h2 className="font-display text-lg font-semibold">Connect with {method?.name}</h2>
        </div>

        {!!method?.recommended?.length && (
          <div className="mt-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Recommended permissions</p>
            <ul className="mt-3 space-y-2">
              {method.recommended.map((r) => (
                <li key={r.scope} className="flex items-start gap-2 text-sm">
                  <code className="mt-0.5 rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-ink">{r.scope}</code>
                  <span className="text-body">
                    {r.why}
                    {r.required && <span className="ml-1 text-[var(--color-danger)]">· required</span>}
                  </span>
                </li>
              ))}
            </ul>
            {method.docs_url && (
              <a href={method.docs_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline">
                Create a token with these scopes <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        )}

        <div className="mt-6 space-y-4">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Token</span>
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
            <input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="acme" className="field mt-1.5 w-full" />
          </label>
        </div>

        <button
          onClick={() => connect.mutate()}
          disabled={token.trim().length < 10 || connect.isPending}
          className="btn btn-primary mt-6"
        >
          {connect.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Connect
        </button>
        <p className="mt-3 text-xs text-muted">The token is validated against GitHub, then encrypted at rest — it&apos;s never shown again.</p>
      </div>
    </div>
  );
}

/* ------------------------------ capabilities ------------------------------ */

function Capabilities({ provider }: { provider: IntegrationProvider }) {
  const caps = provider.connection?.capabilities ?? [];
  return (
    <div className="card p-6">
      <h3 className="font-display text-lg font-semibold text-ink">What this connection can do</h3>
      <p className="mt-1 text-sm text-body">
        Capabilities are detected from your token&apos;s granted scopes. Missing one? Add the scope on GitHub and press Sync.
      </p>
      <ul className="mt-4 space-y-2">
        {caps.map((cap) => (
          <li key={cap.key} className="flex items-start gap-3 rounded-xl border border-line p-3">
            <span className={cap.enabled ? "text-[var(--color-success)]" : "text-muted"}>
              {cap.enabled ? <Check className="h-4 w-4" /> : <CircleSlash className="h-4 w-4" />}
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-ink">{cap.name}</span>
                {!cap.enabled && cap.recommend && (
                  <span className="text-xs text-muted">
                    needs <code className="rounded bg-surface-2 px-1 font-mono text-ink">{cap.recommend}</code>
                  </span>
                )}
              </div>
              <p className="text-xs text-body">{cap.description}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------ repo browser ------------------------------ */

function RepoBrowser({ slug, orgId, canPrivate }: { slug: string; orgId: string | undefined; canPrivate: boolean }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");

  const search = useQuery({
    queryKey: ["org", slug, "integration", "github", "search", submitted],
    queryFn: () => api.githubIntegrationSearch(slug, submitted),
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
      <p className="mt-1 text-sm text-body">
        Search your connected repos and import detected resources into the org.
        {!canPrivate && <span className="text-muted"> Private repos need the <code className="font-mono">repo</code> scope.</span>}
      </p>

      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); setSubmitted(q.trim()); }}>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search repositories…" className="field w-full pl-9" />
        </div>
        <button type="submit" className="btn btn-secondary">Search</button>
      </form>

      <div className="mt-4 space-y-2">
        {search.isLoading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading repositories…</div>
        ) : search.isError ? (
          <p className="py-6 text-sm text-muted">{errorMessage(search.error)}</p>
        ) : !search.data?.length ? (
          <p className="py-6 text-sm text-muted">No repositories found.</p>
        ) : (
          search.data.map((repo) => (
            <div key={repo.full_name} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <a href={repo.html_url ?? "#"} target="_blank" rel="noopener noreferrer" className="truncate text-sm font-semibold text-ink hover:text-primary">
                    {repo.full_name}
                  </a>
                  {repo.private && <Lock className="h-3 w-3 shrink-0 text-muted" />}
                  {repo.language && <span className="shrink-0 text-xs text-muted">{repo.language}</span>}
                  <span className="flex shrink-0 items-center gap-0.5 text-xs text-muted"><Star className="h-3 w-3" /> {repo.stars}</span>
                </div>
                {repo.description && <p className="mt-0.5 truncate text-xs text-body">{repo.description}</p>}
              </div>
              <button onClick={() => importRepo.mutate(repo)} disabled={importRepo.isPending} className="btn btn-secondary btn-sm shrink-0" title="Detect and import resources from this repo">
                {importRepo.isPending && importRepo.variables?.full_name === repo.full_name ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PackagePlus className="h-3.5 w-3.5" />}
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
  const capOn = useMemo(() => new Map(conn.capabilities.map((c) => [c.key, c.enabled])), [conn.capabilities]);
  const methodName = provider.auth_methods.find((m) => m.key === conn.auth_method)?.name ?? conn.auth_method;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: qk.integration(slug, provider.key) });
    qc.invalidateQueries({ queryKey: qk.integrationProviders(slug) });
  };

  const sync = useMutation({
    mutationFn: () => api.syncIntegration(slug, provider.key),
    onSuccess: () => { invalidate(); toast("Synced — capabilities refreshed"); },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const setMode = useMutation({
    mutationFn: (mode: string) => api.updateIntegrationConfig(slug, provider.key, { sync_mode: mode }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.integration(slug, provider.key) }),
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const disconnect = useMutation({
    mutationFn: () => api.disconnectIntegration(slug, provider.key),
    onSuccess: () => { invalidate(); toast(`${provider.name} disconnected`); },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="space-y-6">
      {/* metadata + actions */}
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            {conn.account_avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={conn.account_avatar} alt="" className="h-10 w-10 rounded-xl" />
            ) : (
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-2"><Github className="h-5 w-5" /></span>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="tag !bg-[var(--color-success)]/10 !text-[var(--color-success)] inline-flex items-center gap-1"><Check className="h-3 w-3" /> Connected</span>
                {conn.account_url ? (
                  <a
                    href={conn.account_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={conn.account_label ?? undefined}
                    className="inline-flex max-w-[12rem] items-center gap-1 text-sm font-semibold text-ink hover:text-primary"
                  >
                    <span className="truncate">{conn.account_label}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                ) : (
                  <span className="max-w-[12rem] truncate text-sm font-semibold text-ink" title={conn.account_label ?? undefined}>
                    {conn.account_label}
                  </span>
                )}
                {conn.account_type && <span className="shrink-0 text-xs text-muted">· {conn.account_type}</span>}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3 lg:grid-cols-5">
                <MetaItem label="Method" value={methodName} />
                <MetaItem label="Token" value={`••••${conn.token_hint ?? ""}`} mono />
                <MetaItem
                  label="Scopes"
                  value={conn.scopes.length ? conn.scopes.join(", ") : "—"}
                  full={conn.scopes.length ? conn.scopes.join(", ") : undefined}
                />
                <MetaItem label="Added" value={shortDate(conn.created_at)} full={longDate(conn.created_at)} />
                <MetaItem label="Last synced" value={shortDate(conn.last_synced_at)} full={longDate(conn.last_synced_at)} />
              </dl>
            </div>
          </div>
          {isAdmin && (
            <div className="flex gap-2">
              <button onClick={() => sync.mutate()} disabled={sync.isPending} className="btn btn-secondary btn-sm" title="Re-check the token and refresh capabilities">
                {sync.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Sync
              </button>
              <button
                onClick={() => { if (confirm(`Disconnect ${provider.name}? Stored credentials will be deleted.`)) disconnect.mutate(); }}
                disabled={disconnect.isPending}
                className="btn btn-secondary btn-sm !text-[var(--color-danger)]"
              >
                {disconnect.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />} Disconnect
              </button>
            </div>
          )}
        </div>
        {conn.status === "error" && conn.last_error && (
          <p className="mt-3 rounded-lg bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">{conn.last_error}</p>
        )}
      </div>

      <Capabilities provider={provider} />

      {/* sync mode — write modes gate on the `write` capability */}
      <div className="card p-6">
        <h3 className="font-display text-lg font-semibold text-ink">Sync mode</h3>
        <p className="mt-1 text-sm text-body">Which direction changes flow between GitHub and SkillShare.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {SYNC_MODES.map((m) => {
            const active = syncMode === m.key;
            const locked = !!m.needs && !capOn.get(m.needs);
            return (
              <button
                key={m.key}
                onClick={() => isAdmin && !locked && setMode.mutate(m.key)}
                disabled={!isAdmin || locked || setMode.isPending}
                className={`rounded-xl border p-4 text-left transition ${
                  active ? "border-primary bg-primary-50" : "border-line hover:border-primary/40"
                } ${locked ? "cursor-not-allowed opacity-55" : ""}`}
                title={locked ? "Requires the write capability (repo scope) — grant it and Sync" : undefined}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-ink">{m.label}</span>
                  {active ? <Check className="h-4 w-4 text-primary" /> : locked ? <Lock className="h-4 w-4 text-muted" /> : null}
                </div>
                <p className="mt-1 text-xs text-muted">{m.hint}</p>
              </button>
            );
          })}
        </div>
      </div>

      {provider.key === "github" && <RepoBrowser slug={slug} orgId={orgId} canPrivate={!!capOn.get("read_private")} />}
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
              <div className="flex items-center gap-2">
                <h1 className="font-display text-2xl font-semibold text-ink">{provider.name}</h1>
                <ShieldCheck className="h-4 w-4 text-muted" aria-label="Premium integration" />
              </div>
              {provider.category && <p className="text-sm text-muted">{provider.category}</p>}
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-body">{provider.description}</p>
            </div>
          </header>

          {provider.connected ? (
            <ConnectedView provider={provider} slug={org!.slug} orgId={org?.id} isAdmin={!!isAdmin} />
          ) : (
            <ConnectFlow provider={provider} slug={org!.slug} isAdmin={!!isAdmin} />
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
