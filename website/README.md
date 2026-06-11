# SkillShare — Marketing Website

Public marketing site for SkillShare by Think41 (Next.js 16, App Router,
SSR + ISR, SEO-optimized). Implements the *Marketing Website Specification
v1.0*. The site is informational; every functional action redirects into the
dashboard app (`../client`) via `src/lib/redirects.ts`.

## Run it

```bash
cd website
npm install
npm run dev      # http://localhost:3000
npm run build    # production build (static + ISR)
```

Pages: `/`, `/how-it-works`, `/marketplace`, `/marketplace/:id`,
`/publishers/:username`, `/pricing`, `/blog`, plus auto-generated
`sitemap.xml`, `robots.txt`, and per-resource OpenGraph cards.

## Marketplace data — single source of truth

The marketplace pages read from the backend's **public** API
(`/api/public/*`, see `../backend/BACKEND_SPEC.md` §3.6) so the website,
dashboard, CLI, and MCP all show the same content in the same wire shape
(`src/lib/data.ts`).

```bash
# Wire the site to a running backend (server-side fetch + ISR, revalidate 60s):
API_URL=http://localhost:8400 npm run dev
```

- `API_URL` (or `NEXT_PUBLIC_API_URL`) set → pages fetch live with ISR.
- Neither set → the site falls back to the bundled seed in `src/lib/data.ts`
  (mirrors `backend/scripts/seed.py`) so a standalone marketing build still
  renders real content with no backend.

## Notes

- This is Next.js 16 — read `node_modules/next/dist/docs/` before changing
  framework-level code (async `params`, ISR, metadata, etc.).
- Design tokens (violet/lime/ink palette, Schibsted Grotesk / Manrope /
  JetBrains Mono, 20px card radius, ◆▣▤ glyphs) are shared with the dashboard.
