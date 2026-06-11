# SkillShare API — FastAPI

Implements [`BACKEND_SPEC.md`](./BACKEND_SPEC.md) end to end: auth (JWT +
refresh rotation), orgs / projects / pods, resources with scope inheritance,
the public marketplace, GitHub-style profiles, feature flags + premium
licensing, activity, ⌘K search, rate limiting, and the §7 error envelope.
The wire format matches the dashboard client (`../client`) field-for-field.

## Run it

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                # then edit (see the env table below)

.venv/bin/python -m scripts.seed    # demo data (same content as the client mock)
.venv/bin/uvicorn app.main:app --reload --port 8400
```

API docs: http://localhost:8400/docs · health: `GET /api/health`

> Port 8000 is a common default for other local services — pick 8400 (or
> anything free) and point the client at it.

Demo login after seeding: `aniket.lnu@think41.com` / `skillshare-demo`
(every seeded user shares `SEED_PASSWORD`).

## Attach the dashboard

```bash
cd ../client
NEXT_PUBLIC_API_URL=http://localhost:8400 npm run dev
```

That's the whole integration — the client's transport seam
(`client/src/lib/api/http.ts`) switches off its in-browser mock when
`NEXT_PUBLIC_API_URL` is set.

## Verify

```bash
.venv/bin/python -m scripts.smoke   # 44-check contract test (throwaway SQLite)
```

## Integrations (CLI + MCP)

The registry is also usable from a terminal and from AI agents — see
[`integration/`](./integration) (spec §10). Both authenticate with
**Personal Access Tokens** (`POST /api/auth/tokens`, `skst_…`).

```bash
.venv/bin/pip install -e integration/cli -e integration/mcp
.venv/bin/skillshare login          # CLI: mints + stores a PAT
claude mcp add skillshare \
  --env SKILLSHARE_API_URL=http://localhost:8400 \
  --env SKILLSHARE_TOKEN=skst_... -- skillshare-mcp
```

## Layout

```
app/config.py        env-driven settings (see .env.example)
app/models.py        SQLAlchemy models = SPEC §2 (+ api_tokens, §10)
app/security.py      passwords, JWT (HS256/RS256), refresh rotation, PATs
app/permissions.py   scope-based access checks = SPEC §4.2
app/features.py      flag catalog + resolution = SPEC §2.12
app/ratelimit.py     sliding-window limits = SPEC §4.3
app/serialize.py     wire-format output (scope_label, author, counts…)
app/routers/         auth (+PATs) · orgs (+features/license/search/activity)
                     · projects · pods · resources · public · users
integration/cli/     `skillshare` command-line client (SPEC §10.2)
integration/mcp/     `skillshare-mcp` MCP server for agents (SPEC §10.3)
scripts/seed.py      demo data, idempotent (--reset to wipe)
scripts/smoke.py     end-to-end contract test
```

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | prod | `sqlite:///./skillshare.db` | Postgres 15+ in prod (`postgresql+psycopg2://…`) |
| `JWT_SECRET` | prod | dev placeholder | HS256 signing secret |
| `JWT_ALGORITHM` | – | `HS256` | set `RS256` + keypair for spec-exact RS256 |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | RS256 only | – | PEM keypair |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | – | `15` | spec §4.1 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | – | `7` | spec §4.1 |
| `CORS_ORIGINS` | prod | `http://localhost:3001` | dashboard origin(s), comma-separated |
| `GOOGLE_CLIENT_ID` | optional | – | enables `POST /api/auth/google` |
| `RATE_LIMIT_ENABLED` | – | `true` | plus `RATE_LIMIT_{AUTH,WRITE,SEARCH}_PER_MIN` |
| `REDIS_URL` | optional | – | shared limiter store for multi-instance deploys |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL`, `S3_PUBLIC_BASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | optional | – | presigned uploads (§6); placeholder URLs otherwise |
| `MAX_UPLOAD_MB` | – | `10` | spec §6 |
| `LICENSE_KEY_PATTERN` | – | `^T41-PREM-[A-Z0-9]{4,}$` | accepted license keys |
| `SEED_PASSWORD` | – | `skillshare-demo` | password for seeded demo users |
| `ENV` | – | `development` | `production` enables Secure cookies |

## Production notes

- Move `Base.metadata.create_all` to Alembic migrations before real data.
- Set `JWT_ALGORITHM=RS256` with a keypair for the spec-exact setup.
- Run ≥2 instances? Set `REDIS_URL` so rate limits are shared.
- Postgres FTS (or Meilisearch) replaces the v1 Python-side search when
  resource counts grow (spec §1).
