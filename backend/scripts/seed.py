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

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Activity,
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
                       created_at=t("2025-09-12")),
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


def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User.id).first():
            print("Database already seeded — use --reset to wipe and reseed.")
            return
        seed(db)
        print(f"Seeded demo data. Login: aniket.lnu@think41.com / {settings.seed_password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
