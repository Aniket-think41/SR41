"use client";

/**
 * Billing & plans (spec §5). Shows the signed-in user's personal plan + usage,
 * their owned orgs' plans, and the plan catalog with Upgrade CTAs. Online
 * checkout is scaffolded but disabled until Razorpay keys are set — the UI
 * degrades to a "coming soon / ask an admin" message and never crashes.
 */

import { useQuery, useMutation } from "@tanstack/react-query";
import { CreditCard, Check, Info, Loader2, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import type { Plan } from "@/lib/types";
import { useToast } from "@/components/Toast";

const RANK: Record<Plan, number> = { FREE: 0, PRO: 1, ENTERPRISE: 2 };

export default function BillingPage() {
  const { toast } = useToast();
  const { data: config } = useQuery({ queryKey: qk.billingConfig, queryFn: api.billingConfig });
  const { data: sub, isLoading } = useQuery({
    queryKey: qk.billingSubscription,
    queryFn: api.billingSubscription,
  });

  const checkout = useMutation({
    mutationFn: (plan: Plan) => api.billingCheckout({ plan, target_type: "user" }),
    onSuccess: () => toast("Redirecting to checkout…"),
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const enabled = !!config?.enabled;
  const currentPlan = (sub?.user.plan ?? "FREE") as Plan;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <p className="kicker flex items-center gap-1.5">
          <CreditCard className="h-3.5 w-3.5" /> Billing
        </p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Plans &amp; billing</h1>
        <p className="mt-1.5 text-sm text-body">Your personal plan, quotas, and upgrade options.</p>
      </div>

      {!enabled && (
        <div className="card flex items-start gap-3 border-dashed p-5">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <p className="text-sm font-bold text-ink">Online upgrades are coming soon.</p>
            <p className="mt-0.5 text-sm text-body">
              Self-serve checkout isn&rsquo;t enabled yet. In the meantime, ask a platform admin to grant your
              plan — they can set it from the admin console.
            </p>
          </div>
        </div>
      )}

      {/* Current usage */}
      <div className="card p-6">
        <h2 className="font-display text-lg font-semibold">Your plan</h2>
        {isLoading || !sub ? (
          <p className="mt-2 text-sm text-muted">Loading…</p>
        ) : (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-line p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-muted">Personal / publisher</p>
              <p className="font-display mt-1 text-2xl font-semibold">{sub.user.plan_name}</p>
              <p className="mt-1 text-sm text-body">
                {sub.user.publisher_resource_used}
                {sub.user.publisher_resource_quota === null ? " published · unlimited" : ` / ${sub.user.publisher_resource_quota} published`}
              </p>
              <p className="mt-1 text-xs text-muted">
                Orgs owned: {sub.user.orgs_owned}
                {sub.user.max_orgs === null ? " · unlimited" : ` / ${sub.user.max_orgs}`} · MCP{" "}
                {sub.user.mcp_included ? "included" : "not included"}
              </p>
            </div>
            {sub.orgs.length > 0 && (
              <div className="rounded-2xl border border-line p-4">
                <p className="text-xs font-bold uppercase tracking-wider text-muted">Organizations you own</p>
                <ul className="mt-2 space-y-1.5">
                  {sub.orgs.map((o) => (
                    <li key={o.slug} className="flex items-center justify-between text-sm">
                      <span className="font-semibold text-ink">{o.name}</span>
                      <span className="tag">{o.plan_name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Plan catalog */}
      <div className="grid gap-4 md:grid-cols-3">
        {(config?.plans ?? []).map((p) => {
          const isCurrent = p.key === currentPlan;
          const isUpgrade = RANK[p.key] > RANK[currentPlan];
          return (
            <div key={p.key} className={`card p-5 ${isCurrent ? "ring-2 ring-primary" : ""}`}>
              <div className="flex items-center justify-between">
                <h3 className="font-display text-lg font-semibold">{p.name}</h3>
                {isCurrent && <span className="tag !bg-primary !text-white">Current</span>}
              </div>
              <p className="font-display mt-2 text-3xl font-semibold">
                ${p.price_usd}
                <span className="text-sm font-normal text-muted">/mo</span>
              </p>
              <p className="mt-2 text-sm text-body">{p.tagline}</p>
              <ul className="mt-3 space-y-1.5 text-sm text-body">
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary" />
                  {p.max_orgs === null ? "Unlimited orgs" : p.max_orgs === 0 ? "No orgs" : `${p.max_orgs} orgs`}
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary" />
                  {p.resource_quota === null ? "Unlimited resources" : `${p.resource_quota} resources`}
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary" /> MCP {p.mcp_included ? "included" : "not included"}
                </li>
              </ul>
              {isUpgrade && (
                <button
                  onClick={() => checkout.mutate(p.key)}
                  disabled={!enabled || checkout.isPending}
                  title={enabled ? undefined : "Online upgrades are coming soon — ask an admin"}
                  className="btn btn-primary btn-sm mt-4 w-full"
                >
                  {checkout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  {enabled ? `Upgrade to ${p.name}` : "Coming soon"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
