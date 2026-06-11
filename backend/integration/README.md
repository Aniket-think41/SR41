# SkillShare Integrations

Two ways to use the registry outside the dashboard. Both speak the same REST
API (`../BACKEND_SPEC.md`) and authenticate with **Personal Access Tokens**
(spec §10) — long-lived `skst_…` bearer tokens minted per user.

| Folder | What | Who uses it |
| ------ | ---- | ----------- |
| [`cli/`](./cli) | `skillshare` command-line client | humans in a terminal, CI scripts |
| [`mcp/`](./mcp) | MCP server (stdio) | AI agents — Claude Code, Claude Desktop, any MCP client |

## Auth in one minute

```bash
# Interactive (recommended): logs in, mints a PAT, stores it locally
skillshare login

# Or mint a token by hand and export it (what the MCP server uses)
curl -s -X POST $API/api/auth/tokens \
  -H "Authorization: Bearer <jwt-from-login>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my laptop"}' | jq -r .token
export SKILLSHARE_TOKEN=skst_...
```

- Tokens are shown **once** at creation; the server stores only a SHA-256 hash.
- Manage them: `GET /api/auth/tokens`, `DELETE /api/auth/tokens/:id`
  (or `skillshare tokens` / `skillshare logout`).
- Every API permission rule (spec §4.2) applies to PATs exactly as to the
  dashboard session — a token can only see what its user can see.

## Environment variables

| Variable | Used by | Meaning |
| --- | --- | --- |
| `SKILLSHARE_API_URL` | cli + mcp | API origin, e.g. `http://localhost:8400` |
| `SKILLSHARE_TOKEN` | cli + mcp | a `skst_…` PAT (the CLI can also read its stored login) |

## Install (dev, from this repo)

```bash
cd backend
.venv/bin/pip install -e integration/cli -e integration/mcp
.venv/bin/skillshare --help
.venv/bin/skillshare-mcp   # stdio MCP server (waits for an MCP client)
```
