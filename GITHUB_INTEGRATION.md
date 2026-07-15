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

## Notes for the next builder
- No Alembic: new tables auto-create via `create_all`; if you add a **column** to an
  existing table, register it in `main.py::_ensure_additive_columns`.
- Providers are a code catalog synced to the DB on boot — edit `PROVIDER_CATALOG`,
  don't hand-edit rows.
- Keep credentials out of every serializer; only `token_hint` (last 4) is client-safe.
- Dashboard runs on an in-browser mock until `NEXT_PUBLIC_API_URL` is set — keep
  `mock/handlers.ts` in sync with new endpoints.
