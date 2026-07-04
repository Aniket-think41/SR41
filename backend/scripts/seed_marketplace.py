"""
Marketplace showcase seed — creates 5 public organizations (all owned by the
SkillShare admin) and fills them + the public marketplace with ~225 real
skills, MCP servers, and team notes curated from the open ecosystem
(modelcontextprotocol/servers, official integrations, community servers, and
common agent skills / team playbooks).

Idempotent: stable IDs, skip-if-exists. Safe to re-run.

  # against production Neon (export the prod URL first):
  DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST/db?sslmode=require" \
      .venv/bin/python -m scripts.seed_marketplace

  # wipe the showcase orgs/resources and rebuild:
  ... -m scripts.seed_marketplace --reset

The owner is resolved by OWNER_EMAIL (default aniket.lnu@think41.com).
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, ".")  # allow running as a script from backend/

from app.database import SessionLocal  # noqa: E402
from app.models import Organization, OrgMember, Resource, User  # noqa: E402

OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "aniket.lnu@think41.com")


# ---------------------------------------------------------------------------
# Deterministic, idempotent helpers
# ---------------------------------------------------------------------------

def _h(seed: str, n: int = 8) -> int:
    return int(hashlib.md5(seed.encode()).hexdigest()[:n], 16)


def counts(rid: str) -> tuple[int, int]:
    """Plausible, stable (stars, installs) derived from the resource id."""
    h = _h(rid)
    stars = 28 + h % 1900
    installs = stars * (4 + (h >> 8) % 11) + (h % 400)
    return stars, installs


def version_for(rid: str) -> str:
    h = _h(rid)
    return f"{1 + h % 3}.{(h >> 4) % 12}.{(h >> 8) % 10}"


def slugify(s: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in s)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


# ---------------------------------------------------------------------------
# Content generators
# ---------------------------------------------------------------------------

def mcp_config(key: str, runtime: str, pkg: str, env_keys: list[str], extra_args: list[str]) -> str:
    if runtime == "npx":
        args = ["-y", pkg] + extra_args
        command = "npx"
    elif runtime == "uvx":
        args = [pkg] + extra_args
        command = "uvx"
    elif runtime == "docker":
        args = ["run", "-i", "--rm", pkg] + extra_args
        command = "docker"
    else:
        args = [pkg] + extra_args
        command = runtime
    server: dict = {"command": command, "args": args}
    if env_keys:
        server["env"] = {k: f"<your-{k.lower().replace('_', '-')}>" for k in env_keys}
    return json.dumps({"mcpServers": {key: server}}, indent=2)


def mcp_md(title: str, key: str, runtime: str, pkg: str, desc: str, env_keys: list[str], source: str) -> str:
    install = {
        "npx": f"npx -y {pkg}",
        "uvx": f"uvx {pkg}",
        "docker": f"docker run -i --rm {pkg}",
    }.get(runtime, pkg)
    env_block = ""
    if env_keys:
        env_block = "\n## Configuration\n\nSet these environment variables (kept server-side, never sent to the model):\n\n" + \
            "".join(f"- `{k}`\n" for k in env_keys)
    return (
        f"# {title}\n\n{desc}\n\n## Install\n\n```bash\n{install}\n```\n\n"
        f"Add to your MCP client config (`claude_desktop_config.json`, `.mcp.json`, etc.):\n\n"
        f"```json\n{mcp_config(key, runtime, pkg, env_keys, [])}\n```\n"
        f"{env_block}\n## Source\n\n{source}\n"
    )


def skill_md(title: str, desc: str, steps: list[str], inputs: list[str], source: str) -> str:
    slug = slugify(title)
    steps_md = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    inputs_md = "\n".join(f"- `{i}`" for i in inputs)
    return (
        f"# {title}\n\n{desc}\n\n## When to use\n\nInvoke this skill when {desc[0].lower() + desc[1:]}\n\n"
        f"## Usage\n\n```bash\nclaude skill add {slug}\n```\n\n"
        f"## Inputs\n\n{inputs_md}\n\n## How it works\n\n{steps_md}\n\n"
        f"## Output\n\nA structured result with a short summary and actionable next steps.\n\n"
        f"## Reference\n\n{source}\n"
    )


def note_md(title: str, intro: str, sections: list[tuple[str, str]]) -> str:
    body = f"# {title}\n\n{intro}\n"
    for heading, text in sections:
        body += f"\n## {heading}\n\n{text}\n"
    return body


# ---------------------------------------------------------------------------
# CATALOGS
# ---------------------------------------------------------------------------
# MCP entry: (title, key, runtime, pkg, [env_keys], description, [tags], source)

OFFICIAL_MCP = [
    ("Filesystem", "filesystem", "npx", "@modelcontextprotocol/server-filesystem", [], "Secure, sandboxed read/write access to a configurable set of local directories. The reference server for giving agents file access with explicit allow-listed roots.", ["filesystem", "files", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem"),
    ("Fetch", "fetch", "uvx", "mcp-server-fetch", [], "Fetches a URL and converts HTML to clean markdown for the model to read. The canonical web-fetch server for grounding answers in live pages.", ["web", "fetch", "html", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch"),
    ("Git", "git", "uvx", "mcp-server-git", [], "Read, search, and manipulate a local Git repository — status, diff, log, blame, and commit operations exposed as tools.", ["git", "vcs", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/git"),
    ("GitHub", "github", "npx", "@modelcontextprotocol/server-github", ["GITHUB_PERSONAL_ACCESS_TOKEN"], "Manage issues, pull requests, files, and searches across the GitHub API. Tokens stay server-side; agents get structured results.", ["github", "vcs", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/github"),
    ("GitLab", "gitlab", "npx", "@modelcontextprotocol/server-gitlab", ["GITLAB_PERSONAL_ACCESS_TOKEN", "GITLAB_API_URL"], "Project, issue, and merge-request management against the GitLab API, self-hosted or SaaS.", ["gitlab", "vcs", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/gitlab"),
    ("Google Drive", "gdrive", "npx", "@modelcontextprotocol/server-gdrive", ["GDRIVE_CREDENTIALS_PATH"], "Search and read files from Google Drive, with automatic export of Google Docs/Sheets/Slides to readable formats.", ["google", "drive", "files", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/gdrive"),
    ("Google Maps", "google-maps", "npx", "@modelcontextprotocol/server-google-maps", ["GOOGLE_MAPS_API_KEY"], "Geocoding, place search, directions, and distance-matrix lookups via the Google Maps Platform.", ["google", "maps", "geo", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/google-maps"),
    ("Slack", "slack", "npx", "@modelcontextprotocol/server-slack", ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"], "Read channels and post messages with scoped bot permissions — great for status updates, triage bots, and digests.", ["slack", "messaging", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/slack"),
    ("PostgreSQL", "postgres", "npx", "@modelcontextprotocol/server-postgres", [], "Read-only Postgres access with schema introspection and query timeouts. Connection strings stay server-side.", ["database", "postgres", "sql", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/postgres"),
    ("SQLite", "sqlite", "uvx", "mcp-server-sqlite", [], "Query and inspect a local SQLite database, with built-in business-insight memo tooling for analysis sessions.", ["database", "sqlite", "sql", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite"),
    ("Sentry", "sentry", "uvx", "mcp-server-sentry", ["SENTRY_AUTH_TOKEN"], "Retrieve and analyze Sentry issues and stack traces so agents can triage production errors with full context.", ["observability", "errors", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/sentry"),
    ("Puppeteer", "puppeteer", "npx", "@modelcontextprotocol/server-puppeteer", [], "Headless-browser automation: navigate, screenshot, click, fill forms, and scrape rendered pages.", ["browser", "automation", "scraping", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer"),
    ("Brave Search", "brave-search", "npx", "@modelcontextprotocol/server-brave-search", ["BRAVE_API_KEY"], "Web and local search through the Brave Search API — privacy-respecting grounding for agents.", ["search", "web", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search"),
    ("Memory", "memory", "npx", "@modelcontextprotocol/server-memory", [], "A knowledge-graph-based persistent memory so agents remember facts, entities, and relations across sessions.", ["memory", "knowledge-graph", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/memory"),
    ("Time", "time", "uvx", "mcp-server-time", [], "Current time and timezone conversion utilities — the small, dependable helper every agent ends up needing.", ["time", "utility", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/time"),
    ("Everything", "everything", "npx", "@modelcontextprotocol/server-everything", [], "A reference/test server exercising every MCP feature — prompts, tools, resources, sampling — for building and debugging clients.", ["reference", "testing", "demo"], "https://github.com/modelcontextprotocol/servers/tree/main/src/everything"),
    ("Sequential Thinking", "sequential-thinking", "npx", "@modelcontextprotocol/server-sequential-thinking", [], "A tool for dynamic, reflective problem-solving through a structured chain of thoughts that can branch and revise.", ["reasoning", "planning", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking"),
    ("AWS KB Retrieval", "aws-kb", "npx", "@modelcontextprotocol/server-aws-kb-retrieval", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"], "Retrieve from an Amazon Bedrock Knowledge Base via the Agent Runtime — RAG grounded in your AWS-hosted documents.", ["aws", "rag", "bedrock", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/aws-kb-retrieval-server"),
    ("Redis", "redis", "npx", "@modelcontextprotocol/server-redis", [], "Interact with a Redis key-value store — get/set, scan, and manage keys for caching and ephemeral state.", ["database", "redis", "cache", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/redis"),
    ("EverArt", "everart", "npx", "@modelcontextprotocol/server-everart", ["EVERART_API_KEY"], "Generate images with multiple models through the EverArt API, returned as ready-to-use URLs.", ["image", "generation", "reference"], "https://github.com/modelcontextprotocol/servers/tree/main/src/everart"),
    # Official third-party integrations (maintained by the vendors, listed in the MCP servers README)
    ("Stripe", "stripe", "npx", "@stripe/mcp", ["STRIPE_SECRET_KEY"], "Interact with the Stripe API — customers, payments, invoices, and products — from your agent.", ["payments", "stripe", "official"], "https://github.com/stripe/agent-toolkit"),
    ("Cloudflare", "cloudflare", "npx", "@cloudflare/mcp-server-cloudflare", ["CLOUDFLARE_API_TOKEN"], "Manage Cloudflare Workers, KV, R2, D1, and DNS through the official Cloudflare MCP server.", ["cloudflare", "edge", "official"], "https://github.com/cloudflare/mcp-server-cloudflare"),
    ("Notion", "notion", "npx", "@notionhq/notion-mcp-server", ["NOTION_API_KEY"], "Read and write Notion pages and databases via the official Notion MCP integration.", ["notion", "docs", "official"], "https://github.com/makenotion/notion-mcp-server"),
    ("Linear", "linear", "npx", "@linear/mcp-server", ["LINEAR_API_KEY"], "Create, search, and update Linear issues and projects from your agent — official integration.", ["linear", "issues", "official"], "https://linear.app/docs/mcp"),
    ("Neon", "neon", "npx", "@neondatabase/mcp-server-neon", ["NEON_API_KEY"], "Manage serverless Postgres on Neon — create projects, run SQL, and branch databases.", ["database", "postgres", "neon", "official"], "https://github.com/neondatabase/mcp-server-neon"),
    ("Supabase", "supabase", "npx", "@supabase/mcp-server-supabase", ["SUPABASE_ACCESS_TOKEN"], "Query tables, manage projects, and run SQL against Supabase — the official MCP integration.", ["database", "supabase", "official"], "https://github.com/supabase-community/supabase-mcp"),
    ("Qdrant", "qdrant", "uvx", "mcp-server-qdrant", ["QDRANT_URL", "QDRANT_API_KEY"], "Store and retrieve vector memories in the Qdrant vector database for semantic search and RAG.", ["vector", "qdrant", "rag", "official"], "https://github.com/qdrant/mcp-server-qdrant"),
    ("Chroma", "chroma", "uvx", "chroma-mcp", [], "Embeddings, vector search, and document storage backed by the Chroma vector database.", ["vector", "chroma", "rag", "official"], "https://github.com/chroma-core/chroma-mcp"),
    ("Browserbase", "browserbase", "npx", "@browserbasehq/mcp", ["BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID"], "Cloud headless browsers for navigation, screenshots, and data extraction at scale.", ["browser", "automation", "official"], "https://github.com/browserbase/mcp-server-browserbase"),
    ("E2B", "e2b", "npx", "@e2b/mcp-server", ["E2B_API_KEY"], "Run AI-generated code in secure cloud sandboxes — a safe execution surface for agents.", ["sandbox", "code-execution", "official"], "https://github.com/e2b-dev/mcp-server"),
    ("Axiom", "axiom", "npx", "@axiomhq/mcp-server-axiom", ["AXIOM_TOKEN"], "Query and analyze logs, traces, and event data in Axiom using natural language.", ["observability", "logs", "official"], "https://github.com/axiomhq/mcp-server-axiom"),
    ("Grafana", "grafana", "docker", "mcp/grafana", ["GRAFANA_URL", "GRAFANA_API_KEY"], "Search dashboards, query Prometheus/Loki datasources, and inspect incidents in Grafana.", ["observability", "grafana", "official"], "https://github.com/grafana/mcp-grafana"),
    ("Heroku", "heroku", "npx", "@heroku/mcp-server", ["HEROKU_API_KEY"], "Manage Heroku apps, dynos, add-ons, and config vars from your agent.", ["heroku", "paas", "official"], "https://github.com/heroku/heroku-mcp-server"),
    ("Hugging Face", "huggingface", "npx", "@huggingface/mcp-server", ["HF_TOKEN"], "Search models, datasets, and Spaces on the Hugging Face Hub and call hosted inference.", ["ml", "models", "official"], "https://huggingface.co/settings/mcp"),
    ("PayPal", "paypal", "npx", "@paypal/mcp", ["PAYPAL_ACCESS_TOKEN"], "Create invoices, manage orders, and process payments through the official PayPal MCP server.", ["payments", "paypal", "official"], "https://github.com/paypal/agent-toolkit"),
    ("Square", "square", "npx", "@square/square-mcp-server", ["SQUARE_ACCESS_TOKEN"], "Access the Square API for payments, catalog, customers, and orders.", ["payments", "square", "official"], "https://developer.squareup.com/docs/mcp"),
    ("Apify", "apify", "npx", "@apify/actors-mcp-server", ["APIFY_TOKEN"], "Run any of 5,000+ Apify Actors to scrape websites, search, and extract structured data.", ["scraping", "automation", "official"], "https://github.com/apify/actors-mcp-server"),
    ("Firecrawl", "firecrawl", "npx", "firecrawl-mcp", ["FIRECRAWL_API_KEY"], "Crawl, scrape, and convert entire websites to clean markdown for LLM grounding.", ["scraping", "web", "official"], "https://github.com/mendableai/firecrawl-mcp-server"),
    ("Exa", "exa", "npx", "exa-mcp-server", ["EXA_API_KEY"], "Neural web search built for AI — semantic results, content retrieval, and similarity search.", ["search", "web", "official"], "https://github.com/exa-labs/exa-mcp-server"),
    ("Tavily", "tavily", "npx", "tavily-mcp", ["TAVILY_API_KEY"], "Search and extract optimized for LLM agents, with concise, citation-ready results.", ["search", "web", "official"], "https://github.com/tavily-ai/tavily-mcp"),
    ("Perplexity", "perplexity", "npx", "@perplexity-ai/mcp-server", ["PERPLEXITY_API_KEY"], "Ask Perplexity's Sonar models for grounded, cited answers to live questions.", ["search", "research", "official"], "https://github.com/ppl-ai/modelcontextprotocol"),
    ("Elasticsearch", "elasticsearch", "npx", "@elastic/mcp-server-elasticsearch", ["ES_URL", "ES_API_KEY"], "Search and aggregate over Elasticsearch indices using natural language.", ["search", "elasticsearch", "official"], "https://github.com/elastic/mcp-server-elasticsearch"),
    ("MongoDB", "mongodb", "npx", "mongodb-mcp-server", ["MDB_MCP_CONNECTION_STRING"], "Query collections, inspect schemas, and run aggregations against MongoDB and Atlas.", ["database", "mongodb", "official"], "https://github.com/mongodb-js/mongodb-mcp-server"),
    ("Astra DB", "astra-db", "npx", "@datastax/astra-db-mcp", ["ASTRA_DB_APPLICATION_TOKEN", "ASTRA_DB_API_ENDPOINT"], "Manage collections and run vector search on DataStax Astra DB.", ["database", "vector", "official"], "https://github.com/datastax/astra-db-mcp"),
    ("Snyk", "snyk", "npx", "snyk", ["SNYK_TOKEN"], "Scan code and dependencies for vulnerabilities and license issues via the Snyk MCP server.", ["security", "sca", "official"], "https://github.com/snyk/snyk-ls"),
    ("Semgrep", "semgrep", "uvx", "semgrep-mcp", ["SEMGREP_APP_TOKEN"], "Run static-analysis security scans with Semgrep and surface findings to the agent.", ["security", "sast", "official"], "https://github.com/semgrep/mcp"),
    ("Pinecone", "pinecone", "npx", "@pinecone-database/mcp", ["PINECONE_API_KEY"], "Upsert and query vectors in Pinecone for production-grade semantic search and RAG.", ["vector", "pinecone", "official"], "https://github.com/pinecone-io/pinecone-mcp"),
    ("Logfire", "logfire", "uvx", "logfire-mcp", ["LOGFIRE_READ_TOKEN"], "Query OpenTelemetry traces and metrics collected by Pydantic Logfire.", ["observability", "tracing", "official"], "https://github.com/pydantic/logfire-mcp"),
]

COMMUNITY_MCP = [
    ("Playwright", "playwright", "npx", "@playwright/mcp", [], "Drive a real browser with Playwright — navigate, assert, screenshot, and extract from rendered pages with accessibility-tree awareness.", ["browser", "automation", "testing"], "https://github.com/microsoft/playwright-mcp"),
    ("Docker", "docker", "npx", "docker-mcp", [], "Manage containers, images, volumes, and compose stacks on the local Docker daemon.", ["docker", "containers", "devops"], "https://github.com/QuantGeekDev/docker-mcp"),
    ("Kubernetes", "kubernetes", "npx", "mcp-server-kubernetes", [], "Inspect and operate a Kubernetes cluster — pods, deployments, logs, and kubectl-style actions.", ["kubernetes", "devops", "infra"], "https://github.com/Flux159/mcp-server-kubernetes"),
    ("MySQL", "mysql", "npx", "@benborla29/mcp-server-mysql", ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASS"], "Run read-only queries and inspect schemas on a MySQL database.", ["database", "mysql", "sql"], "https://github.com/benborla/mcp-server-mysql"),
    ("ClickHouse", "clickhouse", "uvx", "mcp-clickhouse", ["CLICKHOUSE_HOST", "CLICKHOUSE_USER"], "Query the ClickHouse columnar warehouse for fast analytical workloads.", ["database", "analytics", "olap"], "https://github.com/ClickHouse/mcp-clickhouse"),
    ("DuckDB", "duckdb", "uvx", "mcp-server-motherduck", ["motherduck_token"], "Analytical SQL over local files and MotherDuck — Parquet, CSV, and cloud data lakes.", ["database", "analytics", "duckdb"], "https://github.com/motherduckdb/mcp-server-motherduck"),
    ("BigQuery", "bigquery", "uvx", "mcp-server-bigquery", ["GOOGLE_APPLICATION_CREDENTIALS", "BIGQUERY_PROJECT"], "Run queries and inspect datasets in Google BigQuery.", ["database", "bigquery", "gcp"], "https://github.com/LucasHild/mcp-server-bigquery"),
    ("Snowflake", "snowflake", "uvx", "mcp-snowflake-server", ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"], "Query the Snowflake data cloud and explore warehouses, databases, and schemas.", ["database", "snowflake", "warehouse"], "https://github.com/isaacwasserman/mcp-snowflake-server"),
    ("Airtable", "airtable", "npx", "airtable-mcp-server", ["AIRTABLE_API_KEY"], "Read and write Airtable bases, tables, and records from your agent.", ["airtable", "database", "saas"], "https://github.com/domdomegg/airtable-mcp-server"),
    ("Obsidian", "obsidian", "npx", "mcp-obsidian", ["OBSIDIAN_API_KEY"], "Search and read your Obsidian vault notes through the Local REST API plugin.", ["notes", "obsidian", "pkm"], "https://github.com/MarkusPfundstein/mcp-obsidian"),
    ("Todoist", "todoist", "npx", "@abhiz123/todoist-mcp-server", ["TODOIST_API_TOKEN"], "Create, query, and complete Todoist tasks with natural-language filters.", ["productivity", "tasks", "saas"], "https://github.com/abhiz123/todoist-mcp-server"),
    ("Spotify", "spotify", "uvx", "spotify-mcp", ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"], "Control playback, search the catalog, and manage playlists on Spotify.", ["music", "spotify", "media"], "https://github.com/varunneal/spotify-mcp"),
    ("YouTube", "youtube", "npx", "@anaisbetts/mcp-youtube", [], "Fetch transcripts and metadata for YouTube videos so agents can summarize them.", ["video", "youtube", "media"], "https://github.com/anaisbetts/mcp-youtube"),
    ("Reddit", "reddit", "uvx", "mcp-server-reddit", [], "Browse subreddits, fetch posts and comments, and search Reddit content.", ["social", "reddit", "web"], "https://github.com/Hawstein/mcp-server-reddit"),
    ("Discord", "discord", "npx", "mcp-discord", ["DISCORD_TOKEN"], "Read and send messages and manage channels on a Discord server.", ["messaging", "discord", "social"], "https://github.com/v-3/discordmcp"),
    ("Telegram", "telegram", "npx", "@chaindead/telegram-mcp", ["TG_APP_ID", "TG_API_HASH"], "Read chats and send messages through the Telegram MTProto API.", ["messaging", "telegram", "social"], "https://github.com/chaindead/telegram-mcp"),
    ("Gmail", "gmail", "npx", "@gongrzhe/server-gmail-autoauth-mcp", [], "Read, search, draft, and send email through a connected Gmail account.", ["email", "gmail", "google"], "https://github.com/GongRzhe/Gmail-MCP-Server"),
    ("Google Calendar", "gcal", "npx", "@gongrzhe/server-calendar-autoauth-mcp", [], "List, create, and update events on Google Calendar.", ["calendar", "google", "productivity"], "https://github.com/GongRzhe/Calendar-MCP-Server"),
    ("Jira", "jira", "uvx", "mcp-atlassian", ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"], "Create, search, and transition Jira issues across projects.", ["jira", "atlassian", "issues"], "https://github.com/sooperset/mcp-atlassian"),
    ("Confluence", "confluence", "uvx", "mcp-atlassian", ["CONFLUENCE_URL", "CONFLUENCE_API_TOKEN"], "Search and read Confluence spaces and pages for grounded answers.", ["confluence", "atlassian", "docs"], "https://github.com/sooperset/mcp-atlassian"),
    ("Asana", "asana", "npx", "@roychri/mcp-server-asana", ["ASANA_ACCESS_TOKEN"], "Manage Asana tasks, projects, and workspaces from your agent.", ["asana", "tasks", "pm"], "https://github.com/roychri/mcp-server-asana"),
    ("Trello", "trello", "npx", "@delorenj/mcp-server-trello", ["TRELLO_API_KEY", "TRELLO_TOKEN"], "Read and update Trello boards, lists, and cards.", ["trello", "kanban", "pm"], "https://github.com/delorenj/mcp-server-trello"),
    ("Figma", "figma", "npx", "figma-developer-mcp", ["FIGMA_API_KEY"], "Pull layout, styles, and component data from Figma files to generate accurate UI.", ["design", "figma", "frontend"], "https://github.com/GLips/Figma-Context-MCP"),
    ("Blender", "blender", "uvx", "blender-mcp", [], "Drive Blender for 3D modeling, scene creation, and rendering via natural language.", ["3d", "blender", "creative"], "https://github.com/ahujasid/blender-mcp"),
    ("Home Assistant", "home-assistant", "uvx", "mcp-server-home-assistant", ["HA_URL", "HA_TOKEN"], "Control smart-home devices and query state through Home Assistant.", ["iot", "home-automation"], "https://github.com/tevonsb/homeassistant-mcp"),
    ("Apple Shortcuts", "apple-shortcuts", "npx", "@modelcontextprotocol/server-apple-shortcuts", [], "Run macOS/iOS Shortcuts as tools to automate the Apple ecosystem.", ["apple", "automation", "macos"], "https://github.com/recursechat/mcp-server-apple-shortcuts"),
    ("Shell", "shell", "uvx", "mcp-shell-server", ["ALLOW_COMMANDS"], "Execute an allow-listed set of shell commands in a controlled working directory.", ["shell", "system", "automation"], "https://github.com/tumf/mcp-shell-server"),
    ("AWS", "aws", "uvx", "awslabs.core-mcp-server", ["AWS_PROFILE", "AWS_REGION"], "Interact with AWS services through the official AWS Labs MCP servers — Cost Explorer, docs, CDK, and more.", ["aws", "cloud", "infra"], "https://github.com/awslabs/mcp"),
    ("Terraform", "terraform", "docker", "hashicorp/terraform-mcp-server", [], "Explore Terraform Registry providers and modules and reason about infrastructure code.", ["terraform", "iac", "devops"], "https://github.com/hashicorp/terraform-mcp-server"),
    ("Prometheus", "prometheus", "uvx", "prometheus-mcp-server", ["PROMETHEUS_URL"], "Run PromQL queries and inspect metrics and alerts from Prometheus.", ["observability", "metrics", "prometheus"], "https://github.com/pab1it0/prometheus-mcp-server"),
    ("Datadog", "datadog", "npx", "@winor30/mcp-server-datadog", ["DATADOG_API_KEY", "DATADOG_APP_KEY"], "Query metrics, monitors, logs, and incidents in Datadog.", ["observability", "datadog", "monitoring"], "https://github.com/winor30/mcp-server-datadog"),
    ("PagerDuty", "pagerduty", "uvx", "pagerduty-mcp-server", ["PAGERDUTY_API_TOKEN"], "List incidents, on-call schedules, and services in PagerDuty for incident response.", ["incident", "pagerduty", "oncall"], "https://github.com/wpfleger96/pagerduty-mcp-server"),
    ("Shopify", "shopify", "npx", "@shopify/dev-mcp", ["SHOPIFY_ACCESS_TOKEN"], "Query products, orders, and customers and explore the Shopify Admin API.", ["ecommerce", "shopify", "saas"], "https://github.com/Shopify/dev-mcp"),
    ("Cloudinary", "cloudinary", "npx", "@cloudinary/mcp-server", ["CLOUDINARY_URL"], "Upload, transform, and manage media assets on Cloudinary.", ["media", "images", "cdn"], "https://github.com/cloudinary/mcp-server"),
    ("Vercel", "vercel", "npx", "@vercel/mcp-adapter", ["VERCEL_TOKEN"], "Inspect deployments, projects, and environment variables on Vercel.", ["vercel", "deploy", "frontend"], "https://github.com/vercel/mcp-adapter"),
    ("Raygun", "raygun", "npx", "@raygun.io/mcp-server-raygun", ["RAYGUN_PAT_TOKEN"], "Access crash reporting and real-user-monitoring data from Raygun.", ["observability", "errors", "monitoring"], "https://github.com/MindscapeHQ/mcp-server-raygun"),
    ("Algolia", "algolia", "npx", "@algolia/mcp", ["ALGOLIA_APP_ID", "ALGOLIA_API_KEY"], "Search and manage Algolia indices and inspect analytics.", ["search", "algolia", "saas"], "https://github.com/algolia/mcp-node"),
    ("Weaviate", "weaviate", "uvx", "mcp-server-weaviate", ["WEAVIATE_URL", "WEAVIATE_API_KEY"], "Store and query objects with vector search in the Weaviate database.", ["vector", "weaviate", "rag"], "https://github.com/weaviate/mcp-server-weaviate"),
    ("Milvus", "milvus", "uvx", "milvus-mcp-server", ["MILVUS_URI"], "Vector similarity search and collection management on the Milvus database.", ["vector", "milvus", "rag"], "https://github.com/zilliztech/mcp-server-milvus"),
    ("Couchbase", "couchbase", "uvx", "couchbase-mcp-server", ["CB_CONNECTION_STRING", "CB_USERNAME"], "Run N1QL queries and inspect buckets and scopes in Couchbase.", ["database", "couchbase", "nosql"], "https://github.com/Couchbase-Ecosystem/mcp-server-couchbase"),
    ("Neo4j", "neo4j", "uvx", "mcp-neo4j-cypher", ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"], "Run Cypher queries and explore the schema of a Neo4j graph database.", ["database", "graph", "neo4j"], "https://github.com/neo4j-contrib/mcp-neo4j"),
    ("Stripe Agent", "stripe-toolkit", "npx", "@stripe/agent-toolkit", ["STRIPE_SECRET_KEY"], "A higher-level Stripe toolkit for building billing and payment agent workflows.", ["payments", "stripe", "billing"], "https://github.com/stripe/agent-toolkit"),
    ("WhatsApp", "whatsapp", "uvx", "whatsapp-mcp", [], "Read and send WhatsApp messages through a bridged personal account.", ["messaging", "whatsapp", "social"], "https://github.com/lharries/whatsapp-mcp"),
    ("OpenAPI", "openapi", "npx", "@ivotoby/openapi-mcp-server", ["OPENAPI_SPEC_URL"], "Turn any OpenAPI/Swagger spec into callable MCP tools automatically.", ["api", "openapi", "integration"], "https://github.com/snaggle-ai/openapi-mcp-server"),
    ("Excel", "excel", "npx", "@negokaz/excel-mcp-server", [], "Read and write `.xlsx` workbooks — sheets, ranges, and formulas — without Excel installed.", ["excel", "spreadsheet", "files"], "https://github.com/negokaz/excel-mcp-server"),
    ("Wikipedia", "wikipedia", "uvx", "wikipedia-mcp", [], "Search and read Wikipedia articles for reliable, citation-ready grounding.", ["wikipedia", "research", "web"], "https://github.com/Rudra-ravi/wikipedia-mcp"),
]

# SKILL entry: (title, description, [tags], [steps], [inputs], source)

OFFICIAL_SKILLS = [
    ("Commit Message Writer", "Reads your staged diff and writes a clean Conventional Commits message with a scoped subject and a body that explains the why.", ["git", "commits", "docs"], ["Run `git diff --staged` to read the change.", "Classify it as feat/fix/refactor/docs/chore.", "Write a <=50-char subject and a wrapped body.", "Flag breaking changes with a `!` and a footer."], ["scope", "style"], "https://www.conventionalcommits.org"),
    ("PR Description Generator", "Turns a branch's commits and diff into a structured pull-request description with summary, changes, test plan, and risk notes.", ["github", "review", "docs"], ["Collect commits between the base and head.", "Group changes by area.", "Draft summary, test plan, and rollback notes.", "Link related issues."], ["base_branch", "template"], "https://github.blog/changelog"),
    ("Code Reviewer", "Reviews a diff for correctness bugs, security issues, and simplification opportunities, leaving inline comments and a summary verdict.", ["code-review", "quality", "security"], ["Parse the diff into hunks.", "Check each hunk for logic, edge-case, and security defects.", "Suggest reuse and simplifications.", "Emit inline comments plus an approve/request-changes verdict."], ["effort", "ruleset"], "https://google.github.io/eng-practices/review/"),
    ("Unit Test Writer", "Generates table-driven unit tests for a target function, covering happy paths, edge cases, and error conditions in your project's test framework.", ["testing", "quality", "tdd"], ["Read the target function and its signature.", "Enumerate equivalence classes and edge cases.", "Generate tests in the detected framework.", "Add fixtures and assertions with clear names."], ["target", "framework"], "https://martinfowler.com/bliki/UnitTest.html"),
    ("Docstring Generator", "Writes accurate docstrings/JSDoc for functions and classes from their implementation, including params, returns, raises, and examples.", ["docs", "python", "javascript"], ["Infer parameter and return types.", "Summarize behavior in one line.", "Document params, returns, and raised errors.", "Add a minimal usage example."], ["style", "language"], "https://peps.python.org/pep-0257/"),
    ("Refactor Assistant", "Proposes and applies safe refactors — extract function, rename, dedupe, simplify conditionals — while preserving behavior and tests.", ["refactor", "quality", "cleanup"], ["Identify code smells in the target.", "Propose behavior-preserving refactors.", "Apply edits and update call sites.", "Run the test suite to confirm green."], ["target", "scope"], "https://refactoring.com"),
    ("Security Auditor", "Scans code for the OWASP Top 10 and common insecure patterns — injection, secrets, weak crypto, missing authz — and reports findings with fixes.", ["security", "sast", "owasp"], ["Walk the codebase for sensitive sinks.", "Match against OWASP Top 10 patterns.", "Rate severity and likelihood.", "Propose concrete remediations."], ["severity_threshold"], "https://owasp.org/www-project-top-ten/"),
    ("Dependency Upgrader", "Reads your lockfile, finds outdated and vulnerable dependencies, and proposes a staged upgrade plan with changelog highlights.", ["dependencies", "security", "maintenance"], ["Parse the manifest and lockfile.", "Query for newer and patched versions.", "Group upgrades by risk (patch/minor/major).", "Summarize breaking changes per major bump."], ["ecosystem"], "https://docs.npmjs.com/cli/commands/npm-audit"),
    ("Changelog Writer", "Reads merged PRs over a range and writes a human changelog grouped by Added, Changed, Fixed, and Removed.", ["release", "docs", "github"], ["Collect merged PRs in the range.", "Classify each by type.", "Write Keep-a-Changelog sections.", "Credit contributors."], ["from_tag", "to_tag"], "https://keepachangelog.com"),
    ("README Generator", "Bootstraps a high-quality README from a repository — what it does, install, quickstart, configuration, and contributing.", ["docs", "onboarding", "markdown"], ["Detect language, build tool, and entry points.", "Draft purpose and feature bullets.", "Write install and quickstart sections.", "Add badges and a license note."], ["project_name"], "https://www.makeareadme.com"),
    ("API Docs Writer", "Generates reference docs from route handlers or an OpenAPI spec — endpoints, params, request/response shapes, and examples.", ["docs", "api", "openapi"], ["Discover routes or parse the spec.", "Document params and bodies per endpoint.", "Generate request/response examples.", "Group by resource."], ["format"], "https://swagger.io/specification/"),
    ("SQL Query Builder", "Translates a natural-language question into a correct, parameterized SQL query against your schema, with an EXPLAIN-friendly shape.", ["sql", "database", "data"], ["Read the schema and relationships.", "Map the question to tables and joins.", "Write a parameterized query.", "Note indexes that would help."], ["dialect", "schema"], "https://use-the-index-luke.com"),
    ("Regex Builder", "Builds and explains a regular expression from a plain-English description, with test cases and a readable breakdown.", ["regex", "utility", "text"], ["Parse the matching intent.", "Construct the pattern incrementally.", "Generate positive and negative test cases.", "Explain each token."], ["flavor"], "https://www.regular-expressions.info"),
    ("Error Explainer", "Takes a stack trace or error message and explains the root cause, the likely fix, and how to prevent it next time.", ["debugging", "errors", "support"], ["Parse the stack trace.", "Locate the originating frame in your code.", "Explain the root cause in plain terms.", "Propose a fix and a guardrail."], ["language"], "https://stackoverflow.com"),
    ("Log Analyzer", "Ingests log output, clusters similar lines, surfaces anomalies and error spikes, and summarizes what happened on a timeline.", ["observability", "logs", "debugging"], ["Parse and normalize log lines.", "Cluster by template.", "Detect spikes and rare events.", "Summarize the incident timeline."], ["time_window"], "https://www.honeycomb.io/blog"),
    ("Performance Profiler", "Reads a profile or benchmark output and identifies hot paths, allocations, and N+1 patterns with prioritized optimizations.", ["performance", "profiling", "quality"], ["Parse the profile.", "Rank functions by self and cumulative time.", "Spot N+1 and allocation hotspots.", "Recommend targeted optimizations."], ["target"], "https://github.com/brendangregg/FlameGraph"),
    ("Accessibility Auditor", "Audits HTML/JSX against WCAG 2.2 AA — contrast, labels, roles, focus order — and reports issues with code-level fixes.", ["accessibility", "frontend", "wcag"], ["Parse the markup or component tree.", "Check against WCAG 2.2 AA rules.", "Flag contrast, label, and ARIA issues.", "Suggest accessible replacements."], ["level"], "https://www.w3.org/WAI/WCAG22/quickref/"),
    ("i18n Extractor", "Finds hardcoded user-facing strings, extracts them to a translation catalog, and rewrites the source to use translation keys.", ["i18n", "frontend", "localization"], ["Scan for hardcoded strings in JSX/templates.", "Generate stable translation keys.", "Write the catalog entries.", "Rewrite source to use the t() helper."], ["framework"], "https://www.i18next.com"),
    ("Type Annotator", "Adds precise type annotations to untyped Python/JS, inferring from usage and adding the minimal generics needed to pass the checker.", ["types", "python", "typescript"], ["Infer types from assignments and calls.", "Add annotations to signatures.", "Introduce generics only where needed.", "Run the type checker to confirm."], ["strictness"], "https://mypy.readthedocs.io"),
    ("Migration Writer", "Generates a forward and rollback database migration from a model diff, safe for zero-downtime deploys.", ["database", "migrations", "backend"], ["Diff the current and target schema.", "Write additive forward steps first.", "Add a tested rollback.", "Flag locking operations on large tables."], ["orm"], "https://martinfowler.com/articles/evodb.html"),
    ("Mock Data Generator", "Produces realistic, schema-aware fixtures and seed data — names, emails, relationships — for tests and demos.", ["testing", "data", "fixtures"], ["Read the schema and constraints.", "Generate realistic field values.", "Respect foreign-key relationships.", "Emit as SQL/JSON/CSV."], ["count", "format"], "https://fakerjs.dev"),
    ("GraphQL Schema Designer", "Designs a typed GraphQL schema from a domain description — types, queries, mutations, and pagination connections.", ["graphql", "api", "backend"], ["Model the domain as types.", "Add queries and mutations.", "Use Relay-style connections for lists.", "Annotate with descriptions."], ["domain"], "https://graphql.org/learn/"),
    ("JSON Schema Generator", "Infers a strict JSON Schema from example payloads, with formats, required fields, and sensible constraints.", ["json", "validation", "api"], ["Read the example payloads.", "Infer types and required fields.", "Add formats and bounds.", "Emit draft 2020-12 schema."], ["draft"], "https://json-schema.org"),
    ("Type Definition Writer", "Generates accurate TypeScript `.d.ts` declarations for an untyped JS module from its usage.", ["typescript", "types", "javascript"], ["Read the module's exports.", "Infer parameter and return types.", "Write declaration types.", "Verify with the compiler."], ["module"], "https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html"),
    ("Dead Code Finder", "Locates unused exports, unreachable branches, and orphaned files, and proposes safe deletions.", ["cleanup", "quality", "refactor"], ["Build the import/reference graph.", "Flag unreferenced symbols.", "Confirm no dynamic usage.", "Propose a deletion list."], ["entrypoints"], "https://github.com/pzavolinsky/ts-unused-exports"),
    ("Import Organizer", "Sorts, groups, and dedupes imports, removes unused ones, and applies your project's ordering convention.", ["cleanup", "style", "tooling"], ["Parse all imports.", "Remove unused.", "Group stdlib/third-party/local.", "Sort within groups."], ["order"], "https://github.com/lydell/eslint-plugin-simple-import-sort"),
    ("Diff Summarizer", "Reads a large diff and writes a concise, reviewer-friendly summary of what changed and why it matters.", ["code-review", "docs", "git"], ["Parse the diff by file and area.", "Group related changes.", "Summarize intent per group.", "Flag anything risky."], ["base"], "https://graphite.dev/guides"),
    ("Snapshot Test Updater", "Reviews failing snapshot diffs, distinguishes intended changes from regressions, and updates only the right snapshots.", ["testing", "quality", "frontend"], ["Read each snapshot diff.", "Classify intended vs. regression.", "Update intended snapshots.", "Flag suspected regressions."], ["framework"], "https://jestjs.io/docs/snapshot-testing"),
    ("Edge Case Enumerator", "Given a function, enumerates the boundary and adversarial inputs worth testing — empty, null, huge, malformed, concurrent.", ["testing", "quality", "tdd"], ["Read the signature and contract.", "Enumerate boundaries per input.", "Add adversarial and concurrency cases.", "Output a test matrix."], ["target"], "https://en.wikipedia.org/wiki/Boundary-value_analysis"),
    ("Mermaid Diagram Generator", "Turns a description or a codebase area into a Mermaid diagram — flowchart, sequence, ER, or class.", ["docs", "diagrams", "architecture"], ["Pick the diagram type.", "Extract entities and relations.", "Emit Mermaid syntax.", "Add a legend."], ["type"], "https://mermaid.js.org"),
    ("Input Validator Generator", "Generates request-validation code (Zod/Pydantic/Joi) from a schema or endpoint description, with helpful error messages.", ["validation", "backend", "api"], ["Read the schema or shape.", "Generate validators with constraints.", "Add clear error messages.", "Wire into the handler."], ["library"], "https://zod.dev"),
    ("Retry & Backoff Adder", "Wraps a flaky call with exponential backoff, jitter, and a circuit breaker, tuned to the operation's idempotency.", ["reliability", "backend", "patterns"], ["Identify the unreliable call.", "Add exponential backoff with jitter.", "Cap retries and add a breaker.", "Respect idempotency."], ["max_retries"], "https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/"),
    ("Pagination Implementer", "Adds cursor-based pagination to a list endpoint, including the query, response envelope, and client cursor handling.", ["api", "backend", "patterns"], ["Pick a stable sort key.", "Encode and decode cursors.", "Return `next_cursor`.", "Cap and validate `limit`."], ["page_size"], "https://relay.dev/graphql/connections.htm"),
    ("Rate Limiter Designer", "Adds a token-bucket or sliding-window rate limiter to an endpoint, with per-key limits and clear 429 responses.", ["reliability", "backend", "security"], ["Choose the algorithm and key.", "Implement the limiter.", "Return 429 with Retry-After.", "Add metrics."], ["limit"], "https://stripe.com/blog/rate-limiters"),
    ("Webhook Handler Scaffolder", "Scaffolds a secure webhook receiver — signature verification, idempotency keys, and an async processing queue.", ["backend", "integration", "security"], ["Verify the signature.", "Dedupe by idempotency key.", "Enqueue for async processing.", "Return 2xx fast."], ["provider"], "https://stripe.com/docs/webhooks"),
    ("Feature Flag Wrapper", "Wraps a code path behind a feature flag with a clean fallback and a TODO to remove the flag after rollout.", ["patterns", "deploy", "engineering"], ["Wrap the new path behind a flag.", "Keep the old path as fallback.", "Add an owner and removal date.", "Emit flag-state metrics."], ["flag_name"], "https://martinfowler.com/articles/feature-toggles.html"),
    ("Caching Layer Adder", "Introduces a read-through cache with sane TTLs and explicit invalidation around an expensive read.", ["performance", "backend", "patterns"], ["Identify the hot read.", "Add read-through caching.", "Set TTL and key strategy.", "Wire invalidation on writes."], ["ttl"], "https://aws.amazon.com/caching/best-practices/"),
    ("Config Schema Validator", "Validates app configuration at startup against a schema and fails fast with a precise, actionable error.", ["config", "reliability", "backend"], ["Define the config schema.", "Validate at boot.", "Fail fast with field-level errors.", "Document defaults."], ["format"], "https://12factor.net/config"),
    ("Exception Hierarchy Designer", "Designs a clean exception hierarchy for a module — base error, typed subclasses, and consistent messages.", ["patterns", "backend", "quality"], ["Identify failure modes.", "Define a base error type.", "Add typed subclasses.", "Standardize messages and codes."], ["module"], "https://google.github.io/styleguide/pyguide.html"),
    ("Logging Instrumenter", "Adds structured logging at the right points — boundaries, errors, and slow paths — with correlation IDs and no secrets.", ["observability", "backend", "logs"], ["Find boundaries and error paths.", "Add structured log statements.", "Attach correlation IDs.", "Scrub secrets."], ["level"], "https://12factor.net/logs"),
    ("Property-Based Test Writer", "Writes property-based tests that assert invariants over generated inputs, complementing example-based tests.", ["testing", "quality", "tdd"], ["State the invariants.", "Define input generators.", "Assert properties.", "Add shrinking-friendly cases."], ["target"], "https://hypothesis.readthedocs.io"),
    ("Code Smell Detector", "Scans a module for long functions, deep nesting, duplicated logic, and feature envy, ranked by impact.", ["quality", "refactor", "review"], ["Compute complexity metrics.", "Detect duplication and long methods.", "Rank smells by impact.", "Suggest the first refactor."], ["target"], "https://refactoring.guru/refactoring/smells"),
    ("Enum & Constant Extractor", "Replaces magic numbers and stringly-typed values with named enums/constants and updates all references.", ["refactor", "quality", "cleanup"], ["Find magic literals.", "Propose named constants/enums.", "Replace usages.", "Keep behavior identical."], ["scope"], "https://refactoring.com/catalog/replaceMagicLiteral.html"),
    ("Fixture Factory Builder", "Builds typed test-data factories with sensible defaults and overrides for your models.", ["testing", "fixtures", "quality"], ["Read the model fields.", "Generate factory with defaults.", "Support per-test overrides.", "Wire relationships."], ["model"], "https://thoughtbot.github.io/factory_bot/"),
    ("Function Signature Improver", "Suggests clearer signatures — fewer positional args, value objects over flags, and explicit return types.", ["refactor", "quality", "api"], ["Review the current signature.", "Group related args into objects.", "Replace boolean flags.", "Add explicit return types."], ["target"], "https://www.martinfowler.com/bliki/FlagArgument.html"),
]

AGENT_SKILLS = [
    ("Dockerfile Optimizer", "Rewrites a Dockerfile for smaller images and faster builds — multi-stage, layer ordering, cache mounts, and a non-root user.", ["docker", "devops", "performance"], ["Analyze the current Dockerfile and image size.", "Introduce multi-stage builds.", "Reorder layers for cache hits.", "Drop to a non-root user and slim base."], ["base_image"], "https://docs.docker.com/build/building/best-practices/"),
    ("Kubernetes Manifest Generator", "Generates production-ready K8s manifests — Deployment, Service, HPA, and probes — from a short service description.", ["kubernetes", "devops", "infra"], ["Capture image, ports, and resource needs.", "Generate Deployment with probes and limits.", "Add Service and HPA.", "Include a PodDisruptionBudget."], ["replicas"], "https://kubernetes.io/docs/concepts/"),
    ("CI Pipeline Builder", "Scaffolds a CI workflow (GitHub Actions / GitLab CI) with lint, test, build, and deploy stages and sensible caching.", ["ci", "devops", "automation"], ["Detect the toolchain.", "Generate lint and test jobs.", "Add build and artifact steps.", "Wire caching and matrix builds."], ["provider"], "https://docs.github.com/actions"),
    ("Terraform Module Author", "Writes a reusable Terraform module with variables, outputs, and examples, following the standard module structure.", ["terraform", "iac", "devops"], ["Define the resource surface.", "Parameterize with variables and defaults.", "Expose outputs.", "Add an example and README."], ["provider"], "https://developer.hashicorp.com/terraform/language/modules"),
    ("Incident Triage Assistant", "Given an alert and recent logs/metrics, proposes a likely root cause, blast radius, and the first three mitigation steps.", ["incident", "sre", "oncall"], ["Read the alert and correlated signals.", "Form a ranked hypothesis list.", "Estimate blast radius.", "Propose immediate mitigations."], ["severity"], "https://sre.google/sre-book/managing-incidents/"),
    ("On-call Digest", "Summarizes a shift's pages, deploys, and noisy alerts into a handoff note for the next on-call engineer.", ["oncall", "sre", "ops"], ["Collect pages and deploys in the window.", "Cluster recurring alerts.", "Note unresolved follow-ups.", "Write the handoff summary."], ["shift_window"], "https://increment.com/on-call/"),
    ("dbt Model Builder", "Drafts a dbt model with CTEs, tests, and documentation from a description of the desired transformation.", ["data", "dbt", "analytics"], ["Identify sources and grain.", "Write staging and final CTEs.", "Add schema tests.", "Document columns."], ["materialization"], "https://docs.getdbt.com/best-practices"),
    ("Pandas Analysis", "Loads a dataset, profiles it, and answers an analytical question with clean pandas code and a short narrative of findings.", ["data", "python", "pandas"], ["Load and profile the dataframe.", "Clean types and missing values.", "Compute the requested aggregation.", "Summarize findings."], ["question"], "https://pandas.pydata.org/docs/"),
    ("Chart Generator", "Turns a dataset and a question into the right chart with sensible encodings, labels, and a one-line takeaway.", ["data", "viz", "analytics"], ["Pick a chart type for the question.", "Map fields to encodings.", "Add titles and axis labels.", "State the takeaway."], ["library"], "https://www.storytellingwithdata.com"),
    ("Slide Deck Drafter", "Outlines and drafts a presentation from a brief — title, agenda, content slides, and a closing — in a clean structure.", ["docs", "presentation", "writing"], ["Capture the audience and goal.", "Outline the narrative arc.", "Draft one idea per slide.", "Add speaker notes."], ["length"], "https://www.duarte.com/presentation-skills-resources/"),
    ("Email Drafter", "Writes a clear, appropriately-toned email from a few bullet points — subject, body, and a specific call to action.", ["writing", "productivity", "comms"], ["Read the bullets and intent.", "Pick a tone for the audience.", "Draft subject and body.", "End with a clear ask."], ["tone"], "https://hbr.org/2016/11/how-to-write-email-with-military-precision"),
    ("Meeting Notes Summarizer", "Turns a transcript into structured notes — decisions, action items with owners, and open questions.", ["productivity", "notes", "comms"], ["Read the transcript.", "Extract decisions.", "List action items with owners and dates.", "Capture open questions."], ["attendees"], "https://www.atlassian.com/team-playbook"),
    ("Jira Ticket Writer", "Expands a one-line request into a well-formed ticket — context, acceptance criteria, and a test plan.", ["pm", "jira", "writing"], ["Clarify the user need.", "Write context and scope.", "Add Given/When/Then acceptance criteria.", "Note out-of-scope items."], ["issue_type"], "https://www.atlassian.com/agile/project-management/user-stories"),
    ("User Story Splitter", "Breaks a large story or epic into thin, independently shippable vertical slices with clear value each.", ["pm", "agile", "planning"], ["Identify the epic's value.", "Find natural slicing seams.", "Write thin vertical slices.", "Sequence by risk and value."], ["epic"], "https://www.humanizingwork.com/the-humanizing-work-guide-to-splitting-user-stories/"),
    ("RFC Drafter", "Drafts a design RFC — problem, goals/non-goals, proposed design, alternatives, and a rollout plan.", ["docs", "architecture", "writing"], ["State the problem and motivation.", "List goals and non-goals.", "Describe the proposed design.", "Compare alternatives and risks."], ["title"], "https://github.com/rust-lang/rfcs"),
    ("Data Pipeline Designer", "Designs an ETL/ELT pipeline from sources to warehouse — ingestion, transforms, scheduling, and data-quality checks.", ["data", "etl", "architecture"], ["Map sources and destinations.", "Choose batch vs. streaming.", "Define transforms and tests.", "Plan scheduling and backfills."], ["sources"], "https://www.startdataengineering.com"),
    ("Code Comment Explainer", "Reads an unfamiliar function and writes a plain-language walkthrough of what it does and why, line by line where useful.", ["docs", "onboarding", "code"], ["Read the function and its callers.", "Explain the high-level intent.", "Walk through tricky lines.", "Note assumptions and gotchas."], ["target"], "https://abseil.io/resources/swe-book"),
    ("Bash Script Author", "Writes a robust bash script with `set -euo pipefail`, argument parsing, and helpful error messages from a task description.", ["shell", "automation", "devops"], ["Capture inputs and behavior.", "Scaffold with strict mode and usage.", "Implement with clear functions.", "Add error handling and traps."], ["task"], "https://google.github.io/styleguide/shellguide.html"),
    ("OpenAPI Spec Writer", "Generates an OpenAPI 3.1 spec from route handlers or a description — paths, schemas, security, and examples.", ["api", "openapi", "docs"], ["Enumerate endpoints and methods.", "Define request/response schemas.", "Add security schemes.", "Include examples."], ["version"], "https://spec.openapis.org/oas/latest.html"),
    ("Cron Expression Builder", "Translates a natural-language schedule into a correct cron expression with a human-readable confirmation.", ["scheduling", "utility", "devops"], ["Parse the desired cadence.", "Build the five/six-field expression.", "Confirm the next run times.", "Note timezone caveats."], ["timezone"], "https://crontab.guru"),
    ("Release Train Conductor", "Cuts a release end to end — bumps versions, writes the changelog, tags, and drafts the announcement.", ["release", "ci", "automation"], ["Determine the version bump.", "Generate the changelog.", "Create the tag and notes.", "Draft the announcement."], ["channel"], "https://semver.org"),
    ("Helm Chart Author", "Generates a Helm chart for a service — templates, values, and sane defaults for probes, resources, and ingress.", ["kubernetes", "helm", "devops"], ["Capture the service shape.", "Template Deployment/Service/Ingress.", "Parameterize via values.yaml.", "Add NOTES and a README."], ["service"], "https://helm.sh/docs/"),
    ("GitHub Action Composer", "Builds a reusable composite GitHub Action from a sequence of steps, with inputs, outputs, and caching.", ["ci", "github", "automation"], ["Define inputs and outputs.", "Compose the steps.", "Add caching.", "Document usage."], ["name"], "https://docs.github.com/actions/sharing-automations/creating-actions"),
    ("Makefile Generator", "Writes a self-documenting Makefile with common targets — build, test, lint, run, clean — and a help target.", ["build", "devops", "tooling"], ["Detect the toolchain.", "Add standard targets.", "Make targets phony and idempotent.", "Add a `help` target."], ["language"], "https://www.gnu.org/software/make/manual/make.html"),
    ("Nginx Config Writer", "Generates an Nginx server block — TLS, gzip, caching headers, and a reverse proxy to your upstream.", ["nginx", "devops", "infra"], ["Capture domain and upstream.", "Add TLS and HTTP→HTTPS redirect.", "Set caching and gzip.", "Proxy to the upstream."], ["domain"], "https://nginx.org/en/docs/"),
    ("Ansible Playbook Writer", "Drafts an idempotent Ansible playbook for a provisioning task, with roles, handlers, and variables.", ["ansible", "iac", "devops"], ["Define the desired state.", "Write idempotent tasks.", "Add handlers and variables.", "Tag for partial runs."], ["target_host"], "https://docs.ansible.com"),
    ("Cloud Cost Analyzer", "Reads a cloud cost export and surfaces the top spend drivers, idle resources, and concrete savings.", ["finops", "cloud", "cost"], ["Parse the cost report.", "Rank spend by service and tag.", "Flag idle/oversized resources.", "Estimate savings."], ["provider"], "https://www.finops.org"),
    ("SLO Definer", "Helps define SLIs and SLOs for a service — what to measure, the target, and the error budget policy.", ["sre", "reliability", "slo"], ["Pick user-centric SLIs.", "Set realistic SLO targets.", "Define the error budget.", "Write the burn-rate alerts."], ["service"], "https://sre.google/workbook/implementing-slos/"),
    ("Alert Rule Writer", "Writes actionable alerting rules with multi-window burn rates, avoiding noisy single-threshold pages.", ["observability", "alerting", "sre"], ["Tie alerts to SLOs.", "Use multi-window burn rates.", "Add clear runbook links.", "Set severities."], ["metric"], "https://sre.google/workbook/alerting-on-slos/"),
    ("Runbook Generator", "Turns an alert into a step-by-step runbook — what it means, how to confirm, how to mitigate, and how to verify.", ["sre", "oncall", "docs"], ["Explain what the alert means.", "List confirmation steps.", "Give mitigation steps.", "Add verification and escalation."], ["alert"], "https://www.atlassian.com/incident-management/on-call/runbooks"),
    ("Load Test Designer", "Designs a load test — scenarios, ramp profile, and pass/fail SLAs — and scaffolds the k6/Locust script.", ["performance", "testing", "sre"], ["Model realistic user journeys.", "Define ramp and soak profiles.", "Set SLA thresholds.", "Scaffold the script."], ["tool"], "https://k6.io/docs/"),
    ("SQL Migration Reviewer", "Reviews a migration for lock risk, backward compatibility, and rollback safety before it ships.", ["database", "migrations", "review"], ["Detect locking operations.", "Check backward compatibility.", "Verify a rollback exists.", "Flag large-table risks."], ["dialect"], "https://github.com/ankane/strong_migrations"),
    ("Data Quality Checker", "Generates data-quality assertions for a table — nulls, ranges, uniqueness, freshness — and a report.", ["data", "quality", "analytics"], ["Profile the table.", "Generate not-null/range/unique checks.", "Add freshness checks.", "Emit a pass/fail report."], ["table"], "https://docs.getdbt.com/docs/build/tests"),
    ("Airflow DAG Builder", "Scaffolds an Airflow DAG with tasks, dependencies, retries, and sensible scheduling from a pipeline description.", ["data", "airflow", "etl"], ["Define tasks and order.", "Set retries and SLAs.", "Wire dependencies.", "Add the schedule and catchup policy."], ["schedule"], "https://airflow.apache.org/docs/"),
    ("Notebook Cleaner", "Cleans a Jupyter notebook for sharing — clears noisy output, orders cells, extracts functions, and adds markdown.", ["data", "python", "notebooks"], ["Clear and re-run outputs.", "Order and dedupe cells.", "Extract reusable functions.", "Add explanatory markdown."], ["notebook"], "https://jupyter.org"),
    ("A/B Test Analyzer", "Analyzes an experiment's results — lift, confidence interval, and significance — and writes a clear verdict.", ["data", "experimentation", "analytics"], ["Validate sample sizes.", "Compute lift and CI.", "Check significance and power.", "Write a ship/hold verdict."], ["metric"], "https://www.evanmiller.org/ab-testing/"),
    ("Standup Summarizer", "Turns async standup updates into a team summary — progress, blockers, and what needs attention today.", ["productivity", "agile", "comms"], ["Collect the updates.", "Group by progress/blocker/plan.", "Surface cross-team blockers.", "Flag at-risk items."], ["team"], "https://www.atlassian.com/agile/scrum/standups"),
    ("Sprint Retro Facilitator", "Structures a retrospective from collected notes — what went well, what didn't, and concrete experiments to try.", ["agile", "process", "facilitation"], ["Cluster the inputs.", "Surface themes.", "Pick a few experiments.", "Assign owners."], ["sprint"], "https://retromat.org"),
    ("Roadmap Drafter", "Turns goals and constraints into a themed quarterly roadmap with now/next/later horizons.", ["pm", "planning", "strategy"], ["Capture goals and constraints.", "Group into themes.", "Place on now/next/later.", "Note dependencies and risks."], ["quarter"], "https://www.productplan.com/learn/product-roadmap/"),
    ("Customer Email Responder", "Drafts an empathetic, accurate support reply from a ticket and the relevant docs, with a clear resolution.", ["support", "writing", "comms"], ["Read the ticket and context.", "Confirm the resolution.", "Draft an empathetic reply.", "Add next steps and links."], ["tone"], "https://www.helpscout.com/blog/"),
    ("Release Notes Publisher", "Writes customer-facing release notes from the technical changelog — benefit-led, grouped, and screenshot-ready.", ["release", "docs", "marketing"], ["Read the changelog.", "Translate changes into benefits.", "Group by theme.", "Add a short highlights intro."], ["audience"], "https://www.intercom.com/blog/"),
    ("GitOps Manifest Reviewer", "Reviews a GitOps PR (Argo/Flux) for drift, image pinning, and safe rollout strategy.", ["gitops", "kubernetes", "devops"], ["Diff desired vs. live state.", "Check image tag pinning.", "Verify rollout strategy.", "Flag risky changes."], ["tool"], "https://argo-cd.readthedocs.io"),
    ("Capacity Planner", "Estimates the resources a service needs from traffic projections, with headroom and a scaling trigger.", ["sre", "capacity", "infra"], ["Model traffic growth.", "Derive resource needs.", "Add headroom.", "Define autoscaling triggers."], ["horizon"], "https://sre.google/sre-book/software-engineering-in-sre/"),
    ("Backfill Script Writer", "Writes a safe, resumable backfill — batched, idempotent, throttled, and observable — for a data change.", ["data", "backend", "migrations"], ["Batch the work.", "Make each batch idempotent.", "Throttle to protect the DB.", "Log progress and allow resume."], ["table"], "https://stripe.com/blog/online-migrations"),
    ("OpenTelemetry Instrumenter", "Adds OpenTelemetry traces and metrics to a service, propagating context across boundaries.", ["observability", "tracing", "backend"], ["Add the SDK and exporter.", "Instrument inbound/outbound calls.", "Propagate context.", "Add key metrics."], ["language"], "https://opentelemetry.io/docs/"),
]

# NOTE entry: (title, description, [tags], intro, [(heading, text)])

TEAM_NOTES = [
    ("Incident Runbook", "The on-call playbook — severity definitions, comms cadence, escalation, and the post-mortem flow.", ["sre", "process", "oncall"], "How we run incidents. Blameless by default — the system failed, not the person.", [("Severities", "**SEV1** customer-facing outage — page the lead now. **SEV2** degraded, no data loss — 30-minute response. **SEV3** internal tooling — next business day."), ("Comms cadence", "Open `#inc-YYYYMMDD-name`, post an update every 30 minutes, and schedule the post-mortem within 48 hours of resolution."), ("Escalation", "On-call → secondary after 15 minutes unacked → engineering manager for SEV1 lasting over an hour.")]),
    ("Engineering Onboarding", "Day-one to week-one guide for new engineers — access, environment, first PR, and who to ask.", ["onboarding", "process", "people"], "Welcome. By the end of week one you'll have shipped a small PR to production.", [("Day one", "Get SSO, repo access, and your dev environment running from the README. Pair with your onboarding buddy."), ("First PR", "Pick a `good-first-issue`. Open a draft early, ask for a review at `effort=high`."), ("Who to ask", "Architecture → your tech lead. Infra → the platform pod. People stuff → your manager.")]),
    ("Code Review Checklist", "What a reviewer looks for before approving — correctness, tests, security, and readability.", ["code-review", "quality", "process"], "A consistent bar for every PR. Reviewers use this list; authors self-check against it first.", [("Correctness", "Does it do what the PR says? Are edge cases and error paths handled?"), ("Tests", "New behavior has tests. Bug fixes have a regression test."), ("Security", "No secrets, no injection, authz checked on every new endpoint."), ("Readability", "Names say what they mean. The diff reads like the code around it.")]),
    ("Branching Strategy", "How we use Git — trunk-based development, short-lived branches, and squash merges.", ["git", "process", "engineering"], "Trunk-based. Main is always releasable.", [("Branches", "Short-lived feature branches off main. Rebase, don't merge, to stay current."), ("Merging", "Squash merge with a Conventional Commits title. Delete the branch on merge."), ("Releases", "Tag main. No long-running release branches.")]),
    ("Release Process", "How a change goes from merged to production — the release train, checks, and rollback.", ["release", "process", "ci"], "We ship the train weekly, and any time for hotfixes.", [("The train", "Cut every Tuesday. The conductor runs the Release Train Conductor skill."), ("Gates", "Green CI, changelog updated, feature-flagged if user-facing."), ("Rollback", "Revert the deploy first, investigate second. Mean-time-to-recovery beats root cause in the moment.")]),
    ("Security Policy", "Baseline security expectations for every service — secrets, dependencies, and access.", ["security", "policy", "process"], "Security is everyone's job, not a gate at the end.", [("Secrets", "Never in code or logs. Use the secret manager; reference by name."), ("Dependencies", "Automated scanning on every PR. Patch criticals within 48 hours."), ("Access", "Least privilege. Review access quarterly. MFA everywhere.")]),
    ("Data Retention Policy", "What we keep, for how long, and how we delete it.", ["data", "policy", "privacy"], "Keep what we need, only as long as we need it.", [("Categories", "Operational logs 30 days, analytics events 13 months, account data until deletion."), ("Deletion", "Account deletion purges PII within 30 days across primary and backups."), ("Exceptions", "Legal holds override retention; document them.")]),
    ("API Design Guide", "Conventions for our HTTP APIs — naming, pagination, errors, and versioning.", ["api", "conventions", "backend"], "One vocabulary across every service.", [("Naming", "Plural nouns, kebab-case paths, camelCase JSON bodies."), ("Pagination", "Cursor-based: `?cursor=...&limit=50`, response carries `next_cursor`."), ("Errors", "Envelope `{ error: { code, message, status } }`. 4xx for client, 5xx for us."), ("Versioning", "Major version in the path: `/v1/...`. Additive changes don't bump it.")]),
    ("Naming Conventions", "How we name things across the codebase so reads are predictable.", ["conventions", "quality", "engineering"], "Boring, consistent names beat clever ones.", [("Code", "Functions are verbs, variables are nouns, booleans read as questions (`isReady`)."), ("Files", "kebab-case for modules, PascalCase for components."), ("Resources", "Singular table names, `_id` foreign keys, timestamps `created_at`/`updated_at`.")]),
    ("Testing Strategy", "What we test at each level and what 'done' means for tests.", ["testing", "quality", "process"], "Fast feedback first; confidence where it counts.", [("The pyramid", "Lots of unit tests, fewer integration, a thin layer of end-to-end."), ("Coverage", "We track it, we don't worship it. New logic ships with tests."), ("Flaky tests", "A flaky test is a broken test. Quarantine and fix within a sprint.")]),
    ("Observability Standards", "What every service emits — logs, metrics, and traces — and the golden signals we watch.", ["observability", "sre", "standards"], "If it's in production, it's observable.", [("Golden signals", "Latency, traffic, errors, saturation — dashboarded per service."), ("Logs", "Structured JSON, correlation IDs, no secrets."), ("Traces", "OpenTelemetry, sampled, propagated across service boundaries.")]),
    ("Secrets Management", "How we store, rotate, and access secrets safely.", ["security", "secrets", "ops"], "Secrets live in the manager, never in the repo.", [("Storage", "Cloud secret manager, referenced by name in config."), ("Rotation", "Rotate on a schedule and immediately on suspected exposure."), ("Access", "Scoped per service identity; audited.")]),
    ("Deployment Checklist", "The pre-deploy checklist for any production change.", ["deploy", "ops", "process"], "Run through this before every production deploy.", [("Before", "CI green, migrations reviewed, feature flag in place, rollback known."), ("During", "Watch error rate and latency for ten minutes."), ("After", "Update the changelog, close the ticket, note anything surprising.")]),
    ("Post-mortem Template", "The structure for a blameless incident review.", ["sre", "process", "template"], "Blameless. We're fixing the system, not assigning fault.", [("Summary", "What happened, impact, and duration in three sentences."), ("Timeline", "Detection → mitigation → resolution, with timestamps."), ("Root cause", "The chain of contributing factors, not a single culprit."), ("Action items", "Concrete, owned, and dated follow-ups.")]),
    ("Definition of Done", "What 'done' means before a ticket is closed.", ["process", "quality", "agile"], "Done means shippable, not 'works on my machine'.", [("Code", "Reviewed, tests passing, no TODOs left in."), ("Docs", "Updated where behavior changed."), ("Ops", "Observable, flagged if risky, rollback understood.")]),
    ("Database Conventions", "How we model and migrate data.", ["database", "conventions", "backend"], "Schemas are forever; design them like it.", [("Modeling", "Normalize first, denormalize with intent. UUID or prefixed string PKs."), ("Migrations", "Additive and backward-compatible; never drop in the same deploy that stops writing."), ("Indexes", "Index the columns you filter and join on; measure before adding.")]),
    ("Frontend Standards", "How we build UI — components, state, and accessibility.", ["frontend", "standards", "react"], "Accessible, consistent, and on-brand by default.", [("Components", "Small, typed, and composed. Lift state only as far as needed."), ("Styling", "Design tokens, no magic numbers. Dark mode is not optional."), ("Accessibility", "Keyboard-navigable, labeled, WCAG 2.2 AA contrast.")]),
    ("Git Commit Style", "How we write commit messages.", ["git", "conventions", "docs"], "Commits are documentation. Write them for the next reader.", [("Format", "Conventional Commits: `type(scope): subject`."), ("Subject", "Imperative, <=50 chars, no period."), ("Body", "Explain the why, wrap at 72, reference issues in the footer.")]),
    ("Feature Flag Guide", "How we use feature flags safely.", ["process", "deploy", "engineering"], "Flags decouple deploy from release.", [("When", "Any user-facing or risky change ships behind a flag."), ("Lifecycle", "Create with an owner and a removal date. Stale flags are tech debt."), ("Cleanup", "Remove the flag and the dead branch once the rollout is at 100%.")]),
    ("Customer Support Escalation", "When and how engineering gets pulled into a support issue.", ["support", "process", "ops"], "Most issues never reach engineering — these do.", [("Tiers", "Support handles known issues; engineering takes confirmed bugs and outages."), ("Escalation", "Reproducible bug → ticket with steps. Outage → incident channel."), ("Feedback loop", "Every escalation updates the support knowledge base.")]),
    ("Architecture Decision Records", "How and when we write ADRs to capture significant technical decisions.", ["architecture", "docs", "process"], "If a decision is hard to reverse, write it down.", [("When", "Any choice with long-term or cross-team impact gets an ADR."), ("Format", "Context, decision, consequences, and status (proposed/accepted/superseded)."), ("Lifecycle", "ADRs are immutable; supersede rather than edit.")]),
    ("Service Catalog", "The source of truth for what services exist, who owns them, and how to reach them.", ["ops", "ownership", "reference"], "Every running service has an owner and an on-call.", [("Entry", "Name, owner pod, on-call rotation, repo, dashboards, and runbooks."), ("Tiers", "Tier 1 customer-critical, Tier 2 important, Tier 3 internal."), ("Upkeep", "Reviewed each quarter; orphaned services are decommissioned.")]),
    ("Tech Radar", "Our shared view of which technologies to adopt, trial, hold, or retire.", ["architecture", "strategy", "reference"], "A living map of our technology choices.", [("Rings", "Adopt, Trial, Assess, Hold — with a one-line rationale each."), ("Process", "Proposals reviewed monthly by the architecture group."), ("Defaults", "When in doubt, use what's in Adopt.")]),
    ("Coding Style Guide", "Cross-language principles for readable, consistent code.", ["style", "quality", "engineering"], "Optimize for the reader, not the writer.", [("Principles", "Small functions, clear names, early returns, no clever one-liners."), ("Comments", "Explain why, not what. Delete commented-out code."), ("Formatting", "Auto-format on save; never argue about style a tool can settle.")]),
    ("PR Etiquette", "How authors and reviewers keep pull requests fast and kind.", ["code-review", "process", "people"], "Small PRs, fast reviews, kind comments.", [("Authors", "Keep PRs under ~400 lines. Describe the why. Self-review first."), ("Reviewers", "Respond within a business day. Ask, don't demand."), ("Tone", "Praise good code. Phrase nits as nits.")]),
    ("Meeting Norms", "How we keep meetings rare, short, and useful.", ["process", "people", "productivity"], "A meeting needs an agenda, an owner, and a decision.", [("Before", "No agenda, no meeting. Share pre-reads."), ("During", "Start on time, capture decisions and actions."), ("After", "Post notes within an hour. No notes, it didn't happen.")]),
    ("Remote Work Guide", "How we collaborate across time zones and locations.", ["people", "process", "remote"], "Default to async; protect deep work.", [("Async first", "Write decisions down. Don't block on a meeting."), ("Overlap", "Protect a few hours of shared overlap for live collaboration."), ("Presence", "Output over hours. Cameras optional.")]),
    ("Communication Norms", "Which channel to use for what, and expected response times.", ["people", "process", "comms"], "The right channel makes everyone faster.", [("Channels", "Chat for quick sync, docs for decisions, tickets for work, email for external."), ("Response", "Chat within hours, PRs within a day, no expectation outside work hours."), ("Urgency", "Use the incident path for anything truly urgent.")]),
    ("Career Ladder", "What growth looks like at each level, and how we evaluate it.", ["people", "growth", "process"], "Clear expectations make growth fair.", [("Levels", "Scope, autonomy, and impact grow at each level — defined explicitly."), ("Evaluation", "Against the level you're at, with concrete examples."), ("Promotion", "Demonstrate the next level consistently before the title changes.")]),
    ("Interview Process", "How we run a fair, consistent hiring loop.", ["hiring", "process", "people"], "Hire for ability to do the job, not for pedigree.", [("Loop", "Recruiter screen, technical, system/craft, and values conversation."), ("Rubric", "Score against a shared rubric; write evidence, not vibes."), ("Decision", "Debrief together; one strong no is a no.")]),
    ("Tech Debt Policy", "How we track, prioritize, and pay down technical debt.", ["engineering", "process", "quality"], "Debt is fine if it's tracked and intentional.", [("Tracking", "Tag debt tickets; link them from the code with a TODO."), ("Budget", "Reserve ~20% of capacity for debt and maintenance."), ("Escalation", "Debt that slows the team becomes a prioritized project.")]),
    ("Dependency Policy", "Rules for adding and maintaining third-party dependencies.", ["security", "dependencies", "policy"], "Every dependency is a liability you accept on purpose.", [("Adding", "Prefer the standard library; justify new deps in the PR."), ("Maintaining", "Automated updates; patch criticals within 48 hours."), ("Removing", "Drop unused and unmaintained packages promptly.")]),
    ("Open Source Policy", "How we contribute to and release open source.", ["legal", "open-source", "policy"], "We give back, within clear guardrails.", [("Contributing", "Allowed on your own time; check licenses and the CLA."), ("Releasing", "Get approval, choose a permissive license, scrub secrets and IP."), ("Maintaining", "Released projects need an owner and a support stance.")]),
    ("Accessibility Standards", "The accessibility bar every product surface must clear.", ["accessibility", "frontend", "standards"], "Accessible by default, not as a retrofit.", [("Target", "WCAG 2.2 AA across web surfaces."), ("Checks", "Keyboard navigation, labels, contrast, and focus order in every review."), ("Testing", "Automated axe checks in CI plus periodic manual audits.")]),
    ("Performance Budget", "The performance limits we hold the frontend to.", ["performance", "frontend", "standards"], "Speed is a feature; budgets keep it.", [("Budgets", "JS under 200KB gz, LCP under 2.5s, no layout shift over 0.1."), ("Enforcement", "CI fails a PR that blows the budget."), ("Review", "Re-baseline budgets each quarter.")]),
    ("Analytics Tracking Plan", "How we define, name, and govern product events.", ["data", "analytics", "process"], "Clean data starts with a tracking plan.", [("Naming", "object_action, snake_case, documented before instrumenting."), ("Properties", "Typed, with allowed values; no PII in event names."), ("Governance", "New events reviewed; the plan is the source of truth.")]),
    ("Privacy Checklist", "What to verify before shipping anything that touches user data.", ["privacy", "security", "policy"], "Privacy review is part of done.", [("Collection", "Collect the minimum; document purpose and retention."), ("Consent", "Get consent where required; honor deletion requests."), ("Sharing", "No third-party sharing without review and a DPA.")]),
    ("Disaster Recovery Plan", "How we recover from a major outage or data loss.", ["sre", "ops", "policy"], "Hope is not a recovery plan.", [("Objectives", "Documented RTO and RPO per critical service."), ("Backups", "Tested restores, not just successful backups."), ("Drills", "Run a recovery game day twice a year.")]),
    ("Backup Policy", "What we back up, how often, and how we verify it.", ["ops", "data", "policy"], "An untested backup is a guess.", [("Scope", "Databases and critical object storage, per the retention policy."), ("Cadence", "Daily snapshots, continuous WAL for primary databases."), ("Verification", "Automated monthly restore test into an isolated environment.")]),
    ("Cost Awareness Guide", "How engineers keep cloud spend sane day to day.", ["finops", "cloud", "engineering"], "Everyone owns a slice of the cloud bill.", [("Visibility", "Tag resources by service and owner; watch the dashboard."), ("Habits", "Right-size, turn off idle, prefer managed over bespoke."), ("Review", "Monthly cost review per pod; biggest movers get a look.")]),
    ("Tool Selection Guide", "How we evaluate and adopt a new tool or vendor.", ["process", "procurement", "strategy"], "New tools earn their place.", [("Criteria", "Need, fit, security posture, lock-in, and total cost."), ("Trial", "Time-boxed pilot with a clear success metric."), ("Decision", "Document the choice; revisit at renewal.")]),
    ("Definition of Ready", "What a ticket needs before the team starts it.", ["agile", "process", "planning"], "Ready means startable without a scavenger hunt.", [("Clarity", "Clear problem, acceptance criteria, and scope."), ("Dependencies", "Blockers identified and sequenced."), ("Sizing", "Estimated and small enough to finish in a sprint.")]),
    ("Code Ownership Map", "Who owns which areas of the codebase and reviews changes to them.", ["ownership", "process", "engineering"], "Every path has an owner.", [("Mapping", "CODEOWNERS routes reviews to the owning pod."), ("Responsibility", "Owners keep their area healthy, documented, and tested."), ("Handover", "Ownership changes are explicit, never implied.")]),
    ("Environments Guide", "What each environment is for and how code flows between them.", ["ops", "deploy", "process"], "Dev, staging, prod — and the rules that keep them honest.", [("Purpose", "Dev for building, staging mirrors prod, prod is sacred."), ("Promotion", "Same artifact promoted across envs; config differs, code doesn't."), ("Data", "Never copy prod PII into lower environments.")]),
]


ORGS = [
    ("org-official-mcp", "Official MCP", "official-mcp",
     "The reference Model Context Protocol servers and official vendor integrations — file access, search, databases, and the tools agents reach for first.",
     "MCP", OFFICIAL_MCP),
    ("org-official-skills", "Official Skills", "official-skills",
     "Battle-tested agent skills for everyday engineering — reviews, tests, docs, refactors, and the writing tasks every team repeats.",
     "SKILL", OFFICIAL_SKILLS),
    ("org-awesome-mcp", "Awesome MCP Servers", "awesome-mcp",
     "A curated marketplace of community MCP servers connecting agents to databases, browsers, SaaS tools, and the rest of your stack.",
     "MCP", COMMUNITY_MCP),
    ("org-agent-skills", "Agent Skills Hub", "agent-skills",
     "Skills for DevOps, data, and delivery — Dockerfiles to dbt models, incident triage to RFCs. The toolbox for shipping with agents.",
     "SKILL", AGENT_SKILLS),
    ("org-team-playbooks", "Team Playbooks", "team-playbooks",
     "The institutional memory every team needs — runbooks, onboarding, conventions, and policies, ready to inherit org-wide.",
     "NOTE", TEAM_NOTES),
]


def build_resources(org_id: str, kind: str, catalog: list, author_id: str) -> list[Resource]:
    out: list[Resource] = []
    for entry in catalog:
        if kind == "MCP":
            title, key, runtime, pkg, env_keys, desc, tags, source = entry
            rid = f"res-{org_id[4:]}-{slugify(title)}"
            stars, installs = counts(rid)
            out.append(Resource(
                id=rid, type="MCP", title=title, description=desc,
                content_md=mcp_md(title, key, runtime, pkg, desc, env_keys, source),
                server_url=None, config_json=mcp_config(key, runtime, pkg, env_keys, []),
                version=version_for(rid), tags=tags,
                attachments=[{"kind": "link", "url": source, "title": "Source", "caption": None}],
                scope_type="ORG", scope_id=org_id, author_id=author_id, is_public=True,
                stars_count=stars, installs_count=installs,
            ))
        elif kind == "SKILL":
            title, desc, tags, steps, inputs, source = entry
            rid = f"res-{org_id[4:]}-{slugify(title)}"
            stars, installs = counts(rid)
            out.append(Resource(
                id=rid, type="SKILL", title=title, description=desc,
                content_md=skill_md(title, desc, steps, inputs, source),
                file_url=f"https://cdn.skillshare.think41.com/packages/{slugify(title)}-{version_for(rid)}.skill",
                version=version_for(rid), tags=tags,
                attachments=[{"kind": "link", "url": source, "title": "Reference", "caption": None}],
                scope_type="ORG", scope_id=org_id, author_id=author_id, is_public=True,
                stars_count=stars, installs_count=installs,
            ))
        else:  # NOTE
            title, desc, tags, intro, sections = entry
            rid = f"res-{org_id[4:]}-{slugify(title)}"
            stars, installs = counts(rid)
            out.append(Resource(
                id=rid, type="NOTE", title=title, description=desc,
                content_md=note_md(title, intro, sections),
                version=version_for(rid), tags=tags,
                scope_type="ORG", scope_id=org_id, author_id=author_id, is_public=True,
                stars_count=stars, installs_count=installs,
            ))
    return out


def reset(db, owner_id: str) -> None:
    org_ids = [o[0] for o in ORGS]
    n_res = db.query(Resource).filter(Resource.scope_id.in_(org_ids)).delete(synchronize_session=False)
    db.query(OrgMember).filter(OrgMember.org_id.in_(org_ids)).delete(synchronize_session=False)
    n_org = db.query(Organization).filter(Organization.id.in_(org_ids)).delete(synchronize_session=False)
    db.commit()
    print(f"Reset: removed {n_org} showcase orgs and {n_res} resources.")


def main() -> None:
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.email == OWNER_EMAIL).first()
        if not owner:
            print(f"ERROR: owner {OWNER_EMAIL} not found.")
            sys.exit(1)
        if not owner.is_publisher:
            owner.is_publisher = True
            db.commit()
            print(f"Marked {OWNER_EMAIL} as a publisher.")

        if "--reset" in sys.argv:
            reset(db, owner.id)

        total = 0
        for org_id, name, slug, desc, kind, catalog in ORGS:
            org = db.get(Organization, org_id)
            if not org:
                db.add(Organization(id=org_id, name=name, slug=slug, description=desc,
                                    is_public=True, owner_id=owner.id, plan="PREMIUM"))
                db.commit()  # commit org first — no ORM relationship declares the FK order
                print(f"Created org: {name} ({slug})")
            # ensure owner is an ADMIN member
            if not db.query(OrgMember).filter(OrgMember.org_id == org_id, OrgMember.user_id == owner.id).first():
                db.add(OrgMember(org_id=org_id, user_id=owner.id, role="ADMIN"))
                db.commit()

            resources = build_resources(org_id, kind, catalog, owner.id)
            added = 0
            for r in resources:
                if not db.get(Resource, r.id):
                    db.add(r)
                    added += 1
            db.commit()
            total += added
            print(f"  {name}: +{added} resources (catalog has {len(catalog)})")

        pub = db.query(Resource).filter(Resource.is_public.is_(True)).count()
        print(f"\nDone. Added {total} new resources. Marketplace now has {pub} public resources.")
        print(f"Owner of all 5 orgs: {OWNER_EMAIL} ({owner.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
