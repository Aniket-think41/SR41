# BACKEND SPECIFICATION

**SkillShare** — API Design, Data Models & Service Architecture
*SkillShare by Think41 — Backend Spec v1.0*

> **Status: implemented** — FastAPI service in this folder (`app/`), verified
> against the client contract by `scripts/smoke.py` (49 checks). Run + env
> reference: [`README.md`](./README.md). The dashboard client (`../client`)
> attaches by setting one env var (see §9); its
> `client/src/lib/mock/handlers.ts` remains the in-browser fallback when no
> API URL is configured.

---

## 1. Technology Stack

Recommended stack. Teams may substitute equivalent technologies.

| Layer        | Technology                          | Notes |
| ------------ | ----------------------------------- | ----- |
| Runtime      | Node.js 20+ / Python FastAPI        | Either; Node preferred for JS teams |
| Framework    | Express / Fastify / FastAPI         | RESTful JSON API |
| Database     | PostgreSQL 15+                      | Primary store; multi-tenant RLS |
| ORM          | Prisma / SQLAlchemy                 | Schema migrations included |
| Auth         | JWT (access + refresh tokens)       | Google OAuth via Passport / Authlib |
| Cache        | Redis                               | Sessions, rate limits, search cache |
| Search       | PostgreSQL Full-Text / Meilisearch  | FTS sufficient for v1 |
| File Storage | S3-compatible (AWS S3 / Cloudflare R2) | Skill package uploads |
| Hosting      | Railway / Render / AWS ECS          | Stateless containers |

---

## 2. Data Models

Field names below are the wire format — the client types match 1:1.

### 2.1 User

```
users {
  id, email, password_hash, username, display_name, avatar_url, bio,
  location, website,            -- GitHub-style profile additions (§8)
  is_publisher, verified, created_at, updated_at
}
```

- `is_publisher`: boolean — enables public marketplace publishing.
- `username`: unique URL-safe handle, used by publisher/profile routes.
- Linked to: `org_members`, `project_members`, `pod_members`, `resources`.

### 2.2 Organization

```
organizations {
  id, name, slug, logo_url, description, is_public, owner_id,
  plan: FREE|PREMIUM,           -- licensing tier (§8)
  terminology: { project, pod },-- custom labels, e.g. pod → "Team" (§8)
  created_at
}
```

- `slug`: unique URL-safe identifier.
- `is_public`: false by default — future feature to allow public org profiles.
- `plan`: set to `PREMIUM` by license activation (§3.8); unlocks premium flags.
- `terminology`: UI labels only — routes, models, and API names stay
  `projects` / `pods`. Writable only while the `custom-terminology` feature
  is enabled (else `403 FORBIDDEN`).

### 2.3 Org Member

```
org_members { id, org_id, user_id, role: ADMIN|MEMBER, joined_at }
```

### 2.4 Project

```
projects { id, org_id, name, description, tags[], visibility: ORG|PUBLIC, created_by, created_at }
```

### 2.5 Project Member

```
project_members { id, project_id, user_id, role: LEAD|MEMBER }
```

### 2.6 Pod

```
pods { id, project_id, name, description, purpose_tag, created_by, created_at }
```

### 2.7 Pod Member

```
pod_members { id, pod_id, user_id, role: OWNER|MEMBER }
```

### 2.8 Resource

```
resources {
  id, type: SKILL|MCP|NOTE, title, description, content_md,
  server_url, config_json,      -- MCP structured fields (§8)
  file_url, version, tags[],
  attachments[],                -- hybrid content model (see below)
  scope_type: ORG|PROJECT|POD|PUBLIC, scope_id,
  author_id, is_public, stars_count, installs_count, created_at, updated_at
}
```

- `scope_type` + `scope_id` together define where a resource lives.
- `is_public`: true when published to public marketplace.
- `file_url`: S3 URL for uploaded skill packages.
- `attachments`: typed media (hybrid content model). JSON array of
  `{ kind: link|image|video|file, url, title?, caption? }`. `content_md` stays
  the canonical prose; attachments add structured media. Consumers that are
  markdown-only (CLI `pull`, MCP, website) render attachments as a trailing
  `## Resources` section / media block, so nothing downstream breaks.

### 2.9 Resource Star

```
resource_stars { id, resource_id, user_id, created_at }
```

### 2.10 Invitation

```
invitations { id, org_id, email, role, token, expires_at, accepted_at }
```

### 2.11 Activity (§8 addition)

```
activities { id, user_id, org_id, verb, object_type, object_id, object_title, meta, created_at }
```

- `verb`: created | updated | published | starred | joined | invited.
- Powers the dashboard-home feed and the profile activity tab.

### 2.12 Feature Flags & Licensing (§8 addition)

```
feature_flags { key PK, name, description, premium: bool, default_enabled: bool }
org_features  { id, org_id, key → feature_flags.key, enabled: bool }   -- per-org override
licenses      { id, org_id, license_key, plan: PREMIUM, activated_by, activated_at, expires_at }
```

- `feature_flags` is the global catalog (seeded by migration, managed by
  Think41 staff — not org admins). v1 catalog:

  | key                  | premium | default | gates |
  | -------------------- | ------- | ------- | ----- |
  | `marketplace`        | no      | on      | marketplace browse + `POST /resources/:id/import` |
  | `publishing`         | **yes** | on      | `POST /resources/:id/publish` |
  | `command-palette`    | no      | on      | `GET /orgs/:slug/search` (UI hides ⌘K) |
  | `activity-feed`      | no      | on      | `GET /orgs/:slug/activity` (UI hides feed) |
  | `custom-terminology` | **yes** | on      | `terminology` writes on `PATCH /orgs/:slug` |

- **Resolution rule** (must match the client's expectations):
  `licensed = !flag.premium || org.plan == PREMIUM`;
  `enabled = licensed && (override.enabled ?? flag.default_enabled)`.
  Unlicensed premium flags are always `enabled: false`, overrides ignored.
- Enforce flags **server-side on the gated endpoints** (403 with a clear
  message), not just in the UI.

---

## 3. API Endpoints

### 3.1 Auth

| Method | Endpoint            | Description |
| ------ | ------------------- | ----------- |
| POST   | `/api/auth/signup`  | Register new user with email + password |
| POST   | `/api/auth/login`   | Login, returns JWT access + refresh tokens |
| POST   | `/api/auth/google`  | Google OAuth callback |
| POST   | `/api/auth/refresh` | Refresh access token |
| POST   | `/api/auth/logout`  | Invalidate refresh token |
| GET    | `/api/auth/me`      | Get current user profile |
| PATCH  | `/api/auth/me`      | Update own profile (§8 — display_name, bio, location, website, is_publisher) |
| POST   | `/api/auth/tokens`  | **§10** Mint a Personal Access Token — body `{name, expires_days?}`; full token returned once |
| GET    | `/api/auth/tokens`  | **§10** List my tokens (prefix + metadata only) |
| DELETE | `/api/auth/tokens/:id` | **§10** Revoke a token |

`signup`/`login` response (consumed by `client/src/components/AuthShell.tsx`):

```json
{ "user": { …User }, "access_token": "…", "refresh_token": "…" }
```

### 3.2 Organizations

| Method | Endpoint                            | Description |
| ------ | ----------------------------------- | ----------- |
| GET    | `/api/orgs`                         | **§8** List orgs the caller belongs to (`my_role` included) — powers the org switcher |
| POST   | `/api/orgs`                         | Create organization |
| GET    | `/api/orgs/:slug`                   | Get org details (+ caller's `my_role`) |
| PATCH  | `/api/orgs/:slug`                   | Update org settings (admin only) |
| GET    | `/api/orgs/:slug/members`           | List members (each with embedded `user`) |
| POST   | `/api/orgs/:slug/invite`            | Send invitation by email |
| GET    | `/api/orgs/:slug/invitations`       | **§8** List pending invitations (admin) |
| DELETE | `/api/orgs/:slug/invitations/:id`   | **§8** Cancel a pending invitation |
| POST   | `/api/orgs/:slug/join/:token`       | Accept invitation |
| DELETE | `/api/orgs/:slug/members/:userId`   | Remove member |
| PATCH  | `/api/orgs/:slug/members/:userId`   | **§8** Change a member's role |
| GET    | `/api/orgs/:slug/activity`          | **§8** Recent activity feed (≤20) |
| GET    | `/api/orgs/:slug/search?q=`         | **§8** Command palette: `{ resources, projects, pods, members }` |

### 3.3 Projects

| Method | Endpoint                                            | Description |
| ------ | --------------------------------------------------- | ----------- |
| GET    | `/api/orgs/:slug/projects`                          | List org projects (+ `pods_count`, `members_count`, `resources_count`) |
| POST   | `/api/orgs/:slug/projects`                          | Create project (creator becomes LEAD) |
| GET    | `/api/orgs/:slug/projects/:projectId`               | Get project |
| PATCH  | `/api/orgs/:slug/projects/:projectId`               | Update project |
| DELETE | `/api/orgs/:slug/projects/:projectId`               | Delete project (cascades pods + scoped resources) |
| GET    | `/api/orgs/:slug/projects/:projectId/members`       | List project members |
| POST   | `/api/orgs/:slug/projects/:projectId/members`       | Add member to project |

### 3.4 Pods

| Method | Endpoint                                      | Description |
| ------ | --------------------------------------------- | ----------- |
| GET    | `/api/projects/:projectId/pods`               | List pods in project (+ counts) |
| POST   | `/api/projects/:projectId/pods`               | Create pod (creator becomes OWNER) |
| GET    | `/api/projects/:projectId/pods/:podId`        | Get pod |
| PATCH  | `/api/projects/:projectId/pods/:podId`        | Update pod |
| DELETE | `/api/projects/:projectId/pods/:podId`        | Delete pod (cascades pod-scoped resources) |
| GET    | `/api/projects/:projectId/pods/:podId/members`| **§8** List pod members |
| POST   | `/api/projects/:projectId/pods/:podId/members`| Add pod member |

### 3.5 Resources

| Method | Endpoint                              | Description |
| ------ | ------------------------------------- | ----------- |
| POST   | `/api/resources`                      | Create resource (body includes `scope_type`, `scope_id`) |
| GET    | `/api/resources/:id`                  | Get single resource |
| PATCH  | `/api/resources/:id`                  | Update resource |
| DELETE | `/api/resources/:id`                  | Delete resource |
| GET    | `/api/orgs/:slug/resources`           | Org-level resources |
| GET    | `/api/projects/:projectId/resources`  | Project-level resources |
| GET    | `/api/pods/:podId/resources`          | Pod resources (includes inherited) |
| GET    | `/api/pods/:podId/resources?scope=all`| Pod + project + org unified view (also `scope=pod\|project\|org`) |
| POST   | `/api/resources/:id/publish`          | Publish resource to public marketplace (requires `is_publisher`) |
| DELETE | `/api/resources/:id/publish`          | **§8** Unpublish (the dashboard's publish toggle) |
| POST   | `/api/resources/:id/star`             | Star a resource |
| DELETE | `/api/resources/:id/star`             | Unstar a resource |
| POST   | `/api/resources/upload`               | Upload skill package file to S3 (presigned flow, §6) |
| POST   | `/api/resources/:id/import`           | **§8** "Add to my org": copy a public resource into `body.org_slug`; bumps source `installs_count` |

All resource list endpoints accept `?q=&type=&tag=&sort=updated|newest|stars|installs`
and return resources enriched with:

```json
{ "scope_label": "ORG", "author": { …User }, "starred_by_me": true }
```

### 3.6 Public Marketplace

| Method | Endpoint                                   | Description |
| ------ | ------------------------------------------ | ----------- |
| GET    | `/api/public/resources`                    | Browse public resources (no auth) |
| GET    | `/api/public/resources/:id`                | Get public resource detail |
| GET    | `/api/public/publishers/:username`         | Publisher profile + their resources |
| GET    | `/api/public/search?q=...&type=...&tag=...`| Search public resources |

### 3.7 Feature Flags & Licensing (§8 addition)

| Method | Endpoint                          | Description |
| ------ | --------------------------------- | ----------- |
| GET    | `/api/orgs/:slug/features`        | Resolved flags for the org: `[{ key, name, description, premium, default_enabled, enabled, licensed }]` |
| PATCH  | `/api/orgs/:slug/features/:key`   | Toggle a flag for the org (admin only; `403` if premium and unlicensed) — body `{ "enabled": bool }` |
| POST   | `/api/orgs/:slug/license`         | Activate a premium license (admin only) — body `{ "license_key": "…" }`; returns `{ plan, features }` |

License keys are issued out-of-band (sales / self-serve later). The mock
accepts the demo format `T41-PREM-XXXX`; the real service validates against
the `licenses` table and sets `org.plan = PREMIUM`. v1 has no expiry
enforcement (the column exists for later).

### 3.8 Profiles (§8 addition — GitHub-style profile page)

| Method | Endpoint                            | Description |
| ------ | ----------------------------------- | ----------- |
| GET    | `/api/users/:username`              | Profile + `stats { resources, public_resources, stars_received, stars_given, orgs }` |
| GET    | `/api/users/:username/resources`    | Resources authored by the user (visibility-filtered for the caller) |
| GET    | `/api/users/:username/starred`      | Resources the user starred |
| GET    | `/api/users/:username/activity`     | The user's recent activity (≤20) |
| GET    | `/api/users/:username/orgs`         | Orgs the user belongs to (respecting `is_public` for non-self callers) |

---

## 4. Authentication & Authorization

### 4.1 JWT Strategy

- Access token: 15 min expiry, signed with RS256.
- Refresh token: 7 days, stored in HttpOnly cookie.
- Token rotation on each refresh.
- The client sends `Authorization: Bearer <access_token>` and
  `credentials: "include"` for the refresh cookie
  (see `client/src/lib/api/http.ts`).

### 4.2 Permission Model

Every API route enforces scope-based access:

- Org resource: user must be an org member.
- Project resource: user must be a project member (or org admin).
- Pod resource: user must be a pod member (or project lead / org admin).
- Public resource GET routes: no auth required.
- Mutations on a resource additionally require author or scope-admin.
- `POST /api/resources/:id/publish` requires the caller's `is_publisher = true`
  (the dashboard surfaces the 403 message verbatim).

### 4.3 Rate Limiting

- Auth endpoints: 10 requests/minute per IP.
- Write endpoints: 60 requests/minute per user.
- Public search: 30 requests/minute per IP.

---

## 5. Resource Inheritance Logic

When fetching resources for a pod with `scope=all`, the API performs a union query:

```sql
SELECT * FROM resources WHERE
  (scope_type = 'POD' AND scope_id = :podId)
  OR (scope_type = 'PROJECT' AND scope_id = :projectId)
  OR (scope_type = 'ORG' AND scope_id = :orgId)
ORDER BY scope_type, created_at DESC
```

The response includes a `scope_label` field on each resource so the frontend
can display Org / Project / Pod origin badges. (The dashboard's pod screen
renders inherited resources read-only based on `scope_label`.)

If a pod has a resource with the same title as a project-level one, the
pod-level resource takes precedence in the UI (override logic handled
client-side in v1).

---

## 6. File Uploads

Two flows, sharing a **switchable storage backend** (`STORAGE_BACKEND=local|s3`,
see `app/storage.py`):

**Direct multipart upload — `POST /api/uploads`** (images, video, diagrams,
files; powers resource attachments and skill packages):
- `multipart/form-data` with `file` + `kind` (`image|video|file`; diagrams use
  `image`). Validated by extension per kind and `MAX_UPLOAD_MB`.
- Returns `{ file_url, filename, content_type, size_bytes }`.
- **local** backend: bytes written under `UPLOAD_DIR`, served from the
  `/uploads/<key>` static mount; `file_url = PUBLIC_BASE_URL/uploads/<key>`.
- **s3** backend: `boto3 put_object` to `S3_BUCKET` (AWS S3 / Cloudflare R2 /
  MinIO); `file_url = S3_PUBLIC_BASE_URL/<key>`.
- Client: `api.uploadFile(file, kind)`. In mock mode it returns a local
  object URL so previews work with no backend.

**Presigned PUT — `POST /api/resources/upload`** (legacy skill-package path):
backend issues a presigned PUT URL when S3 is configured; the client PUTs the
file directly and stores the returned `file_url`. Returns a placeholder URL
when storage is unconfigured.

`file_url` is stored on the resource (skill package) or on each attachment item
(`attachments[].url`). Production: set `STORAGE_BACKEND=s3` + bucket creds; for
very large media, prefer the presigned flow to avoid proxying bytes through the API.

---

## 7. Error Response Format

All errors follow a consistent envelope:

```json
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "Resource with id X not found", "status": 404 } }
```

Standard error codes: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`,
`VALIDATION_ERROR`, `CONFLICT`, `INTERNAL_ERROR`.

The client parses exactly this envelope (`isApiError` in
`client/src/lib/api/http.ts`) and shows `error.message` in toasts — write
human-readable messages.

---

## 8. Additions discovered while building the client

The dashboard was built first against a mock of this spec; these endpoints /
fields were needed in practice and are **part of the v1 contract** (each is
marked **§8** in the tables above):

1. **`GET /api/orgs`** — the sidebar org switcher needs "my orgs with my role".
2. **Invitations listing & cancel** — Org Settings shows pending invites with
   Resend / Cancel (spec §4.5 of the frontend doc requires it).
3. **`PATCH /api/orgs/:slug/members/:userId`** — role dropdown in the members table.
4. **`GET /api/orgs/:slug/activity`** + `activities` model — dashboard-home feed.
5. **`GET /api/orgs/:slug/search`** — the ⌘K command palette (one round-trip).
6. **`DELETE /api/resources/:id/publish`** — publish is a toggle in the UI.
7. **`POST /api/resources/:id/import`** — marketplace "Add to my org" copies the
   resource into the org scope and increments the source's `installs_count`.
8. **`PATCH /api/auth/me`** + `location`/`website` user fields + `username` —
   the GitHub-style profile page (edit profile, publisher toggle, vanity URL).
9. **Profile routes (§3.8)** — profile tabs: overview stats, authored
   resources, stars, activity, org chips.
10. **MCP structured fields** — `server_url` and `config_json` columns on
    resources; the drawer renders "copy server URL" / "copy config JSON".
11. **Enrichment fields** — list endpoints return `scope_label`, embedded
    `author`, and `starred_by_me` to avoid N+1 calls from the client.
12. **Counts** — project/pod list endpoints return `pods_count`,
    `members_count`, `resources_count` for the cards.
13. **Feature flags per org (§2.12, §3.7)** — admins enable/disable features
    for their organization; gated endpoints enforce server-side.
14. **Premium licensing** — `org.plan` tier + license activation; premium
    flags (`publishing`, `custom-terminology`) stay locked on the FREE plan.
15. **Org terminology** — `organizations.terminology` relabels
    Projects / Pods in the UI (e.g. pods read as "Teams"); the data model and
    API naming never change. Writes gated by the `custom-terminology` flag.

---

## 9. Attach contract (how the client connects)

1. Implement this spec (the mock at `client/src/lib/mock/handlers.ts` is the
   executable reference — route for route, including error envelopes).
2. Serve under a base URL, CORS-allowing the dashboard origin with credentials.
3. Set in the client:

   ```bash
   NEXT_PUBLIC_API_URL=https://api.skillshare.think41.com
   ```

4. Done. `client/src/lib/api/http.ts` switches from the in-browser mock to
   network transport. Delete `client/src/lib/mock/` once stable.

**Definition of done for parity:** every function in
`client/src/lib/api/index.ts` returns the shapes in `client/src/lib/types.ts`
against the real backend, and the dashboard works with mock mode disabled.

---

## 10. Integrations — Personal Access Tokens, CLI & MCP server

The registry is usable outside the dashboard via two first-party clients in
[`integration/`](./integration): a **CLI** (`skillshare`, for humans and CI)
and an **MCP server** (`skillshare-mcp`, for AI agents — Claude Code,
Claude Desktop, any MCP client). Both are thin wrappers over the §3 API;
**all permissions (§4.2) and feature flags (§2.12) are enforced
server-side**, never in the clients.

### 10.1 Personal Access Tokens (PATs)

Browser sessions use 15-minute JWTs + refresh cookies (§4.1) — unusable for
headless clients. PATs are the integration credential:

```
api_tokens { id, user_id, name, token_prefix, token_hash, created_at,
             last_used_at, expires_at?, revoked }
```

- Format `skst_<random>`; shown **once** at mint time; only the SHA-256
  hash is stored. `token_prefix` (first 12 chars) supports display/list.
- Sent on the same header as JWTs: `Authorization: Bearer skst_…` — the
  auth layer branches on the `skst_` prefix (`app/security.py`).
- Optional `expires_days` (1–365); `last_used_at` updated on every use.
- Endpoints: `POST/GET /api/auth/tokens`, `DELETE /api/auth/tokens/:id`
  (see §3.1). Revocation is immediate.
- Rate limits (§4.3) apply per token-holder like any authenticated user.

### 10.2 CLI (`integration/cli`)

`skillshare login` exchanges email+password for a JWT, mints a PAT named
after the machine, and stores it in `~/.config/skillshare/credentials.json`
(0600). `logout` revokes server-side and deletes the file. Env overrides
`SKILLSHARE_API_URL` / `SKILLSHARE_TOKEN` make it CI-friendly. Commands:
`whoami · orgs · tokens · search · get · pull · list (--org|--pod, --scope)
· add note · star · publish · import`.

### 10.3 MCP server (`integration/mcp`)

Python `mcp` SDK (FastMCP), stdio transport, configured by env
(`SKILLSHARE_API_URL`, `SKILLSHARE_TOKEN`). Twelve tools: marketplace
search/detail/publisher (work unauthenticated), `whoami`, org/pod browsing
(incl. the §5 inheritance union and the ⌘K search), `create_note`,
`star_resource`, `import_resource`. Registered in Claude Code via
`claude mcp add skillshare --env … -- skillshare-mcp`.

### 10.4 Security notes

- A PAT is exactly as powerful as its user — no scopes in v1. Scoped tokens
  (read-only, single-org) are the natural v2 follow-up; the `api_tokens`
  table leaves room (add a `scopes` JSON column).
- Tokens never appear in logs; the API logs only `token_prefix`.
- Verified end-to-end by `scripts/smoke.py` (PAT section) and a live
  stdio MCP client exercise (all 12 tools).
