# GitHub Integration — build status & roadmap

The Integrations surface for organizations, with GitHub as the first provider.
This doc records **what shipped in phase 1** and **what's deferred**, so the big
product vision (discover → sync → manage) has a clear runway.

Decisions locked with the user:
- **Scope this pass:** foundation + marketing page (not the full sync engine).
- **Tier gate:** any paid plan (**PRO+**) unlocks Integrations.
- **GitHub auth:** **Personal Access Token, encrypted at rest** (Fernet). GitHub
  App / OAuth App are a later phase.

---

## Architecture (as built)

```
Dashboard (Integrations section, premium-gated)
  └─ card grid  →  provider config page  →  connect (PAT) / sync mode / repo browser
        │
        ▼
Backend  /api/orgs/{slug}/integrations/*
  • IntegrationProvider (registry, code catalog → DB on boot)
  • OrgIntegration (per-org connection; credentials_enc via app/crypto.py Fernet)
  • gating: integrations feature (PRO+) + per-provider tier/feature-flag
  • github.py authenticated helpers (validate_token / list / search)
        │
        ▼
CLI (integrations, github-search, github-repos) + MCP
  (list_org_integrations, search_github, list_github_repos)
```

Provider visibility is layered: the `integrations` feature flag gates the whole
section; each provider carries its own `min_plan` and an optional `feature_flag`,
so different premium orgs can see different apps. **GitHub has no extra flag →
every PRO+ org sees it.** To show a new provider to only some orgs: add it to
`PROVIDER_CATALOG`, add a flag to `features.CATALOG`, set the provider's
`feature_flag`.

---

## Phase 1 — SHIPPED ✅

### Backend
- `app/crypto.py` — first at-rest encryption layer (Fernet); key from
  `INTEGRATION_SECRET_KEY`, derived from `JWT_SECRET` in dev. `cryptography` dep added.
- Models `IntegrationProvider` + `OrgIntegration` (`credentials_enc` never serialized).
- `integrations` feature flag (`min_plan=PRO`) in `features.CATALOG`.
- `app/integrations.py` — provider catalog, boot-time `sync_providers`, availability
  filtering, encrypted credential set/get, client-safe serialization.
- `app/github.py` — token support on `HttpFetcher` (private repos via contents API),
  `validate_token`, `list_repositories`, `search_repositories`.
- `app/routers/integrations.py` — providers list, connection detail, connect (validate
  + encrypt), config PATCH, disconnect, `github/repos`, `github/search`. Reads gated on
  org membership + feature; writes on org admin.
- `main.py` boot sync of providers; router wired. Tests in `tests/test_integrations.py`.

### Dashboard (client)
- Sidebar **Integrations** item, gated on the `integrations` feature (mirrors marketplace).
- `/dashboard/org/integrations` — white card grid with hover lift; click → config.
- `/dashboard/org/integrations/[provider]` — connect form (PAT + optional account),
  then config view: connection summary, **sync mode** selector, **repo browser**
  (search connected repos → import detected resources into the org), disconnect.
- `api.*` methods, `qk` keys, `useIntegrationProviders` / `useIntegration` hooks.
- Mock (`mock/handlers.ts` + `mock/db.ts`) mirrors the backend so it works offline.

### Marketing website
- `/github-integration` feature page (discover / sync / manage, auto-detection,
  sync modes, public+private strategy, CLI/MCP). Linked in nav + footer.

### CLI + MCP
- CLI: `integrations`, `github-search <q>`, `github-repos` (default to primary org).
- MCP: `list_org_integrations`, `search_github`, `list_github_repos` + instructions.

---

## Deferred — the rest of the vision (not built)

Grouped by the three goals. Each is additive on the foundation above.

**Discover**
- Full repository scan (all repos, topics/README/manifests) with parser classification
  into the extended type set (Skill, MCP, Service, CLI, SDK, API, Template, Agent,
  Prompt Collection, Workflow, Docs, Library, Plugin). Today: URL/search + existing
  detector (SKILL.md / server.json / .mcp.json / README).
- AI metadata generation for missing summaries/tags/use-cases.
- Automatic resource creation from a scan (vs. the current click-to-import).

**Synchronize**
- GitHub webhooks (push/release/repository/star/fork/delete/rename/archive) → live sync.
- Bidirectional sync engine (README↔description, release↔version, topics↔tags). The
  **sync mode** setting is stored today but not yet acted on.
- Draft-review workflow (GitHub → draft resource → admin approval → published).
- GitHub Releases → resource versions; CI/CD-triggered publish.

**Manage**
- GitHub as storage (edit skill.yaml/README in-repo, SkillShare as UI).
- SkillShare-managed repos (create repo from template; scaffolding).
- Attach repo(s) to a resource; multiple-repo strategy; org/team/pod repo attachment.
- Public + private repo pairing with a merged org view.
- Repository health signals, dependency graph, provenance/trust badges.

**Auth hardening**
- GitHub App installation (fine-grained per-repo access, short-lived tokens) and/or
  OAuth App, replacing/augmenting the PAT.

---

## Requirement: Publish resources to GitHub (SkillShare → GitHub)  ⟵ SHIPPED (phase 3, 2026-07-16)

Added + built 2026-07-16 per product request. The inverse of import: push
SkillShare resources OUT to GitHub, with visibility mirrored.

**Shipped:** `ResourceRepoLink` model; `github.py` write helpers (create repo
public|private, put file, set topics); resource→files serializer; endpoints
`github/publish` (managed repo mirroring visibility, or existing repo),
`github/push`, `github/pull`, `github/link`, `github/links` (incl. reverse
repo→resources), `github/links/{id}` DELETE — gated on the `write` capability;
dashboard "Publish resources to GitHub" panel (publish + push/pull/unlink);
CLI `github-publish/links/push/pull`; MCP `publish_to_github`,
`list_github_links`, `push_to_github`, `pull_from_github`. Tests in
`tests/test_integrations.py`.

**Phase 4 (2026-07-16) shipped the rest, config-gated where it needs your creds:**
- **Full-account scan** (`github/scan`) + **bulk import** (`github/bulk-import`) +
  **team/pod import scope**; **scope-level bulk publish** (`github/publish-scope`);
  **sync-all** (`github/sync-all`). CLI `github-scan/publish-all/sync-all`; MCP
  `scan_github_account`, `bulk_import_github`, `publish_scope_to_github`,
  `sync_all_github`. Dashboard "Publish all / Sync all".
- **Live webhooks** (`POST /api/integrations/github/webhook`, HMAC-verified) —
  push/release → pull linked resources. Active once `GITHUB_WEBHOOK_SECRET` set.
- **Scheduled sync** (`POST /api/cron/integrations/sync`, `X-Cron-Secret`) for a
  Cloud Scheduler job. Active once `CRON_SECRET` set.
- **OAuth App + GitHub App connect** — browser "Connect with GitHub" flow
  (`github/oauth/start` + `/api/integrations/github/oauth/callback`), App
  installation-token minting. Methods auto-activate when their creds are set;
  otherwise render "coming soon".
- **AI metadata** (`app/ai.py`, Anthropic) — optional scan enrichment; inert
  until `ANTHROPIC_API_KEY` set.

Everything is in the codebase and degrades gracefully (Razorpay/Sentry pattern).
The ONLY thing left is supplying the external credentials (GitHub App / OAuth
App / Anthropic key) — no more code needed to light them up.

**Rules**
- A resource, or a whole scope (org / team(project) / pod), can be published to a
  GitHub repository.
- **Visibility mirrors SkillShare → GitHub:** a *public* (published) resource →
  a **public** repo; a *private* resource → a **private** repo. Repo visibility is
  set from the resource/scope visibility, never wider.
- **Public / private pairing:** an org can keep a **public repo** containing only
  the shippable/published resources, and a **private repo** (org-members only)
  containing everything — drafts, internal notes, private versions. The world sees
  the public repo; org members see the merged (private) view.
- **Two targets:** (a) *managed repo* — SkillShare creates + owns the layout
  (README, manifest, `SKILL.md` / `.mcp.json` / `note.md`, `assets/`, `versions/`);
  (b) *existing repo* — export into a chosen repo/subpath.
- **Content mapping:** SKILL → `SKILL.md` (+ frontmatter); MCP → `.mcp.json` /
  `server.json`; NOTE → `README.md` / `note.md`; description → README; version →
  a GitHub release/tag; tags → repo topics; attachments → `assets/`.
- **Gated on the `write` capability** (classic PAT `repo` scope). If missing, the
  publish actions are disabled with a "grant `repo` and Sync" hint (capability
  model already exists).
- Direction honours the connection's stored **`sync_mode`** (write_only /
  bidirectional). Bidirectional needs conflict handling + webhooks.

## Build list — what to create for the above (High tier)

1. **DB**
   - `resource_repo_links` (resource_id, provider_key, repo_full_name, path,
     direction, visibility, last_pushed_sha, last_pushed_at) → also gives the
     reverse "repo → resources" mapping.
   - per-scope publish target: repo + public/private role (extend `OrgIntegration.config`
     or a new `github_publish_targets` table for org/team/pod → repo pairing).
2. **Backend — `github.py` write helpers** (all need `write` capability):
   create repo (public|private), create/update file (contents API PUT with sha),
   create release/tag, set topics, upload asset blobs.
3. **Backend — serializer**: resource → repo file layout (the content mapping above).
4. **Backend — endpoints**:
   - `POST /api/orgs/{slug}/integrations/github/publish` — export a resource or a
     scope; create managed repo (visibility from resource) or push to existing.
   - `POST /api/resources/{id}/github/link` / `DELETE` / `GET /api/resources/{id}/repos`.
   - `GET /api/orgs/{slug}/integrations/github/repos/{owner}/{repo}/resources` (reverse).
   - `POST /api/orgs/{slug}/integrations/github/publish-sync` — run a push for all
     linked resources (the Sync-driven / webhook-driven path).
5. **Backend — sync engine/worker**: on resource create/update (and on Sync click /
   webhook), push to linked repos per `sync_mode`; record `last_pushed_sha`.
   Bidirectional adds GitHub→SkillShare apply + conflict resolution.
6. **Dashboard**:
   - Resource: "Publish to GitHub" / "Link repository" (managed vs existing;
     visibility auto from the resource), show linked repo + last-synced.
   - Integration page: manage the public↔private repo pair + per-scope publish
     targets + a "Publish now" action; surface which repos are managed.
   - Reverse: repo browser marks linked repos; resource shows its repo(s).
7. **CLI / MCP**: `github publish <resource>`, `github link <resource> <repo>`,
   `github repo-resources <repo>`; MCP `publish_to_github`, `link_repo`,
   `repo_resources`.
8. **Webhooks** (for live bidirectional): a receiver endpoint + registration
   (needs `admin:repo_hook` / a GitHub App) so repo edits flow back in.

Dependencies: #1–#4 unlock one-way *publish* (public→public / private→private) —
the smallest shippable slice. #5 makes it stay in sync; #8 makes it live/bidirectional.

---

## Notes for the next builder
- No Alembic: new tables auto-create via `create_all`; if you add a **column** to an
  existing table, register it in `main.py::_ensure_additive_columns`.
- Providers are a code catalog synced to the DB on boot — edit `PROVIDER_CATALOG`,
  don't hand-edit rows.
- Keep credentials out of every serializer; only `token_hint` (last 4) is client-safe.
- Dashboard runs on an in-browser mock until `NEXT_PUBLIC_API_URL` is set — keep
  `mock/handlers.ts` in sync with new endpoints.
