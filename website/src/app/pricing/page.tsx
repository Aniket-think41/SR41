import type { Metadata } from "next";
import Link from "next/link";
import { getPlans, type Plan } from "@/lib/data";
import { getStarted } from "@/lib/redirects";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "SkillShare pricing — start free as an individual, scale to Pro for teams, or go Enterprise for unlimited orgs and resources.",
  alternates: { canonical: "/pricing" },
};

export const revalidate = 60;

// Per-plan marketing copy layered on top of the backend's limits. The numbers
// (orgs, resources, MCP) always come from GET /api/public/plans; this only
// decorates them.
const PLAN_META: Record<
  string,
  { badge: string; note: string; featured: boolean; cta: string; extras: string[] }
> = {
  FREE: {
    badge: "Start here",
    note: "forever",
    featured: false,
    cta: "Get started free",
    extras: [
      "Publish to the public marketplace",
      "Think41-verified publisher profile",
      "Community support",
    ],
  },
  PRO: {
    badge: "For teams",
    note: "per month",
    featured: true,
    cta: "Get started free",
    extras: [
      "Org-level inheritance across projects & pods",
      "Role-based access control",
      "Priority support",
    ],
  },
  ENTERPRISE: {
    badge: "At scale",
    note: "per month",
    featured: false,
    cta: "Talk to us",
    extras: [
      "SSO & SCIM",
      "Audit logs & compliance",
      "Dedicated support & custom SLAs",
    ],
  },
};

// Turn the backend's numeric limits into human feature lines.
function limitFeatures(p: Plan): string[] {
  const orgs =
    p.max_orgs === null
      ? "Unlimited organizations"
      : p.max_orgs === 0
        ? "Publish as an individual (no orgs)"
        : `Up to ${p.max_orgs} organization${p.max_orgs === 1 ? "" : "s"}`;

  const resources =
    p.resource_quota === null
      ? "Unlimited resources"
      : `Up to ${p.resource_quota} resources`;

  const mcp = p.mcp_included ? "MCP servers included" : "Skills & notes";

  return [orgs, resources, mcp];
}

const priceLabel = (usd: number) => (usd === 0 ? "$0" : `$${usd}`);

export default async function Pricing() {
  const plans = await getPlans();

  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob left-1/2 top-0 h-80 w-80 -translate-x-1/2" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 text-center md:py-24">
          <div className="inline-flex items-center gap-2 rounded-full bg-lime px-4 py-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-ink">Simple, transparent pricing</span>
          </div>
          <h1 className="font-display mx-auto mt-6 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Pricing that starts at free.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-body">
            Publish as an individual for free, or scale to a plan with more
            organizations, resources, and MCP included.
          </p>
        </div>
      </section>

      <section className="shell py-16 md:py-20">
        <div className="grid items-start gap-6 md:grid-cols-3">
          {plans.map((p) => {
            const meta = PLAN_META[p.key] ?? {
              badge: "",
              note: "per month",
              featured: false,
              cta: "Get started free",
              extras: [],
            };
            const features = [...limitFeatures(p), ...meta.extras];
            return (
              <div
                key={p.key}
                className={`flex flex-col rounded-[24px] p-8 ${
                  meta.featured
                    ? "border-2 border-primary bg-white shadow-[0_30px_60px_-30px_rgba(115,90,229,0.5)] md:-mt-4 md:pb-12"
                    : "card"
                }`}
              >
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-3xl font-semibold">{p.name}</h2>
                  {meta.badge && (
                    <span className={`tag ${meta.featured ? "bg-primary text-white" : ""}`}>{meta.badge}</span>
                  )}
                </div>

                {p.tagline && <p className="mt-3 text-sm text-muted">{p.tagline}</p>}

                <div className="mt-6 flex items-end gap-2">
                  <span className="font-display text-5xl font-bold">{priceLabel(p.price_usd)}</span>
                  <span className="mb-1 text-sm text-muted">{meta.note}</span>
                </div>

                <ul className="mt-8 flex-1 space-y-3 border-t border-line pt-6">
                  {features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-[0.95rem]">
                      <span aria-hidden className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-50 text-xs text-primary">✓</span>
                      <span className={meta.featured ? "text-ink" : "text-body"}>{f}</span>
                    </li>
                  ))}
                </ul>

                <Link href={getStarted()} className={`btn mt-8 w-full ${meta.featured ? "btn-primary" : "btn-secondary"}`}>
                  {meta.cta} →
                </Link>
              </div>
            );
          })}
        </div>

        <p className="mt-10 text-center text-sm text-muted">
          Plan limits shown reflect the current SkillShare entitlements and may change.
        </p>
      </section>
    </>
  );
}
