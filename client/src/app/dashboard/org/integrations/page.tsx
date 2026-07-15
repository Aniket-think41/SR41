"use client";

/**
 * Org Integrations — the premium card grid. Cards are white with a hover lift
 * (.card .card-hover); clicking one opens its config/credentials page. Gated by
 * the `integrations` feature (PRO+); which cards appear is decided server-side
 * (tier + per-provider feature flag).
 */

import { useRouter } from "next/navigation";
import { ArrowRight, Github, Plug, Check } from "lucide-react";
import type { IntegrationProvider } from "@/lib/types";
import { useIntegrationProviders } from "@/lib/hooks";
import { FeatureGate } from "@/components/FeatureGate";

function ProviderIcon({ icon }: { icon: string }) {
  const Icon = icon === "github" ? Github : Plug;
  return (
    <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-2 text-ink">
      <Icon className="h-6 w-6" />
    </span>
  );
}

function IntegrationCard({ p, onOpen }: { p: IntegrationProvider; onOpen: () => void }) {
  const comingSoon = p.status === "coming_soon";
  return (
    <button
      type="button"
      onClick={comingSoon ? undefined : onOpen}
      disabled={comingSoon}
      className={`card card-hover group flex flex-col items-start gap-4 p-6 text-left ${
        comingSoon ? "cursor-not-allowed opacity-60" : ""
      }`}
    >
      <div className="flex w-full items-start justify-between">
        <ProviderIcon icon={p.icon} />
        {p.connected ? (
          <span className="tag !bg-[var(--color-success)]/10 !text-[var(--color-success)] inline-flex items-center gap-1">
            <Check className="h-3 w-3" /> Connected
          </span>
        ) : comingSoon ? (
          <span className="tag">Coming soon</span>
        ) : (
          <ArrowRight className="h-5 w-5 text-muted transition group-hover:translate-x-0.5 group-hover:text-primary" />
        )}
      </div>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-display text-xl font-semibold text-ink">{p.name}</h3>
          {p.category && <span className="text-xs text-muted">· {p.category}</span>}
        </div>
        <p className="mt-2 text-sm leading-relaxed text-body">{p.tagline}</p>
      </div>
    </button>
  );
}

function IntegrationsGrid() {
  const router = useRouter();
  const { data: providers, isLoading } = useIntegrationProviders();

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-3xl font-semibold text-ink">Integrations</h1>
        <p className="mt-2 max-w-2xl text-body">
          Connect external tools to your organization. Discover, sync, and manage
          your skills, MCP servers, and notes straight from the source.
        </p>
      </header>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card h-40 animate-pulse bg-surface-2/40" />
          ))}
        </div>
      ) : !providers?.length ? (
        <div className="card flex flex-col items-center gap-3 p-12 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2 text-primary">
            <Plug className="h-6 w-6" />
          </span>
          <h2 className="font-display text-xl font-semibold text-ink">No integrations available yet</h2>
          <p className="max-w-sm text-sm text-body">
            New integrations show up here as they become available for your plan.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {providers.map((p) => (
            <IntegrationCard
              key={p.key}
              p={p}
              onOpen={() => router.push(`/dashboard/org/integrations/${p.key}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <FeatureGate feature="integrations" title="Integrations">
      <IntegrationsGrid />
    </FeatureGate>
  );
}
