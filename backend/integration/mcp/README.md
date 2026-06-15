# SkillShare MCP Server

Lets AI agents use the registry directly: search the marketplace, read
SKILL.md / MCP configs / notes, browse your org's pods, create notes, star,
and import — over the [Model Context Protocol](https://modelcontextprotocol.io)
(stdio transport).

## Install

The MCP server reuses the CLI's local-scan core, so install the CLI first:

```bash
pip install -e backend/integration/cli        # provides skillshare_cli.local (F2)
pip install -e backend/integration/mcp        # or pipx install once published
```

## Auth

Set two environment variables (see `../README.md` for minting tokens):

```bash
export SKILLSHARE_API_URL=http://localhost:8400
export SKILLSHARE_TOKEN=skst_...     # optional — marketplace tools work without it
```

The token is a SkillShare **Personal Access Token** (`POST /api/auth/tokens`,
or just run `skillshare login` from the CLI and copy it from
`~/.config/skillshare/credentials.json`).

## Connect to Claude Code

```bash
claude mcp add skillshare \
  --env SKILLSHARE_API_URL=http://localhost:8400 \
  --env SKILLSHARE_TOKEN=skst_... \
  -- skillshare-mcp
```

## Connect to Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "skillshare": {
      "command": "skillshare-mcp",
      "env": {
        "SKILLSHARE_API_URL": "http://localhost:8400",
        "SKILLSHARE_TOKEN": "skst_..."
      }
    }
  }
}
```

## Tools

| Tool | Auth | Description |
| ---- | ---- | ----------- |
| `search_marketplace(query, resource_type, tag, sort)` | – | search public skills / MCPs / notes |
| `get_resource(resource_id)` | –/✓ | full content: SKILL.md, MCP url + config JSON, note body, attachments |
| `get_publisher(username)` | – | publisher profile + their public resources |
| `whoami()` | ✓ | the authenticated user |
| `list_my_orgs()` | ✓ | orgs + role + plan |
| `list_org_structure(org_slug)` | ✓ | projects → pods map (ids for targeting) |
| `list_org_resources(org_slug, query, resource_type)` | ✓ | org-level resources |
| `list_pod_resources(pod_id, scope, query, resource_type)` | ✓ | pod library incl. inherited (spec §5) |
| `search_org(org_slug, query)` | ✓ | ⌘K-style search: resources/projects/pods/members |
| `create_note(title, content_md, org_slug \| pod_id, …, attachments)` | ✓ | write a NOTE; `attachments` = [{kind, url, title?}] |
| `upload_file(path, kind)` | ✓ | store a local file (image/video/file) → returns its URL for `attachments` |
| `star_resource(resource_id)` | ✓ | star |
| `import_resource(resource_id, org_slug)` | ✓ | "Add to my org" |
| `check_updates(unread_only, limit)` | ✓ | inbox: resources added/published in your scopes (each with an `install_command` + `resource_id`) |
| `mark_notifications_read(notification_ids, mark_all)` | ✓ | clear inbox items |
| `scan_local(sources, notes_dir, include_dismissed)` | ✓ | find local skills/MCP/notes (Claude Code, Cursor, Codex, Desktop) with status + redacted preview |
| `push_artifact(fingerprint, org_slug \| pod_id, title?, …)` | ✓ | push a scanned artifact (secrets redacted before upload) |
| `dismiss_artifact(fingerprint, kind, source, name)` | ✓ | remember not to recommend it again (synced) |

The server instructions tell the agent to call `check_updates`
**proactively at the start of a conversation** and surface anything new before
other work — so you hear about new team skills / MCPs / notes without asking.

All permissions are enforced server-side by the API (spec §4.2) — the MCP
server holds no logic of its own and can only do what the token's user can.
