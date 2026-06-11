/**
 * Central site configuration.
 * The marketing site is informational only — every functional action
 * redirects to the dashboard app (see lib/redirects.ts).
 */
export const SITE = {
  name: "SkillShare",
  by: "Think41",
  url: "https://skillshare.think41.com",
  // The dashboard lives on its own surface; the website only links into it.
  dashboard: {
    base: "/dashboard",
    signup: "/signup",
    login: "/login",
  },
  nav: [
    { label: "How it works", href: "/how-it-works" },
    { label: "Marketplace", href: "/marketplace" },
    { label: "Pricing", href: "/pricing" },
    { label: "Blog", href: "/blog" },
  ],
} as const;
