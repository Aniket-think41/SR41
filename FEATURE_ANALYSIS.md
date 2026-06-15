# Feature Analysis — CLI/MCP "Notifications" + "Local → Push Recommendation"

> Status: **analysis for approval** (no code written yet). Read this, then tell me
> what to build / what to change. Open questions are at the bottom.

---

## TL;DR — is it possible?

**Yes, both are feasible**, and they fit the architecture you already have.

| Feature | Verdict | Why |
| --- | --- | --- |
| **F1 — "Tell me when something is added/published, with an install command"** | ✅ Easy-to-medium | You already log every add/publish/join into an `Activity` table; this is mostly *fan-out + a poll surface*. The "install directly" part already exists (`skillshare pull` / `skillshare import`). |
| **F2 — "Detect local skills/MCPs I didn't push, recommend pushing, let my agent fill details, remember rejections"** | ✅ Medium (the interesting one) | Needs local filesystem scanning, provenance/fingerprint tracking, and agent-driven metadata drafting via the MCP. Novel but very doable. Main risk = **secrets in MCP configs**. |

The key insight: **F1 is a read/poll problem on data you already produce. F2 is a new "sync engine" that lives in the CLI/MCP, with the *agent* (Claude) doing the reasoning and *our MCP* doing the I/O.**

---

## What already exists (so we don't rebuild it)

- `Activity` model (`backend/app/models.py`): `user_id, org_id, verb, object_type, object_id, object_title, meta, created_at`. Verbs: `created|updated|published|starred|joined|invited`.
- `log_activity()` (`serialize.py`) is already called on: resource create, resource publish, project create, pod create, invite, join.
- Access model in `permissions.py`: org → project → pod with scope inheritance (spec §5).
- `OrgFeature` table + feature-flag plumbing → we can gate both features per org (`activity-feed` flag already exists).
- PAT auth (`skst_`) — CLI and MCP already authenticate as the user, permissions enforced server-side.
- **Install already works**: `skillshare pull <id>` (writes SKILL.md / mcp-config.json / note.md + attachments) and `skillshare import <id>` (copy into org). So a notification just needs to *carry the id + a ready-to-paste command*.
- CLI/MCP local state already lives at `~/.config/skillshare/credentials.json` — natural home for a sync-state file.

---

## Feature 1 — Subscribe & notify ("something new → here's the link + install command")

### 1.1 Scope of the trigger
Notify a user when, **in a scope they can see**:
- someone **adds** a SKILL / MCP / NOTE (org-level, project, or pod the user belongs to), or
- the org **publishes** a resource to the public marketplace.
Never notify the **actor** about their own action.

### 1.2 Two architecture options

**Option A — Derive-on-read (poll a "what's new since cursor" feed).**
- No new table. New endpoint `GET /api/inbox?since=<cursor>` queries `Activity` filtered to the caller's visible scopes (reuse `permissions.py`), excludes the caller's own rows, returns events + a new cursor.
- Client stores the last-seen cursor locally (CLI/MCP) or server-side per user.
- ➕ Tiny to build, reuses existing data, perfect for the CLI/MCP "poll" model.
- ➖ No unread badge/state, no email/real-time without more work.

**Option B — Materialized `Notification` table (fan-out on write).**
- New `Notification(user_id, activity_id, read_at, …)`. When `log_activity()` fires, fan out one row per eligible recipient.
- ➕ Real unread/read state, supports dashboard bell + email + Slack + webhooks later, scales to push.
- ➖ More moving parts; fan-out cost on write; needs subscription/preference model to avoid noise.

**Recommendation: start with A, grow into B.** Ship the poll feed first (covers CLI + MCP immediately and the agent use case). Add the `Notification` table when you want a dashboard bell, unread counts, or email/Slack delivery.

### 1.3 Delivery surfaces
- **CLI**: `skillshare inbox` (or `whats-new`) → prints new items, each with a one-line `skillshare pull <id>` / `import <id>` and a dashboard deep link.
- **MCP**: `check_updates()` tool → returns new items so the user's agent can say "3 new skills in your pod — want me to install `pr-reviewer`?" and then call `pull`/`import`.
- **Dashboard**: bell icon (needs Option B for unread state).
- **Optional later**: email digest, Slack/webhook (you already have an `S3`/external-config pattern; webhooks fit the same shape).

### 1.4 Subscription granularity (preference model)
Decide what users can mute: whole-org vs per-project/pod vs per-type (only MCPs, etc.) vs only-publishes. MVP can be "all scopes I belong to, minus my own actions" with no prefs, then add mutes.

### 1.5 The "install directly" part
Already solved — we just attach to each notification:
- `resource_id`,
- a copy-paste command (`skillshare pull <id> -o ./skills` for skills, `skillshare import <id> --org <slug>` for adopting),
- a dashboard URL (`/dashboard/marketplace/<id>` or the in-app drawer deep link).

**Effort: F1 Option A ≈ small** (1 endpoint + access filter + CLI cmd + MCP tool + cursor storage). Option B is a follow-up.

---

## Feature 2 — Local discovery → "push this to the platform?" (agent-assisted)

This is the standout feature: turn local, hand-made skills/MCPs/notes into shared registry entries, with the agent drafting the metadata and the user approving once.

### 2.1 Where local artifacts live (what we scan)
- **Skills**: `~/.claude/skills/<name>/SKILL.md`, project `.claude/skills/`. (Extensible to other agents later: Cursor rules, etc.)
- **MCP servers**: `~/.claude.json` (`mcpServers`), project `.mcp.json`, `.cursor/mcp.json`, `claude_desktop_config.json`.
- **Notes**: ambiguous — needs a definition (opt-in folders of markdown? a configured `notes_dir`?). **Open question.**
- Scan locations should be a configurable allow-list, never a blind full-disk crawl.

### 2.2 "Not added by us" → provenance + fingerprinting
We need to know which local artifacts are already ours and which are new/changed. Add a **sync-state file**: `~/.config/skillshare/sync-state.json`:
```jsonc
{
  "<content-fingerprint>": {
    "path": "~/.claude/skills/pr-reviewer/SKILL.md",
    "kind": "skill",
    "status": "pushed | rejected | pending",
    "resource_id": "res_…",     // if pushed
    "last_seen": "2026-06-15T…"
  }
}
```
- **Fingerprint = hash of normalized content.** If the file changes, the fingerprint changes → it re-surfaces as "updated, push again?". Identical content stays muted.
- Things `pull`/`add` create should be **stamped automatically** (status `pushed` + `resource_id`) so we never recommend pushing something we just installed.
- Optional backend support: a `source_fingerprint` column on `Resource` so we can detect "this already exists on the platform (pushed from another machine)" and offer *link* instead of *duplicate*.

### 2.3 The agent-assisted flow (the part you described)
1. **Scan** — `skillshare scan` (CLI) or MCP `scan_local()` walks the allow-listed locations, fingerprints each artifact.
2. **Filter** — drop anything `status=pushed` (ours) or `status=rejected` (remembered). What's left = **candidates**.
3. **Draft (agent does the thinking)** — MCP returns each candidate's raw content to the host agent (Claude), which drafts `title`, `description`, `tags`, cleaned `content_md`. This is exactly *"our cli and mcp going to the user's agent to fill the details."*
4. **Approve** — agent shows the user the drafted entry → user approves or rejects.
   - **Approve** → MCP/CLI calls the existing create endpoint (`create_note` / a new `push_skill` / `push_mcp`) and stamps sync-state `pushed` + `resource_id`.
   - **Reject** → stamp sync-state `rejected` (remembered by fingerprint).
5. **Next time** — rejected items stay silent. User can later just say *"push my pr-reviewer skill"* and the agent runs the push tool directly; or `skillshare push <path>` / re-enable a rejected one with `skillshare scan --include-rejected`.

### 2.4 Why MCP-first
The metadata drafting (good title/description/tags from raw SKILL.md) is an LLM job. So the right division of labor is:
- **Our MCP/CLI** = deterministic I/O: scan, fingerprint, read file, redact secrets, call API, persist state.
- **The host agent (Claude)** = reasoning: draft metadata, converse, get approval.
New MCP tools roughly: `scan_local()`, `get_local_artifact(path)`, `push_artifact(kind, draft, source_fingerprint)`, `dismiss_artifact(fingerprint)`, `list_dismissed()`.

### 2.5 ⚠️ Critical risk — secrets in MCP configs
MCP server configs routinely contain **API keys, tokens, connection strings, env vars**. If we push those to a shared/public registry we leak credentials. Mandatory:
- **Redact** known secret-shaped fields (`env`, `headers`, `*_KEY`, `*_TOKEN`, `Authorization`, URLs with credentials) before drafting/pushing, replacing with `${PLACEHOLDER}`.
- **Show the user exactly what will be sent** before any upload (diff/preview).
- Never auto-push; always explicit approval.
This applies to skills too (a SKILL.md can embed secrets) but MCP configs are the high-risk case.

### 2.6 Privacy / consent
- Local FS scanning must be **explicit opt-in** (first run asks, or a `skillshare scan` you invoke). No silent background crawling.
- Show the file list found before reading contents into the agent.

**Effort: F2 ≈ medium.** Scan + fingerprint + sync-state + redaction + 4–5 MCP tools + 2 CLI commands. The agent reasoning is "free" (host model). Backend change is optional (`source_fingerprint`).

---

## Cross-cutting

- **Feature-flag both** via your existing `OrgFeature` infra (e.g. `notifications`, `local-sync`) so orgs opt in.
- **Auth**: PAT already covers it; all writes stay permission-checked server-side.
- **Backend additions**: F1 → 1 endpoint (Option A) or a `Notification` table (Option B). F2 → optional `source_fingerprint` on `Resource` + maybe `push_skill`/`push_mcp` endpoints (or reuse existing create with attachments).

---

## Suggested phasing

1. **F1 MVP** — derive-on-read `GET /api/inbox?since=`, `skillshare inbox`, MCP `check_updates()`, local cursor. *(small)*
2. **F1 polish** — `Notification` table, dashboard bell + unread, mute/subscription prefs, email/Slack. *(medium)*
3. **F2 MVP** — `scan_local` + sync-state + fingerprint + secret redaction + MCP push/dismiss tools + CLI `scan`/`push`. *(medium)*
4. **F2 polish** — multi-agent sources (Cursor/Desktop), drift detection ("local changed, update remote?"), cross-machine dedup via `source_fingerprint`. *(medium)*

I'd ship **Phase 1 then Phase 3** first — they give you the full "notify + adopt + contribute back" loop with the least backend surface.

---

## Decisions (LOCKED — 2026-06-15)

1. **F1 delivery** → **full** (Option B): materialized `Notification` table + unread state + dashboard bell, *plus* the poll feed for CLI/MCP.
2. **F1 scope** → membership-based fan-out: a user is notified about activity in the **orgs**, **projects**, and **pods they are a member of** — nothing outside their membership. Never notified about their own action.
3. **F1 channels** → **CLI + MCP + dashboard bell only**. No email/Slack.
4. **F2 artifacts** → **all three: skills, MCP servers, AND notes.**
5. **F2 scan sources** → **Claude Code is primary**, but the detector layer must be **pluggable** so Cursor, Codex, Claude Desktop, and others are supported.
6. **F2 secrets** → **redact + preview before every push.** No auto-upload.
7. **F2 surface** → **CLI and MCP equally** (shared core, two front-ends).
8. **Rejection / provenance memory** → **synced server-side per user** (carries across machines) with a local cache for offline/speed.

---

## Finalized build plan

### Hard constraints discovered in the code
- Tables are created by `Base.metadata.create_all()` on startup (no Alembic). **New tables (`notifications`, `local_artifact_states`) auto-create.** But adding `source_fingerprint` to the existing `resources` table won't ALTER on SQLite — **requires a reseed** (`scripts/seed.py --reset`), which we do in dev anyway.
- `Activity` only stores `org_id`. For org/project/pod-granular fan-out we extend `log_activity(...)` to also take `scope_type` + `scope_id` (from the resource/pod/project) and write `Notification` rows for the scope's members.

### Backend
**F1**
- Model `Notification`: `id, user_id (recipient), actor_id, org_id, scope_type, scope_id, verb, object_type, object_id, object_title, meta, read_at?, created_at`.
- Fan-out helper invoked from `log_activity`: recipients = members of the scope (org→`org_members`, project→`project_members`, pod→`pod_members`) **minus the actor**; one row each. Publish = org-scoped → notifies org members.
- Endpoints: `GET /api/notifications?unread=&since=&limit=`, `GET /api/notifications/unread_count`, `POST /api/notifications/read` (ids or all), serialized with an **install hint** (`command` + dashboard `deep_link`).
- Feature flag `notifications` added to `features.py` CATALOG.

**F2**
- Model `LocalArtifactState` (per user): `id, user_id, fingerprint, kind (skill|mcp|note), source, status (pushed|dismissed), resource_id?, name, updated_at`. → server-synced rejection/provenance memory.
- `resources.source_fingerprint` column (nullable) for cross-machine "already exists → link, don't duplicate".
- Endpoints: `GET /api/local-state`, `POST /api/local-state` (upsert), and `source_fingerprint` accepted by the existing create endpoint.

### Shared core lib (used by both CLI + MCP)
- `detect/` — pluggable source detectors: `claude_code`, `cursor`, `codex`, `claude_desktop` (each yields `{kind, name, path, raw}`).
- `fingerprint.py` — normalized content hash.
- `redact.py` — strip secret-shaped fields (`env`, `headers`, `*_KEY|*_TOKEN`, `Authorization`, creds-in-URL) → `${PLACEHOLDER}`, returns redacted copy + report.
- Lives in the CLI package; MCP imports it (same repo).

### CLI (`skillshare ...`)
- `inbox` — list notifications (`--unread`, `--mark-read`), local cursor.
- `scan` — run detectors, fingerprint, reconcile with server `local-state`, list candidates (`--source`, `--include-dismissed`, `--json`).
- `push <path>` — push one artifact: pick target scope, redact + **preview/confirm**, create resource, mark `pushed`; decline → mark `dismissed`.

### MCP (agent-driven, equal surface)
- `check_updates()` / `list_notifications(unread)` / `mark_notification_read(id)`.
- `scan_local()` → candidates (reconciled). `get_local_artifact(path)` → redacted content for the agent to draft.
- `push_artifact(kind, source_fingerprint, scope, title, description, tags, body, attachments)` → create + mark pushed.
- `dismiss_artifact(fingerprint)` → mark dismissed (server-synced).

### Dashboard (client)
- Topbar **notification bell** + unread badge → dropdown list → mark-read → deep-link opens the resource drawer. Query hooks + api methods + mock handlers (mock mode).

### Phasing (build order)
1. **Backend F1** — `Notification` model, fan-out in `log_activity`, endpoints, feature flag.
2. **CLI `inbox` + MCP `check_updates`** — verify the notify loop end-to-end.
3. **Dashboard bell** — unread badge + dropdown + deep-link.
4. **Backend F2** — `LocalArtifactState`, `source_fingerprint`, endpoints (+ reseed).
5. **Shared core lib** — detectors (Claude Code first), fingerprint, redact.
6. **CLI `scan`/`push` + MCP `scan_local`/`push_artifact`/`dismiss_artifact`** — full adopt loop, both surfaces.
7. **More sources** — Cursor, Codex, Claude Desktop detectors; drift detection.

Each phase ends with a live smoke test against the running stack before moving on.
