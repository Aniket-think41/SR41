# Hive Integration — analysis & roadmap

Second integration provider (after GitHub). **Hive** = the `crispr` repo, a
multi-tenant ERP/HRIS (Keka-like) for IT consulting, owned by Think41, deployed
at `https://hive.think41.com`. Base API: `/api/v1/{tenant_slug}/*` (RPC-over-HTTP).

Where GitHub gives SkillShare *content* (repos → skills/MCP/notes), **Hive gives
SkillShare its people and structure**: who is in the org, which teams/groups they
belong to, which client projects they're allocated to. It turns SkillShare's
org → project → pod hierarchy from something admins hand-build into something
that mirrors the real company automatically.

---

## 1. What Hive can give us (consumption analysis)

All findings are code-grounded against the `crispr/` checkout.

| Hive concept | Endpoint (REST) | Key fields | Maps to (SkillShare) |
|---|---|---|---|
| **Employee / user** | `GET /employees/list` (cursor, ≤200), `/employees/get`, `/employees/org-chart` | `id`, `code` (T001…), `member_id` (stable across rehire), `workspace_email`, `display_name`, `department`, `designation`, `manager_employee_id`, `is_active`, `status`, `last_working_date` | `User` + `OrgMember` |
| **Project** | `GET /delivery/projects/list` (no pagination), `/get` | `id`, `code`, `name`, `status`, `account_id`/`account_name` (client), `project_type`, `tech_stack[]`, `team[]`, `pm_display_name` | `Project` |
| **Allocation** (person↔project) | `POST /allocations/list` (body `{employee_id?}`) | `employee_id`, `project_id`, `percentage`, `start/end_date`, `status`, `is_active` | `ProjectMember` |
| **Group / team** | `GET /groups/list`, `/groups/members/list` | `GroupSummary{id,name,is_active,google_group_emails[]}`, `GroupMemberSummary{group_id,employee_id}` | `Pod` (+ `PodMember`) |
| **Tenant** | `GET /tenants/current` | `code`, `name`, `is_active` | `Organization` binding |

### The five hard constraints (these drive the design)

1. **No machine credential exists.** Auth is RS256 JWT bearer; tokens are only
   minted by a holder of the private key whose JWKS Hive trusts. There is **no
   PAT / API key / service-account / client-credentials endpoint**. The token
   also authenticates *as a real employee* of the tenant, and every read is
   **OPA-gated on that employee's role**. → See §2; this is the biggest
   difference from the GitHub PAT flow.

2. **The integration user must be privileged.** To see *inactive* employees
   (leavers), the token's employee must have an **HR/admin role**; non-HR callers
   get `is_active=false` rows silently filtered out. To see **org-wide
   allocations** (not just their own), the employee must be in the
   **allocation-manager** group. Without both, the sync sees a narrowed slice.

3. **No webhooks / no external events.** Hive's outbox + relay dispatches only to
   *internal* Temporal consumers (email today); there is **no outbound webhook
   registration** and no event bus we can subscribe to. → **We must poll.**

4. **No `updated_since` / weak `updated_at`.** List endpoints have no
   incremental-change filter and most records carry no `updated_at`. → Sync must
   **snapshot + diff** against our own last-known state.

5. **Person identity churns.** Rehires / employment-type conversions mint a *new*
   `employee.id` + `code` for the same human; `member_id` (and workspace email)
   is the stable key. → Dedup on **email**, keep `member_id` as a secondary key.

### Pagination / limits
- Cursor pagination on `employees/list` (≤200) and `groups/members/list` (≤500).
- **No** pagination on `delivery/projects/list` and `allocations/list` (one shot).
- **No** application-layer rate limiting. Tokens expire ~1h.

### MCP alternative — not recommended for sync
Hive exposes `/mcp/?tenant=<code>` with `list_employees` / `list_projects` /
`list_allocations` / `list_groups`, but its auth is **interactive Google OAuth**
(human-tied), not a machine credential, and returns the same OPA-gated data. Use
REST for the headless sync.

---

## 2. The credential problem & recommended fix

GitHub: admin pastes a PAT → done. Hive has no equivalent. Verified login facts
(code-grounded):

- **No username/password login.** `identity/models.py:21` has a dormant nullable
  `password_hash`, but there is **no production password-login route**. Only
  Google OAuth (`/login/google`) and dev-only email login (`/dev-login`, 404 in
  prod).
- **The web session can't be captured.** The SPA uses **HttpOnly cookie sessions**
  (`client/src/lib/apiClient.ts:15` `credentials:'include'`; no bearer/localStorage
  token anywhere). After Google login Hive sets an HttpOnly session cookie + CSRF
  cookie on `hive.think41.com`. A "popup → log in → grab the token" scheme **cannot
  read it** — JS can't read HttpOnly cookies and our origin can't read Hive's
  cookies cross-origin.
- **No refresh endpoint for Hive's own RS256 API JWT.** The only refresh tokens in
  the repo are Google's (for Google API calls), and `token_issuer.issue_api_token`
  is test-only, never exposed. `require_authenticated_principal`
  (`deps.py:95`) accepts **Bearer RS256 (JWKS-verified)** *or* falls back to the
  **cookie session + CSRF**.

### The one interactive token flow that DOES exist — MCP OAuth
`server/app/entrypoints/mcp/auth.py` implements a full **OAuth 2.0
authorization-code flow with Dynamic Client Registration**:
- `register_client` issues a `client_id` for **any** redirect URI (open DCR,
  1-year validity) — SkillShare self-registers.
- Connect → `authorize` → Google login → callback with code → exchange at `/token`
  → a real **Bearer access token our app stores** (**14-day TTL**, `auth.py:458`),
  usable against Hive's **MCP tools** (`list_employees/projects/allocations/groups`).
- **Refresh tokens are stubbed, not issued** — `grant_types` lists `refresh_token`
  and DCR advertises it, but the exchange returns `refresh_token=None` (`auth.py:481`,
  comment at `:456` says the refresh flow is TODO). Token is HS256 `typ=crispr-mcp-access`
  → **valid on `/mcp/` only, not REST** (REST wants RS256/JWKS).
- Tied to the **connecting admin's Google identity** → sync runs with that person's
  OPA permissions (needs HR + allocation-manager) and breaks if they leave.

### Options
- **(A) MCP OAuth popup — recommended to start.** The connect UX the user
  sketched, done to standard. Works today, no cross-repo coordination. SkillShare
  self-registers via DCR, drives the popup, stores the 14-day token
  (Fernet-encrypted), consumes Hive via **MCP tools**. Downsides: person-tied;
  14-day re-popup until refresh is finished.
- **(A+) Finish Hive's refresh flow — recommended durable upgrade.** Complete the
  already-scaffolded refresh-token issuance in `mcp/auth.py` (return + rotate a
  refresh token). Turns (A) into the user's full "token + rotating refresh token"
  design, no 14-day re-popup. Small change; we own the repo.
- **(B) Service credential in Hive — most robust.** Add a per-tenant integration
  API key + `/auth/service-token`(+refresh) issuing **RS256** for a dedicated
  service principal (fixed HR+allocation-manager role), so the connection is **not
  person-tied** and uses the REST API. Bigger Hive build.
- **(C) Pasted 1h RS256 token — demo stopgap.** Ops mints manually. Fragile.
- **(D) Creative — Hive webhook emitter.** Extend the relay `CONSUMERS` (code
  already comments "Future consumers Slack/analytics/**webhook**") to POST
  employee/allocation/group change events to SkillShare. Turns polling into live
  sync; pairs with (B).

**Recommendation:** ship **(A)** now, upgrade to **(A+)**; consider **(B)** if the
connection must survive the connecting admin leaving, and **(D)** for live sync.

---

## 3. Mapping model (Hive → SkillShare)

```
Hive tenant            → bound to one SkillShare Organization (admin picks tenant slug)
Hive employee          → User (dedup by workspace_email) + OrgMember(role=MEMBER)
  manager / HR / PM     → OrgMember(role=ADMIN)              [role mapping, configurable]
Hive group (team)      → Pod   (or Project) + PodMember per GroupMember
Hive delivery project  → Project + ProjectMember per active allocation
Hive allocation        → ProjectMember(role=MEMBER); PM → LEAD/ADMIN
Hive is_active=false   → deactivate/remove member (offboarding sync)
```

Dedup: **email** is the natural key (SkillShare `User.email` is unique; members
are idempotent via `ensure_org/project/pod_member`). To dedup *entities*
(projects/pods) across syncs we need a new **`external_ref`** column (Hive
`id`/`code`) — SkillShare has none today (GitHub import dedups resources by
`source_fingerprint`; we mirror that idea for people/projects).

---

## 3a. Connect → Fetch → Review → Apply (NO sync-on-connect)

Hard requirement: connecting must **never** auto-add members or fire bulk mail.
Instead:

1. **Connect** — store credential, bind tenant. No member/project/pod writes.
2. **Fetch (staging only)** — pull employees + projects + groups + allocations
   into an integration-owned **staging table** (`hive_staged_*` or a JSON snapshot
   on the connection). Nothing enters `OrgMember/Project/Pod` yet. Dashboard shows
   counts + a browsable, diffable list ("will add / already present / will remove").
3. **Review + Selective Apply** — admin chooses scope of what to import:
   **all**, **by project**, or **by team/group**. Each apply runs the existing
   `resolve_or_provision_user` + `ensure_org/project/pod_member` cascade on the
   selected subset only.
4. **Email suppression** — bulk import must **not** send per-user temp-password
   mail (`_notify_added`). Imported users are provisioned **silently** and sign in
   with their **Google workspace email via SSO** (same email Hive uses); optionally
   a single admin-controlled "you've been added" notice instead of per-user mail.
   Add a `notify=False` path to the member-add helpers for the import loop.

Subsequent scheduled syncs (§4) run against the already-applied set; new joiners
land in staging as "pending" for the same review gate (or auto-apply if the admin
opts in per scope).

## 4. Sync cadence — how many scheduled syncs?

Polling-only + offboarding-is-a-security-event drives this. Recommended tiers,
all via the existing external-cron pattern (`POST /api/cron/...` + `X-Cron-Secret`,
GCP Cloud Scheduler — there is **no in-process scheduler** in the backend):

| Sync | Cadence | Scope | Why |
|---|---|---|---|
| **Offboarding / membership** | **Daily** (nightly) | employees `is_active`/`status`, group membership | Monthly is too slow — a terminated employee keeping SkillShare access for weeks is a real risk. Daily is the floor. |
| **Full structure reconcile** | **Weekly** | projects + allocations + groups → projects/pods/members | Project/allocation churn is slower; weekly full diff keeps structure fresh cheaply. |
| **Sync Now** | On demand (admin button) | full | Instant reconcile after an org change; reuses the same code path. |
| *(with webhooks, option C)* | Live | changed entity only | Replaces most scheduled runs once Hive emits events. |

**Execution (SHIPPED):** background sync runs on **Celery** (`app/celery_app.py`
+ `app/tasks.py`), broker = `REDIS_URL` (or `CELERY_BROKER_URL`). Celery **beat**
carries the cadence: `hive-sync-people` daily (scope=members, incl. offboarding
for opted-in orgs) and `hive-sync-structure` weekly (scope=all). The cron
endpoint `POST /api/cron/hive/sync` **enqueues** the job when a broker is set and
otherwise runs it **inline** (`enqueue_or_run`) — so it works with zero infra and
graduates to the worker the moment `REDIS_URL` is present. A connection opts into
hands-off keeping-in-sync via `config.auto_apply` / `auto_offboard`; otherwise the
scheduled run only refreshes staging for admin review. Worker deploy:
`cloudbuild.worker.yaml` (a `skillshare-worker` Cloud Run service, min-instances=1,
running `celery … worker --beat` beside a tiny health app).

**Verdict on "monthly":** monthly is fine only for the slow structure reconcile;
for people/offboarding, go **daily**. So: **daily (people) + weekly (structure) +
Sync Now**, collapsing to **live** if we build the Hive webhook emitter.

---

## 5. Feature roadmap — most common → most creative

### Tier 1 — Table stakes (mirror the GitHub provider)
1. **Hive provider card** in Integrations — gated (ENTERPRISE or its own
   `feature_flag`), connect form, validate + Fernet-encrypt credential, disconnect.
2. **Tenant binding** — admin enters/selects the Hive tenant slug for the org.
3. **Import users → org members** — pull `employees/list`, `resolve_or_provision_user`
   by email, `ensure_org_member`. Dedup, no duplicates.
4. **Sync Now** button (admin) — full reconcile on demand.
5. **Scheduled sync** — daily people + weekly structure via cron endpoint.

### Tier 2 — Structure mapping (the core value)
6. **Projects → SkillShare Projects** (dedup via new `external_ref`).
7. **Allocations → Project members** (person on project; PM → ADMIN/LEAD).
8. **Groups/teams → Pods** with their members.
9. **Offboarding sync** — `is_active=false` / group-removed → deactivate or remove
   the member (with a safe "suspend vs delete" setting).
10. **Role mapping** — manager/PM/HR → ADMIN; configurable in `config`.

### Tier 3 — Governance & trust
11. **Dry-run / sync preview** — diff (adds/updates/removes) before apply, mirroring
    the GitHub `scan` (dry-run) vs `bulk-import` split.
12. **Selective sync** — pick which Hive projects/groups mirror into which
    project/pod scope (reuse the scope-link RBAC cascade).
13. **Don't-clobber-manual-members** — protect members added by hand in SkillShare;
    only manage rows the sync created (track provenance).
14. **Sync audit log + last-error surface** — per-run change report, `last_synced_at`,
    `last_error` (fields already on `OrgIntegration`).
15. **Org-chart-aware admin assignment** — use `employees/org-chart` reporting lines
    to auto-assign pod/project leads.

### Tier 4 — Creative (uses Hive's richer HR/delivery data)
16. **Tech-stack-driven resource recommendations** — a project's `tech_stack[]`
    (React, FastAPI…) → recommend/auto-attach matching marketplace skills/MCP to
    that project's pod. Ties Hive delivery data into SkillShare discovery.
17. **Bench/beach → learning nudges** — `allocations` beach_periods flag un-allocated
    people; nudge them toward relevant skills/notes (learning is even a Hive roadmap
    domain — closes a loop).
18. **New-joiner onboarding pack** — on a new Hive employee, auto-add to org + their
    project's pod + push a starter pack of pinned resources.
19. **Live sync via Hive webhook emitter** — build the outbound webhook into Hive
    (option C) → real-time membership/offboarding instead of polling.
20. **Skill-graph feedback to staffing** — surface which skills a pod actually
    uses/stars back as a signal for Hive allocations/staffing (SkillShare →
    Hive reverse direction).
21. **Hive as identity source (SSO-lite)** — use Hive workspace email + org-chart as
    the authority for SkillShare org membership and admin, one directory of record.

**Smallest shippable slice:** Tier 1 (#1–#5) + #3's dedup + #9 offboarding — a
provider that keeps org membership in lockstep with the real company, daily.

---

## 6. What to build on the SkillShare side (engineering)

Mirrors the GitHub provider precisely (see `GITHUB_INTEGRATION.md`):

1. **Catalog** — add `key="hive"` to `PROVIDER_CATALOG` (`app/integrations.py`);
   add `AUTH_METHODS["hive"]` + `CAPABILITY_CATALOG["hive"]`; optional new
   `features.CATALOG` flag + `feature_flag="hive"` to gate to some orgs.
2. **`app/hive.py`** — mirror `github.py`: `validate_credential()` → tenant/account
   metadata; `list_employees()`, `list_projects()`, `list_allocations()`,
   `list_groups()` (+ token mint/refresh helper for the RS256 exchange); a
   `DetectedMember` / `DetectedProject` dataclass with `to_*_payload()`.
3. **Router** — in `routers/integrations.py`, replace the hardcoded
   `if provider.key != "github"` guard in `connect` with a Hive branch; add
   `/hive/preview`, `/hive/import`, `/hive/sync` reusing `_require_section`,
   `_verify_scope`, `_require_scope_admin`, `resolve_or_provision_user`, and the
   `ensure_*_member` cascade.
4. **Import loop** — model on `_import_detected` (idempotent). Add an
   **`external_ref`** column for project/pod dedup (register in
   `main.py::_ensure_additive_columns`); users dedup by email.
5. **Cron** — extend `cron_sync` or add `/api/cron/hive/sync` (Cloud Scheduler +
   `X-Cron-Secret`); no in-process scheduler exists.
6. **CLI/MCP** — add `cmd_hive_*` + argparse entries and MCP tools
   (`list_hive_users`, `sync_hive`) alongside the GitHub ones.
7. **Migrations** — `create_all` makes fresh tables; register any later columns in
   `_ensure_additive_columns`; `sync_providers` auto-upserts the catalog entry on boot.

Reused as-is: Fernet credential storage (`set_credentials`/`get_credentials`),
client-safe `connection_out`, feature gating, the org⊃project⊃pod scope RBAC.
