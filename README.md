# SR41 — SkillShare by Think41

Monorepo for SkillShare, the skill & MCP registry. Four surfaces:

| Folder       | Purpose                                                                 | Status        |
| ------------ | ----------------------------------------------------------------------- | ------------- |
| `website/`   | Public marketing site — Next.js (App Router, SSR + ISR), SEO-optimized. | **Built (v1)** |
| `client/`    | The dashboard app (functional product, behind `/dashboard`).            | **Built (v1, mock API)** |
| `backend/`   | API services for the registry, auth, and marketplace data.              | **Built (v1, FastAPI)** |
| `extension/` | Browser / editor extension.                                             | Placeholder   |

## Website

Implements the *Marketing Website Specification v1.0*. The site is purely
informational; every functional action redirects into the dashboard
(see `website/src/lib/redirects.ts`).

```bash
cd website
npm install
npm run dev     # http://localhost:3000
npm run build   # production build (static + ISR)
```

Pages: `/`, `/how-it-works`, `/marketplace`, `/marketplace/:id`,
`/publishers/:username`, `/pricing`, `/blog`. Plus auto-generated
`sitemap.xml`, `robots.txt`, and per-resource OG cards.

## Client (Dashboard)

Implements the *Frontend & Dashboard Spec v1.0* plus a GitHub-style profile
page. Runs on an in-browser mock of the backend contract until the API ships.

```bash
cd client
npm install
npm run dev     # http://localhost:3001 — sign in with the demo button
```

Attach the real backend later with `NEXT_PUBLIC_API_URL` (see
`client/README.md` and `backend/BACKEND_SPEC.md` §9).

## Backend (API)

FastAPI implementation of `backend/BACKEND_SPEC.md` — verified against the
client contract by a 49-check smoke test.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m scripts.seed
.venv/bin/uvicorn app.main:app --reload --port 8400
```

Then attach the dashboard: `cd client && NEXT_PUBLIC_API_URL=http://localhost:8400 npm run dev`.

## Integrations (CLI + MCP)

Use the registry from a terminal or from AI agents — `backend/integration/`:

```bash
cd backend && .venv/bin/pip install -e integration/cli -e integration/mcp
.venv/bin/skillshare login                       # CLI for humans/CI
claude mcp add skillshare \
  --env SKILLSHARE_API_URL=http://localhost:8400 \
  --env SKILLSHARE_TOKEN=skst_... -- skillshare-mcp   # MCP server for agents
```

Both authenticate with Personal Access Tokens (`backend/BACKEND_SPEC.md` §10).
