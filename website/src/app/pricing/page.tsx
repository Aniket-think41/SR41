import type { Metadata } from "next";
import Link from "next/link";
import { getStarted } from "@/lib/redirects";

export const metadata: Metadata = {
  title: "Pricing — free in v1",
  description:
    "SkillShare is free in v1. Organize, publish, and browse with no card required. Team and enterprise plans are coming soon.",
  alternates: { canonical: "/pricing" },
};

const tiers = [
  {
    name: "Free",
    badge: "Available now",
    price: "$0",
    note: "forever, in v1",
    featured: true,
    cta: "Get started free",
    features: [
      "Create one organization",
      "Unlimited projects & pods",
      "Org-level inheritance",
      "Publish to the public marketplace",
      "Think41-verified publisher profile",
      "Community support",
    ],
  },
  {
    name: "Team",
    badge: "Coming soon",
    price: "—",
    note: "teased for v2",
    featured: false,
    cta: "Notify me",
    features: [
      "Everything in Free",
      "Multiple organizations",
      "Private marketplaces",
      "Role-based access control",
      "Usage analytics",
      "Priority support",
    ],
  },
  {
    name: "Enterprise",
    badge: "Coming soon",
    price: "—",
    note: "teased for v2",
    featured: false,
    cta: "Talk to us",
    features: [
      "Everything in Team",
      "SSO & SCIM",
      "Self-hosted registry",
      "Audit logs & compliance",
      "Dedicated support",
      "Custom SLAs",
    ],
  },
];

export default function Pricing() {
  return (
    <>
      <section className="relative overflow-hidden bg-surface">
        <div className="blob left-1/2 top-0 h-80 w-80 -translate-x-1/2" style={{ background: "var(--color-primary-50)" }} />
        <div className="shell relative py-16 text-center md:py-24">
          <div className="inline-flex items-center gap-2 rounded-full bg-lime px-4 py-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-ink">Free tier · v1</span>
          </div>
          <h1 className="font-display mx-auto mt-6 max-w-3xl text-5xl font-semibold sm:text-6xl md:text-[4rem]">
            Pricing that starts at free.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-body">
            v1 is free for everyone. Paid plans are on the roadmap — here&apos;s
            where they&apos;re headed.
          </p>
        </div>
      </section>

      <section className="shell py-16 md:py-20">
        <div className="grid items-start gap-6 md:grid-cols-3">
          {tiers.map((t) => (
            <div
              key={t.name}
              className={`flex flex-col rounded-[24px] p-8 ${
                t.featured
                  ? "border-2 border-primary bg-white shadow-[0_30px_60px_-30px_rgba(115,90,229,0.5)] md:-mt-4 md:pb-12"
                  : "card"
              }`}
            >
              <div className="flex items-center justify-between">
                <h2 className="font-display text-3xl font-semibold">{t.name}</h2>
                <span className={`tag ${t.featured ? "bg-primary text-white" : ""}`}>{t.badge}</span>
              </div>
              <div className="mt-6 flex items-end gap-2">
                <span className="font-display text-5xl font-bold">{t.price}</span>
                <span className="mb-1 text-sm text-muted">{t.note}</span>
              </div>

              <ul className="mt-8 flex-1 space-y-3 border-t border-line pt-6">
                {t.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-[0.95rem]">
                    <span aria-hidden className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-50 text-xs text-primary">✓</span>
                    <span className={t.featured ? "text-ink" : "text-body"}>{f}</span>
                  </li>
                ))}
              </ul>

              <Link href={getStarted()} className={`btn mt-8 w-full ${t.featured ? "btn-primary" : "btn-secondary"}`}>
                {t.cta} →
              </Link>
            </div>
          ))}
        </div>

        <p className="mt-10 text-center text-sm text-muted">
          Team and Enterprise pricing are placeholders for v1 and subject to change.
        </p>
      </section>
    </>
  );
}
