"use client";

/**
 * Org settings → Plan & usage (spec §2). Shows the org's current plan, resource
 * usage against its quota, and an Upgrade CTA. Upgrading routes to the billing
 * page (checkout is gracefully disabled until Razorpay keys are configured).
 */

import Link from "next/link";
import { BadgeCheck, ArrowUpRight, Boxes } from "lucide-react";
import { useCurrentOrg, useOrgEntitlements } from "@/lib/hooks";

function UsageBar({ used, quota }: { used: number; quota: number | null }) {
  if (quota === null)
    return <p className="mt-1 text-sm text-body"><span className="font-bold text-ink">{used}</span> resources · unlimited</p>;
  const pct = Math.min(100, Math.round((used / quota) * 100));
  const near = pct >= 80;
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between text-xs font-semibold text-muted">
        <span>{used} / {quota} resources</span>
        <span className={near ? "text-[var(--color-danger)]" : ""}>{pct}%</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-line">
        <div
          className={`h-full rounded-full transition-[width] ${near ? "bg-[var(--color-danger)]" : "bg-primary"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function PlanUsageCard() {
  const { org } = useCurrentOrg();
  const { data: ent, isLoading } = useOrgEntitlements();
  const isAdmin = org?.my_role === "ADMIN";
  const paid = ent && ent.plan !== "FREE";

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-display flex items-center gap-2 text-lg font-semibold">
          <Boxes className="h-5 w-5 text-primary" /> Plan &amp; usage
        </h2>
        <span className={`tag ${paid ? "!bg-lime !text-ink" : ""}`}>
          {paid ? <BadgeCheck className="h-3 w-3" /> : null}
          {ent?.plan_name ?? "—"} plan
        </span>
      </div>

      {isLoading || !ent ? (
        <p className="mt-3 text-sm text-muted">Loading usage…</p>
      ) : (
        <>
          <UsageBar used={ent.resource_used} quota={ent.resource_quota} />
          <p className="mt-3 text-xs text-muted">
            MCP servers: {ent.mcp_included ? "included" : "not included on this plan"}.
          </p>
        </>
      )}

      {ent && ent.plan !== "ENTERPRISE" && (
        <div className="mt-4 flex items-center gap-3">
          {isAdmin ? (
            <Link href="/dashboard/billing" className="btn btn-primary btn-sm">
              <ArrowUpRight className="h-3.5 w-3.5" /> Upgrade plan
            </Link>
          ) : (
            <p className="text-xs text-muted">Only org admins can change the plan.</p>
          )}
        </div>
      )}
    </div>
  );
}
