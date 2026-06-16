"""
Seed demo data — mirrors client/src/lib/mock/db.ts so the dashboard looks
identical whether it runs on the in-browser mock or this backend.

  .venv/bin/python -m scripts.seed          # idempotent: skips if users exist
  .venv/bin/python -m scripts.seed --reset  # drop + recreate + reseed

Every demo user's password is settings.seed_password (SEED_PASSWORD env,
default "skillshare-demo").
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")  # allow running as a script from backend/

from sqlalchemy import inspect, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Activity,
    BlogPost,
    ChangelogEntry,
    ContentPage,
    Invitation,
    Organization,
    OrgMember,
    Pod,
    PodMember,
    Project,
    ProjectMember,
    Resource,
    ResourceStar,
    User,
)
from app.security import hash_password  # noqa: E402

settings = get_settings()


def t(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def skill_md(name: str, body: str) -> str:
    slug = name.lower().replace(" ", "-")
    return (
        f"# {name}\n\n{body}\n\n## Usage\n\n```bash\nclaude skill add {slug}\n```\n\n"
        "## Inputs\n\n- `target` — what to operate on\n- `effort` — low | medium | high\n\n"
        "## Behavior\n\n1. Reads the target context.\n2. Applies the skill prompt with the configured effort.\n"
        "3. Returns a structured result with citations.\n"
    )


def seed(db) -> None:
    pw = hash_password(settings.seed_password)

    users = {
        "aniket": User(id="u-aniket", email="aniket.lnu@think41.com", password_hash=pw, username="aniket",
                       display_name="Aniket Kumar", bio="Full-stack engineer at Think41. Building SkillShare — the registry itself.",
                       location="Bengaluru, IN", website="https://think41.com", is_publisher=True, verified=True,
                       is_admin=True, created_at=t("2025-09-12")),
        "think41": User(id="u-think41", email="platform@think41.com", password_hash=pw, username="think41",
                        display_name="Think41", bio="The team behind SkillShare. Foundational skills and MCP servers, maintained and verified.",
                        is_publisher=True, verified=True, created_at=t("2025-06-01")),
        "ada": User(id="u-ada", email="ada@example.com", password_hash=pw, username="ada-rao",
                    display_name="Ada Rao", bio="Platform engineer. I build retrieval and code-review skills for fast-moving teams.",
                    is_publisher=True, verified=True, created_at=t("2025-07-15")),
        "nilesh": User(id="u-nilesh", email="nilesh@example.com", password_hash=pw, username="nilesh",
                       display_name="Nilesh Gupta", bio="Infra & observability. MCP servers that connect agents to real production systems.",
                       is_publisher=True, created_at=t("2026-01-10")),
        "mono": User(id="u-mono", email="hello@studiomono.dev", password_hash=pw, username="studio-mono",
                     display_name="Studio Mono", bio="A two-person studio shipping design-system and frontend skills for AI agents.",
                     is_publisher=True, verified=True, created_at=t("2025-08-02")),
        "priya": User(id="u-priya", email="priya@think41.com", password_hash=pw, username="priya",
                      display_name="Priya Sharma", bio="Product engineer, Atlas team.", created_at=t("2025-10-05")),
        "dev": User(id="u-dev", email="dev@think41.com", password_hash=pw, username="devraj",
                    display_name="Dev Raj", bio="Agent infrastructure, Forge team.", created_at=t("2025-11-21")),
    }
    db.add_all(users.values())

    db.add_all([
        Organization(id="org-think41", name="Think41", slug="think41",
                     description="AI-native product studio. Home of SkillShare.", owner_id="u-aniket",
                     plan="PREMIUM", terminology={"project": "Project", "pod": "Team"}, created_at=t("2025-09-12")),
        Organization(id="org-mono", name="Studio Mono", slug="studio-mono",
                     description="Design-system and frontend skills for AI agents.", owner_id="u-mono",
                     plan="FREE", created_at=t("2025-08-02")),
    ])

    db.add_all([
        OrgMember(org_id="org-think41", user_id="u-aniket", role="ADMIN", last_active=t("2026-06-05")),
        OrgMember(org_id="org-think41", user_id="u-priya", role="MEMBER", last_active=t("2026-06-04")),
        OrgMember(org_id="org-think41", user_id="u-dev", role="MEMBER", last_active=t("2026-06-03")),
        OrgMember(org_id="org-think41", user_id="u-think41", role="ADMIN", last_active=t("2026-06-01")),
        OrgMember(org_id="org-mono", user_id="u-mono", role="ADMIN", last_active=t("2026-06-02")),
        OrgMember(org_id="org-mono", user_id="u-aniket", role="MEMBER", last_active=t("2026-06-05")),
    ])

    db.add_all([
        Project(id="proj-atlas", org_id="org-think41", name="Atlas — Customer Platform",
                description="The customer-facing platform: retrieval, dashboards, and the public API.",
                tags=["platform", "rag", "api"], created_by="u-aniket", created_at=t("2025-10-01")),
        Project(id="proj-forge", org_id="org-think41", name="Forge — Internal Tooling",
                description="Agent infrastructure, CI skills, and the internal developer platform.",
                tags=["devex", "agents", "ci"], created_by="u-dev", created_at=t("2025-11-15")),
        Project(id="proj-mono-ds", org_id="org-mono", name="Mono Design System",
                description="Token pipelines and component generation skills.",
                tags=["design", "frontend"], created_by="u-mono", created_at=t("2025-09-01")),
    ])

    db.add_all([
        ProjectMember(project_id="proj-atlas", user_id="u-aniket", role="LEAD"),
        ProjectMember(project_id="proj-atlas", user_id="u-priya", role="MEMBER"),
        ProjectMember(project_id="proj-forge", user_id="u-dev", role="LEAD"),
        ProjectMember(project_id="proj-forge", user_id="u-aniket", role="MEMBER"),
        ProjectMember(project_id="proj-mono-ds", user_id="u-mono", role="LEAD"),
        ProjectMember(project_id="proj-mono-ds", user_id="u-aniket", role="MEMBER"),
    ])

    db.add_all([
        Pod(id="pod-retrieval", project_id="proj-atlas", name="Retrieval Pod",
            description="Owns search, embeddings, and answer quality across Atlas.",
            purpose_tag="rag", created_by="u-aniket", created_at=t("2025-10-08")),
        Pod(id="pod-frontend", project_id="proj-atlas", name="Frontend Pod",
            description="Dashboards, design system, and the component pipeline.",
            purpose_tag="frontend", created_by="u-priya", created_at=t("2025-10-20")),
        Pod(id="pod-dx", project_id="proj-forge", name="DX Pod",
            description="Developer experience: CI skills, release automation, agent tooling.",
            purpose_tag="devex", created_by="u-dev", created_at=t("2025-11-20")),
        Pod(id="pod-tokens", project_id="proj-mono-ds", name="Tokens Pod",
            description="Design-token extraction and validation.",
            purpose_tag="design", created_by="u-mono", created_at=t("2025-09-10")),
    ])

    db.add_all([
        PodMember(pod_id="pod-retrieval", user_id="u-aniket", role="OWNER"),
        PodMember(pod_id="pod-retrieval", user_id="u-priya", role="MEMBER"),
        PodMember(pod_id="pod-frontend", user_id="u-priya", role="OWNER"),
        PodMember(pod_id="pod-frontend", user_id="u-aniket", role="MEMBER"),
        PodMember(pod_id="pod-dx", user_id="u-dev", role="OWNER"),
        PodMember(pod_id="pod-dx", user_id="u-aniket", role="MEMBER"),
        PodMember(pod_id="pod-tokens", user_id="u-mono", role="OWNER"),
    ])

    cdn = "https://cdn.skillshare.think41.com/packages"
    resources = [
        Resource(id="pr-reviewer", type="SKILL", title="PR Reviewer",
                 description="A reviewing skill that reads a diff and surfaces correctness bugs alongside reuse and simplification cleanups. Tunable by effort level, it leaves inline comments and a summary verdict. Built for teams that want consistent, high-signal reviews without a human on every PR.",
                 content_md=skill_md("PR Reviewer", "Reviews pull requests for correctness, reuse, and simplification."),
                 file_url=f"{cdn}/pr-reviewer-2.4.1.skill", version="2.4.1",
                 tags=["code-review", "github", "quality"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-ada", is_public=True, stars_count=921, installs_count=12840,
                 created_at=t("2025-11-02"), updated_at=t("2026-05-20")),
        Resource(id="postgres-mcp", type="MCP", title="Postgres MCP",
                 description="An MCP server that exposes a Postgres database to your agents with a read-only safety boundary, schema introspection, and query timeouts. Connection strings stay server-side; agents get structured results, never raw credentials.",
                 content_md="Read-only Postgres access for agents — schema-aware, query-safe.",
                 server_url="https://mcp.nilesh.dev/postgres",
                 config_json='{\n  "mcpServers": {\n    "postgres": {\n      "url": "https://mcp.nilesh.dev/postgres",\n      "transport": "http",\n      "scopes": ["read"]\n    }\n  }\n}',
                 version="1.8.0", tags=["database", "postgres", "infra"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-nilesh", is_public=True, stars_count=654, installs_count=8120,
                 created_at=t("2026-01-18"), updated_at=t("2026-05-24")),
        Resource(id="design-system-kit", type="SKILL", title="Design System Kit",
                 description="Feed it your design tokens and this skill produces accessible, on-brand React components with motion and dark-mode baked in. It enforces your spacing scale and type ramp so generated UI never drifts from the system.",
                 content_md=skill_md("Design System Kit", "Generate on-brand React components from a token file."),
                 file_url=f"{cdn}/design-system-kit-3.1.2.skill", version="3.1.2",
                 tags=["frontend", "react", "design"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-mono", is_public=True, stars_count=510, installs_count=6450,
                 created_at=t("2025-10-12"), updated_at=t("2026-05-18")),
        Resource(id="incident-runbook", type="NOTE", title="Incident Runbook",
                 description="A structured note capturing how the team runs incidents — severity definitions, the comms cadence, escalation contacts, and post-mortem template. Shared at the org level so every pod inherits the same playbook automatically.",
                 content_md="# Incident Runbook\n\nThe on-call playbook: severities, comms, and escalation paths.\n\n## Severities\n\n- **SEV1** — customer-facing outage. Page the on-call lead immediately.\n- **SEV2** — degraded service, no data loss. Respond within 30 minutes.\n- **SEV3** — internal tooling broken. Next business day.\n\n## Comms cadence\n\n1. Open an incident channel: `#inc-YYYYMMDD-short-name`.\n2. Post a status update every 30 minutes, even if it's \"still digging\".\n3. When resolved, schedule the post-mortem within 48 hours.\n\n> Blameless by default. The system failed, not the person.\n",
                 version="1.2.0", tags=["sre", "process", "on-call"], scope_type="ORG", scope_id="org-think41",
                 attachments=[
                     {"kind": "video", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                      "title": "Incident response walkthrough", "caption": "15-min screen recording of a SEV2 drill."},
                     {"kind": "link", "url": "https://www.atlassian.com/incident-management/handbook",
                      "title": "Atlassian Incident Handbook", "caption": "Reference we based our severities on."},
                     {"kind": "file", "url": "https://cdn.skillshare.think41.com/docs/postmortem-template.md",
                      "title": "postmortem-template.md", "caption": None},
                 ],
                 author_id="u-think41", is_public=True, stars_count=388, installs_count=4300,
                 created_at=t("2025-12-01"), updated_at=t("2026-05-11")),
        Resource(id="semantic-search", type="SKILL", title="Semantic Search",
                 description="A retrieval skill that chunks documents, builds embeddings, and answers questions with citations. Pluggable vector store, re-ranking, and an evaluation harness so you can measure retrieval quality before you ship.",
                 content_md=skill_md("Semantic Search", "Embed, index, and retrieve across your team's knowledge."),
                 file_url=f"{cdn}/semantic-search-2.0.6.skill", version="2.0.6",
                 tags=["rag", "search", "embeddings"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-ada", is_public=True, stars_count=742, installs_count=9870,
                 created_at=t("2025-11-20"), updated_at=t("2026-05-22")),
        Resource(id="slack-mcp", type="MCP", title="Slack MCP",
                 description="An MCP server bridging agents to Slack. Scope it to specific channels, control read vs. write, and keep tokens server-side. Useful for status updates, triage bots, and digest generation.",
                 content_md="Let agents read channels and post with scoped permissions.",
                 server_url="https://mcp.nilesh.dev/slack",
                 config_json='{\n  "mcpServers": {\n    "slack": {\n      "url": "https://mcp.nilesh.dev/slack",\n      "transport": "http",\n      "channels": ["#eng", "#status"]\n    }\n  }\n}',
                 version="1.4.3", tags=["slack", "messaging", "infra"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-nilesh", is_public=True, stars_count=421, installs_count=5610,
                 created_at=t("2026-02-05"), updated_at=t("2026-05-25")),
        Resource(id="changelog-writer", type="SKILL", title="Changelog Writer",
                 description="Reads merged pull requests over a range and writes a human changelog grouped by feature, fix, and chore. Pairs well with PR Reviewer for an end-to-end release flow.",
                 content_md=skill_md("Changelog Writer", "Turn merged PRs into a clean, grouped changelog."),
                 file_url=f"{cdn}/changelog-writer-1.1.0.skill", version="1.1.0",
                 tags=["release", "docs", "github"], scope_type="PUBLIC", scope_id=None,
                 author_id="u-mono", is_public=True, stars_count=277, installs_count=3920,
                 created_at=t("2026-01-05"), updated_at=t("2026-05-09")),
        Resource(id="brand-voice", type="NOTE", title="Brand Voice",
                 description="A note defining how the company writes — voice, tone, banned phrases, and worked examples. Inherited org-wide so every skill that generates copy stays on-brand.",
                 content_md="# Brand Voice\n\nTone, do's and don'ts, and example copy for the whole org.\n\n## Voice\n\nConfident, concrete, a little playful. We explain like a sharp colleague, not a brochure.\n\n## Don'ts\n\n- No \"unleash\", \"supercharge\", \"revolutionize\".\n- No exclamation marks in product UI.\n- Never promise what the roadmap hasn't shipped.\n\n## Worked example\n\n**Before:** \"Unleash the power of AI skills!!\"\n**After:** \"Define a skill once. Every pod inherits it.\"\n",
                 version="1.0.4", tags=["content", "brand", "writing"], scope_type="ORG", scope_id="org-think41",
                 author_id="u-think41", is_public=True, stars_count=196, installs_count=2880,
                 created_at=t("2025-12-15"), updated_at=t("2026-05-06")),
        # --- internal resources ---
        Resource(id="res-handbook", type="NOTE", title="Engineering Handbook",
                 description="How we ship at Think41 — branching, reviews, release trains, and the definition of done.",
                 content_md="# Engineering Handbook\n\n## Branching\n\nTrunk-based. Short-lived feature branches, squash merges, no long-running release branches.\n\n## Reviews\n\nEvery PR gets one human review **or** a PR Reviewer skill pass at `effort=high`. SEV-touching code always gets both.\n\n## Definition of done\n\n- Tests pass.\n- Docs updated.\n- Feature flagged if user-facing.\n",
                 version="2.1.0", tags=["process", "engineering"], scope_type="ORG", scope_id="org-think41",
                 author_id="u-aniket", stars_count=14, created_at=t("2025-10-02"), updated_at=t("2026-05-28")),
        Resource(id="res-github-mcp", type="MCP", title="GitHub MCP",
                 description="Org-wide GitHub access for agents: issues, PRs, and checks. Tokens stay server-side.",
                 content_md="Connect agents to the Think41 GitHub org.",
                 server_url="https://mcp.internal.think41.com/github",
                 config_json='{\n  "mcpServers": {\n    "github": {\n      "url": "https://mcp.internal.think41.com/github",\n      "transport": "http",\n      "org": "think41"\n    }\n  }\n}',
                 version="1.3.0", tags=["github", "infra"], scope_type="ORG", scope_id="org-think41",
                 author_id="u-dev", stars_count=9, created_at=t("2025-11-25"), updated_at=t("2026-05-15")),
        Resource(id="res-atlas-conventions", type="NOTE", title="Atlas API Conventions",
                 description="REST conventions for the Atlas public API — naming, pagination, errors, and versioning.",
                 content_md="# Atlas API Conventions\n\n## Naming\n\nPlural nouns, kebab-case paths, camelCase JSON.\n\n## Pagination\n\nCursor-based: `?cursor=...&limit=50`. Responses carry `next_cursor`.\n\n## Errors\n\nSame envelope as SkillShare: `{ \"error\": { \"code\", \"message\", \"status\" } }`.\n",
                 version="1.4.0", tags=["api", "conventions"], scope_type="PROJECT", scope_id="proj-atlas",
                 author_id="u-aniket", stars_count=7, created_at=t("2025-10-15"), updated_at=t("2026-05-20")),
        Resource(id="res-atlas-pg", type="MCP", title="Atlas Postgres MCP",
                 description="Read-only access to the Atlas staging database for retrieval experiments.",
                 content_md="Staging-only. Production access is never exposed to agents.",
                 server_url="https://mcp.internal.think41.com/atlas-pg",
                 config_json='{\n  "mcpServers": {\n    "atlas-pg": {\n      "url": "https://mcp.internal.think41.com/atlas-pg",\n      "transport": "http",\n      "database": "atlas_staging"\n    }\n  }\n}',
                 version="0.9.2", tags=["postgres", "staging"], scope_type="PROJECT", scope_id="proj-atlas",
                 author_id="u-priya", stars_count=4, created_at=t("2026-01-08"), updated_at=t("2026-05-30")),
        Resource(id="res-eval-harness", type="SKILL", title="Retrieval Eval Harness",
                 description="Scores retrieval quality against the golden question set before every index change ships.",
                 content_md=skill_md("Retrieval Eval Harness", "Run the golden-set evaluation and report precision/recall deltas."),
                 file_url=f"{cdn}/retrieval-eval-harness-0.6.0.skill", version="0.6.0",
                 tags=["rag", "evals", "quality"], scope_type="POD", scope_id="pod-retrieval",
                 author_id="u-aniket", stars_count=6, created_at=t("2026-02-12"), updated_at=t("2026-06-01")),
        Resource(id="res-chunking", type="NOTE", title="Chunking Strategies",
                 description="What we learned shipping three chunkers: heading-aware beats fixed-size, tables need their own path.",
                 content_md="# Chunking Strategies\n\n## TL;DR\n\nHeading-aware chunking with 15% overlap won on every metric. Fixed-size 512 is the floor, not the default.\n\n## Tables\n\nExtract tables separately and embed a generated natural-language summary alongside the raw cells.\n",
                 version="1.1.0", tags=["rag", "embeddings"], scope_type="POD", scope_id="pod-retrieval",
                 author_id="u-priya", stars_count=5, created_at=t("2026-03-02"), updated_at=t("2026-05-26")),
        Resource(id="res-component-gen", type="SKILL", title="Component Generator",
                 description="Generates Atlas dashboard components from our token file — wraps the public Design System Kit with house rules.",
                 content_md=skill_md("Component Generator", "On-brand Atlas components from design tokens."),
                 version="0.3.1", tags=["frontend", "design"], scope_type="POD", scope_id="pod-frontend",
                 author_id="u-priya", stars_count=3, created_at=t("2026-03-20"), updated_at=t("2026-05-22")),
        Resource(id="res-release-skill", type="SKILL", title="Release Train Conductor",
                 description="Cuts the weekly release: changelog, tags, deploy checklist, and the announcement draft.",
                 content_md=skill_md("Release Train Conductor", "Automate the weekly release train end to end."),
                 version="1.0.0", tags=["release", "ci"], scope_type="POD", scope_id="pod-dx",
                 author_id="u-dev", stars_count=8, created_at=t("2026-01-30"), updated_at=t("2026-06-02")),
        Resource(id="res-mono-tokens", type="SKILL", title="Token Extractor",
                 description="Pulls design tokens out of Figma files and validates them against the schema.",
                 content_md=skill_md("Token Extractor", "Figma → tokens.json, validated."),
                 version="2.2.0", tags=["design", "figma"], scope_type="POD", scope_id="pod-tokens",
                 author_id="u-mono", stars_count=2, created_at=t("2025-09-15"), updated_at=t("2026-05-10")),
    ]
    db.add_all(resources)

    db.add_all([
        ResourceStar(resource_id="pr-reviewer", user_id="u-aniket"),
        ResourceStar(resource_id="semantic-search", user_id="u-aniket"),
        ResourceStar(resource_id="incident-runbook", user_id="u-aniket"),
        ResourceStar(resource_id="postgres-mcp", user_id="u-priya"),
    ])

    db.add_all([
        Activity(user_id="u-aniket", org_id="org-think41", verb="updated", object_type="resource",
                 object_id="res-eval-harness", object_title="Retrieval Eval Harness", meta="v0.6.0",
                 created_at=t("2026-06-01T10:24:00")),
        Activity(user_id="u-dev", org_id="org-think41", verb="updated", object_type="resource",
                 object_id="res-release-skill", object_title="Release Train Conductor", meta="v1.0.0",
                 created_at=t("2026-06-02T08:00:00")),
        Activity(user_id="u-priya", org_id="org-think41", verb="updated", object_type="resource",
                 object_id="res-atlas-pg", object_title="Atlas Postgres MCP", created_at=t("2026-05-30T15:40:00")),
        Activity(user_id="u-aniket", org_id="org-think41", verb="updated", object_type="resource",
                 object_id="res-handbook", object_title="Engineering Handbook", meta="v2.1.0",
                 created_at=t("2026-05-28T09:12:00")),
        Activity(user_id="u-priya", org_id="org-think41", verb="created", object_type="resource",
                 object_id="res-component-gen", object_title="Component Generator", created_at=t("2026-03-20T11:00:00")),
        Activity(user_id="u-aniket", org_id="org-think41", verb="starred", object_type="resource",
                 object_id="incident-runbook", object_title="Incident Runbook", created_at=t("2026-05-12T13:30:00")),
        Activity(user_id="u-think41", org_id="org-think41", verb="published", object_type="resource",
                 object_id="brand-voice", object_title="Brand Voice", created_at=t("2026-05-06T10:00:00")),
    ])

    db.add(Invitation(org_id="org-think41", email="maya@think41.com", role="MEMBER",
                      token="tok-maya-1", expires_at=t("2026-06-20")))

    db.commit()


def seed_content(db) -> None:
    """Marketing content: blog posts, changelog, legal pages. Mirrors what the
    website previously hardcoded (website/src/lib/blog.ts and the privacy/terms
    pages). Idempotent per-item, so it tops up an already-seeded DB without a
    wipe — letting the new content tables fill in for existing local databases."""

    posts = [
        BlogPost(
            slug="proactive-notifications", status="published", featured=True,
            title="Your team's new skills now find you", date="2026-06-12", tag="Feature",
            reading_minutes=4, author_name="Ada Rao", author_role="Product, SkillShare",
            excerpt="Notifications land the moment a skill, MCP server, or note is published in a scope you belong to — in the dashboard, the CLI, and right inside your AI agent.",
            standfirst="Discovery shouldn't depend on someone remembering to Slack you a link.",
            body=[
                {"type": "p", "text": "The hardest part of a shared registry was never publishing — it was discovery. Someone on your pod ships a brilliant pr-reviewer skill and you find out three weeks later, by accident. We fixed that."},
                {"type": "h2", "text": "Scoped to what you can actually see"},
                {"type": "p", "text": "When a resource is added or published in a scope you belong to, you get a notification. Membership decides the reach: your org, your projects, and your pods — never anything outside what you already have access to. You're never notified about your own actions."},
                {"type": "ul", "items": [
                    "Dashboard: a bell with an unread count and one-click deep links.",
                    "CLI: `skillshare inbox` — newest first, with a ready-to-run install command.",
                    "MCP: your agent calls `check_updates` at the start of a conversation and tells you what's new before you ask.",
                ]},
                {"type": "quote", "text": "The point is that the registry comes to you. You should hear about a new team MCP from your own agent, not from a forwarded message."},
                {"type": "h2", "text": "Install in one step"},
                {"type": "p", "text": "Every notification carries an install command and a link straight to the resource. See it, run it, done — whether you live in the dashboard, the terminal, or an AI agent."},
            ],
        ),
        BlogPost(
            slug="contribute-back-local-scan", status="published", featured=True,
            title="Push the skills you already have", date="2026-06-12", tag="Feature",
            reading_minutes=5, author_name="Ada Rao", author_role="Product, SkillShare",
            excerpt="Scan your machine for local skills, MCP servers, and notes that aren't on the platform yet — preview them with secrets redacted, then push with one approval.",
            standfirst="The best skills are the ones already sitting in your dotfiles.",
            body=[
                {"type": "p", "text": "Most teams already have great skills — they're just trapped in someone's local Claude Code config, a Cursor setup, or a CLAUDE.md no one else has read. Contribute-back surfaces them."},
                {"type": "h2", "text": "Detect, redact, preview, push"},
                {"type": "ul", "items": [
                    "Detectors read Claude Code (primary), Cursor, Codex, and Claude Desktop — pluggable, so more sources slot in over time.",
                    "Secrets are redacted before anything leaves your machine. API keys, tokens, and credentials in MCP configs never get uploaded.",
                    "You see a full redacted preview, and nothing is pushed without your explicit approval.",
                    "Dismiss something once and it stays dismissed — synced to your account, so it won't nag you on another machine.",
                ]},
                {"type": "quote", "text": "Never auto-upload. MCP configs are full of credentials — the redact-and-preview step is non-negotiable, and it's enforced server-side too."},
                {"type": "h2", "text": "Works from the CLI and your agent"},
                {"type": "p", "text": "Run `skillshare scan` to list candidates and `skillshare push --org <slug>` to contribute them. Or just mention a local skill to your AI agent — it can scan, draft the title and description from the redacted content, show you the preview, and push once you say yes."},
            ],
        ),
        BlogPost(
            slug="org-inheritance", status="published",
            title="Define a skill once, inherit it everywhere", date="2026-05-12", tag="Guide",
            reading_minutes=3, author_name="Marco Reyes", author_role="Engineering, SkillShare",
            excerpt="Org → project → pod inheritance means you maintain a resource in one place and every team below it gets the update automatically. Here's the mental model.",
            body=[
                {"type": "p", "text": "Copy-paste is how skill libraries rot. A resource gets duplicated into five pods, one of them fixes a bug, and now you have five subtly different versions. Inheritance is the cure."},
                {"type": "h2", "text": "Three levels, one source of truth"},
                {"type": "ul", "items": [
                    "Org — the root. Define a resource here and everyone inherits it.",
                    "Project — a body of work that groups related pods.",
                    "Pod — a team. Inherits everything above it and adds its own.",
                ]},
                {"type": "p", "text": "Resolve a pod's library and you get its own resources plus everything inherited from its project and org — deduplicated, always current. Update the org-level definition and the change flows downward with no manual sync."},
            ],
        ),
        BlogPost(
            slug="why-a-registry", status="published",
            title="Why your AI team needs a registry, not a folder", date="2026-04-22", tag="Story",
            reading_minutes=4, author_name="Ada Rao", author_role="Product, SkillShare",
            excerpt="Skills, MCP servers, and notes are real artifacts with versions, owners, and permissions. Treating them like loose files is why they drift. A registry treats them like what they are.",
            body=[
                {"type": "p", "text": "When AI tooling was a novelty, a shared folder of prompts was fine. It isn't anymore. Your skills encode how your team works, your MCP servers hold real credentials, and your notes are institutional memory."},
                {"type": "h2", "text": "What a registry gives you that a folder can't"},
                {"type": "ul", "items": [
                    "Versions and provenance — who published what, and when.",
                    "Permissions scoped to org, project, and pod membership.",
                    "Discovery that comes to you, instead of tribal knowledge.",
                    "One vocabulary across the dashboard, CLI, MCP, and marketplace.",
                ]},
                {"type": "p", "text": "That last point matters most: the website, dashboard, CLI, and MCP all speak the same model. A skill is the same object everywhere you touch it. That's the difference between a tool you check and infrastructure your team relies on."},
            ],
        ),
    ]
    for p in posts:
        if not db.query(BlogPost.id).filter(BlogPost.slug == p.slug).first():
            db.add(p)

    changelog = [
        ChangelogEntry(date="2026-06-12", tag="Feature", title="Notifications + contribute-back",
                       body="Get notified when team resources are published, and push your local skills/MCP/notes back to the platform — secrets redacted, preview first."),
        ChangelogEntry(date="2026-05-27", tag="Release", title="Public marketplace is live",
                       body="Browse every public skill, MCP server, and note without an account. Generated share cards included."),
        ChangelogEntry(date="2026-05-12", tag="Feature", title="Org-level inheritance",
                       body="Define a resource once at the org level and every project and pod inherits it automatically."),
        ChangelogEntry(date="2026-04-30", tag="Feature", title="Think41-verified publishers",
                       body="Verified makers now get a badge across the marketplace and their profile."),
    ]
    for c in changelog:
        exists = db.query(ChangelogEntry.id).filter(
            ChangelogEntry.date == c.date, ChangelogEntry.title == c.title
        ).first()
        if not exists:
            db.add(c)

    pages = [
        ContentPage(
            key="privacy", status="published", kicker="Legal", title="Privacy Policy",
            updated_label="June 15, 2026",
            intro="Plain-language summary of what we collect and how we protect it. SkillShare is v1 — this policy will grow with the product.",
            sections=[
                {"heading": "Who we are", "paragraphs": [
                    "SkillShare is a skill and MCP registry operated by Think41. This policy explains what data we collect when you use the dashboard, CLI, MCP server, and public marketplace, and what we do with it.",
                ]},
                {"heading": "What we collect", "bullets": [
                    "Account data — your name, email, and the organizations, projects, and pods you belong to.",
                    "Content you publish — skills, MCP server configurations, notes, and their metadata.",
                    "Usage data — installs, stars, and activity needed to power notifications and discovery.",
                    "Authentication — Personal Access Tokens you mint for the CLI and MCP, stored hashed.",
                ]},
                {"heading": "Secrets are redacted before they leave your machine", "paragraphs": [
                    "When you contribute a local skill, MCP server, or note through the CLI or MCP, we detect and redact secrets — API keys, tokens, and credentials — before anything is uploaded. You always see a redacted preview, and nothing is pushed without your explicit approval.",
                    "Redaction is enforced again server-side, so a credential that slips past the client is never stored.",
                ]},
                {"heading": "How we use your data", "bullets": [
                    "To operate the registry and resolve what you can see based on your membership.",
                    "To notify you when resources are added or published in scopes you belong to.",
                    "To show installs, stars, and verified-publisher status on the public marketplace.",
                    "To keep the service secure and debug problems.",
                ]},
                {"heading": "What we don't do", "paragraphs": [
                    "We don't sell your data. We don't use the private contents of your org's resources to train models. Public marketplace listings are, by design, public.",
                ]},
                {"heading": "Your choices", "bullets": [
                    "Revoke a Personal Access Token at any time from the dashboard or with `skillshare logout`.",
                    "Dismiss contribution recommendations — your choice is remembered and synced to your account.",
                    "Request export or deletion of your account data by contacting us.",
                ]},
                {"heading": "Changes", "paragraphs": [
                    "We may update this policy as the product evolves. Material changes will be noted on this page, and the “last updated” date above will change.",
                ]},
            ],
        ),
        ContentPage(
            key="terms", status="published", kicker="Legal", title="Terms of Service",
            updated_label="June 15, 2026",
            intro="The ground rules for using SkillShare. Free in v1, with sensible limits on publishing and acceptable use.",
            sections=[
                {"heading": "Acceptance", "paragraphs": [
                    "By creating an account or using SkillShare — the dashboard, CLI, MCP server, or public marketplace — you agree to these terms. If you're using SkillShare for an organization, you agree on its behalf.",
                ]},
                {"heading": "The service", "paragraphs": [
                    "SkillShare is a registry for AI skills, MCP servers, and team knowledge, operated by Think41. It is free in v1. Paid Team and Enterprise plans are planned for future versions; pricing and terms for those will be published before they launch.",
                ]},
                {"heading": "Your content", "bullets": [
                    "You keep ownership of the skills, MCP configs, and notes you publish.",
                    "By publishing to the public marketplace, you grant others the right to view, install, and import that resource.",
                    "You're responsible for having the rights to publish what you upload, and for not including secrets or third-party confidential data.",
                ]},
                {"heading": "Acceptable use", "bullets": [
                    "Don't upload malware, or skills/MCP servers designed to exfiltrate data or cause harm.",
                    "Don't violate others' intellectual property or privacy.",
                    "Don't abuse the API, attempt to bypass permission scopes, or disrupt the service.",
                    "Don't misrepresent authorship or impersonate a verified publisher.",
                ]},
                {"heading": "Verified publishers", "paragraphs": [
                    "Think41-verified status is granted at our discretion and may be revoked if these terms are violated. Verification signals identity, not an endorsement of every resource a publisher ships.",
                ]},
                {"heading": "Disclaimer & liability", "paragraphs": [
                    "SkillShare is provided “as is,” without warranties of any kind. Resources on the marketplace are published by their authors — review them before installing. To the extent permitted by law, Think41 is not liable for indirect or consequential damages arising from use of the service.",
                ]},
                {"heading": "Termination", "paragraphs": [
                    "You can stop using SkillShare at any time and delete your account. We may suspend or terminate access for violations of these terms.",
                ]},
                {"heading": "Changes", "paragraphs": [
                    "We may update these terms as the product evolves. Material changes will be posted here, and continued use after a change means you accept the updated terms.",
                ]},
            ],
        ),
    ]
    for page in pages:
        if not db.query(ContentPage.id).filter(ContentPage.key == page.key).first():
            db.add(page)

    db.commit()


def ensure_columns() -> None:
    """create_all() makes missing tables but not missing columns. Add columns
    introduced after a DB was first created, so existing local SQLite databases
    upgrade in place without a --reset wipe."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "is_admin" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
        print("Migrated: added users.is_admin column.")


def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        if db.query(User.id).first():
            print("Users already seeded — skipping demo data (use --reset to wipe).")
        else:
            seed(db)
            print(f"Seeded demo data. Login: aniket.lnu@think41.com / {settings.seed_password}")
        # Content tables are seeded idempotently every run so existing DBs fill in.
        seed_content(db)
        # Ensure the platform admin flag is set even on a pre-existing DB.
        admin = db.query(User).filter(User.email == "aniket.lnu@think41.com").first()
        if admin and not admin.is_admin:
            admin.is_admin = True
            db.commit()
        print("Marketing content (blog, changelog, legal pages) is up to date.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
