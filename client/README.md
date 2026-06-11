# SkillShare — Dashboard Client

Implements the **Frontend & Dashboard Specification v1.0** (plus a GitHub-style
profile page). Shares the design system of `../website` — white canvas, violet
`#735AE5`, lime `#D1FF00`, Schibsted Grotesk / Manrope / JetBrains Mono — and
the same seed content, so the marketing site and the product feel continuous.

```bash
npm install
npm run dev     # http://localhost:3001
npm run build
```

## Stack

| Layer  | Choice                                  | Notes |
| ------ | --------------------------------------- | ----- |
| Framework | Next.js 16 (App Router)              | matches `../website`; dashboard zone is CSR |
| Styling   | Tailwind CSS 4 + hand-rolled design system | tokens in `src/app/globals.css` |
| State     | Zustand (UI) + React Query (server)  | spec §6 |
| Forms     | React Hook Form + Zod                | spec §1 |
| Editor    | GitHub-style write/preview markdown editor | TipTap upgrade slots behind the same `value/onChange` interface |
| Icons     | Lucide React                         | |

## Running without a backend (today)

There is no backend yet. `src/lib/mock/handlers.ts` implements the **exact
REST surface of `../backend/BACKEND_SPEC.md`** in the browser, persisted to
localStorage. Sign in with the demo button (or any seeded email — any
password is accepted in mock mode).

## Attaching the real backend (one switch)

```bash
NEXT_PUBLIC_API_URL=https://api.skillshare.think41.com npm run build
```

`src/lib/api/http.ts` is the only transport seam: when `NEXT_PUBLIC_API_URL`
is set, every request goes over the network with the JWT `Authorization`
header and the refresh-token cookie; the mock folder becomes dead code and
can be deleted. Screens, hooks, and types stay untouched — they already
speak the backend spec's contract (`src/lib/types.ts` mirrors §2, route
functions in `src/lib/api/index.ts` mirror §3).

## Feature flags, licensing & terminology

Each org has feature flags (Settings → Features): admins toggle
`marketplace`, `publishing`, `command-palette`, `activity-feed`, and
`custom-terminology`. Premium flags need a license (`org.plan = PREMIUM`;
demo key `T41-PREM-XXXX`). `custom-terminology` lets an org relabel
Projects / Pods — e.g. pods read as **Teams** (the seeded Think41 org does
this) — without touching the data model or URLs. `useFeature(key)` /
`useTerms()` in `src/lib/hooks.ts` are the integration points; gated
endpoints are also enforced in the (mock) API. Contract: `BACKEND_SPEC.md`
§2.12 / §3.7.

## Map

```
src/lib/types.ts          data models  = BACKEND_SPEC §2
src/lib/api/index.ts      one fn per endpoint = BACKEND_SPEC §3
src/lib/api/http.ts       transport seam (mock ⇄ network)
src/lib/mock/             in-browser API server + seed data (delete on attach)
src/components/           ResourceCard, badges, drawer (detail + add/edit), browser
src/app/dashboard/        sidebar shell, pod view (core screen), projects,
                          org resources, members, marketplace, profile
```
