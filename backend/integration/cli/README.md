# skillshare — CLI

Command-line client for the SkillShare registry. Same API, same permissions
as the dashboard (BACKEND_SPEC §4.2) — authenticated with a Personal Access
Token (spec §10).

## Install

```bash
pip install -e backend/integration/cli       # or pipx install once published
```

## Quick start

```bash
skillshare login                 # email + password → mints & stores a PAT
skillshare whoami
skillshare orgs

# inbox — resources added/published in your scopes (org / your projects / your pods)
skillshare inbox                 # newest first; ● marks unread, shows install command
skillshare inbox --unread        # only unread
skillshare inbox --mark-read     # list, then clear them

# marketplace (works logged-out too)
skillshare search "code review" --type skill
skillshare get pr-reviewer
skillshare pull pr-reviewer -o ./skills      # writes SKILL.md + downloads attachments/
skillshare pull incident-runbook --no-assets # keep attachment URLs, don't download

# your registry
skillshare list --org think41
skillshare list --pod pod-retrieval --scope all -q eval

# files & attachments (uploaded to the server's storage backend, §6)
skillshare upload diagram.png --kind image   # stores it, prints the URL
skillshare add note --org think41 --title "Deploy checklist" -f checklist.md --tags process,ci \
  --image diagram.png \                       # local file → uploaded automatically
  --video https://youtu.be/… \                # or pass a URL as-is
  --link https://runbook.example.com
skillshare star incident-runbook
skillshare publish res-handbook              # needs publisher mode + org feature
skillshare import postgres-mcp --org think41

# contribute local artifacts (F2) — find local skills/MCP/notes not on the platform
skillshare scan                              # lists candidates; NEW = not pushed yet
skillshare scan --source claude-code --source cursor   # limit sources (also: codex, claude-desktop)
skillshare scan --notes-dir ./docs           # also treat ./docs/*.md as notes
skillshare push --org think41                # push NEW ones (secrets redacted; previews + confirms each)
skillshare push --org think41 --fingerprint fp_ab12   # push just one
skillshare dismiss fp_ab12                   # never recommend this one again (synced server-side)

# housekeeping
skillshare tokens                            # list PATs
skillshare logout                            # revoke + forget
```

## Configuration

| Source | Notes |
| --- | --- |
| `~/.config/skillshare/credentials.json` | written by `login` (chmod 600): `{api_url, token, token_id, email}` |
| `SKILLSHARE_API_URL` env | overrides the stored API URL |
| `SKILLSHARE_TOKEN` env | overrides the stored token — use in CI |
| `SKILLSHARE_CONFIG_DIR` env | alternate config dir |

CI example:

```bash
SKILLSHARE_API_URL=https://api.skillshare.think41.com \
SKILLSHARE_TOKEN=$SKILLSHARE_CI_TOKEN \
skillshare list --org think41 --type skill
```
