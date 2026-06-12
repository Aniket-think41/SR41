/**
 * Central site configuration.
 * The marketing site is informational only — every functional action
 * redirects to the dashboard app (see lib/redirects.ts).
 */

// The dashboard is a SEPARATE app on its own origin (client/, port 3001 in
// local dev). Set NEXT_PUBLIC_DASHBOARD_URL to its public origin in prod;
// defaults to the local dev port so links work out of the box.
const DASHBOARD_ORIGIN = (
  process.env.NEXT_PUBLIC_DASHBOARD_URL ?? "http://localhost:3001"
).replace(/\/$/, "");

export const SITE = {
  name: "SkillShare",
  by: "Think41",
  url: "https://skillshare.think41.com",
  // Absolute links into the dashboard app on its own origin.
  dashboard: {
    origin: DASHBOARD_ORIGIN,
    base: `${DASHBOARD_ORIGIN}/dashboard`,
    signup: `${DASHBOARD_ORIGIN}/signup`,
    login: `${DASHBOARD_ORIGIN}/login`,
  },
  nav: [
    { label: "How it works", href: "/how-it-works" },
    { label: "Marketplace", href: "/marketplace" },
    { label: "Pricing", href: "/pricing" },
    { label: "Blog", href: "/blog" },
  ],
} as const;
