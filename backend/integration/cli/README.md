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

# marketplace (works logged-out too)
skillshare search "code review" --type skill
skillshare get pr-reviewer
skillshare pull pr-reviewer -o ./skills      # writes ./skills/pr-reviewer/SKILL.md

# your registry
skillshare list --org think41
skillshare list --pod pod-retrieval --scope all -q eval
skillshare add note --org think41 --title "Deploy checklist" -f checklist.md --tags process,ci
skillshare star incident-runbook
skillshare publish res-handbook              # needs publisher mode + org feature
skillshare import postgres-mcp --org think41

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
