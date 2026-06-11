import { SITE } from "./site";

/**
 * Dashboard redirect logic — implements MARKETING WEBSITE SPEC §5.
 *
 * The website never performs functional actions itself. All CTAs send the
 * user into the dashboard app via these helpers so the routing rules live
 * in exactly one place. Because the marketing site is statically rendered
 * and has no session, links are generated for the logged-out path; the
 * dashboard resolves the rest (onboarding modal, last-org, etc.) after auth.
 */

const { signup, login } = SITE.dashboard;

/** Primary action — "Get Started Free". */
export const getStarted = () => signup;

/** "Sign In". */
export const signIn = () => login;

/** "Go to Dashboard" — dashboard decides onboarding vs. last-org. */
export const goToDashboard = () => SITE.dashboard.base;

/** Marketplace star hover — "Sign in to save". */
export const saveResource = (id: string) =>
  `${login}?redirect=${encodeURIComponent(`/marketplace/${id}`)}`;

/** Resource detail — "Add to my org". */
export const addToOrg = (id: string) =>
  `${login}?redirect=${encodeURIComponent(`/dashboard/import/${id}`)}`;

/** Publisher page — "Follow". */
export const followPublisher = (username: string) =>
  `${login}?redirect=${encodeURIComponent(`/publishers/${username}`)}`;
