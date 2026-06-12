"""
skillshare — command-line client for the SkillShare registry.

Auth (BACKEND_SPEC §10): `skillshare login` exchanges email+password for a
Personal Access Token (skst_…) and stores it in
~/.config/skillshare/credentials.json (chmod 600). `SKILLSHARE_TOKEN` /
`SKILLSHARE_API_URL` env vars override the stored config (useful in CI).

    skillshare login                          interactive login, mints a PAT
    skillshare whoami / orgs / tokens         account
    skillshare search "code review" --type SKILL
    skillshare get pr-reviewer                full resource detail
    skillshare pull pr-reviewer -o ./skills   save SKILL.md / config / note
    skillshare list --org think41             org resources
    skillshare list --pod pod-retrieval       pod library incl. inherited
    skillshare add note --org think41 --title "..." -f notes.md
    skillshare star <id> / publish <id> / import <id> --org <slug>
"""

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

import httpx

CONFIG_DIR = Path(os.environ.get("SKILLSHARE_CONFIG_DIR", "~/.config/skillshare")).expanduser()
CREDS_FILE = CONFIG_DIR / "credentials.json"
DEFAULT_API = "http://localhost:8400"

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GLYPH = {"SKILL": "◆", "MCP": "▣", "NOTE": "▤"}


def _load_creds() -> dict:
    try:
        return json.loads(CREDS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_creds(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(json.dumps(data, indent=2))
    CREDS_FILE.chmod(0o600)


def api_url() -> str:
    return (os.environ.get("SKILLSHARE_API_URL") or _load_creds().get("api_url") or DEFAULT_API).rstrip("/")


def token() -> str | None:
    return os.environ.get("SKILLSHARE_TOKEN") or _load_creds().get("token")


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def request(method: str, path: str, *, body: dict | None = None, params: dict | None = None, auth: bool = True):
    headers = {}
    if auth:
        t = token()
        if not t:
            die("not logged in — run `skillshare login` (or set SKILLSHARE_TOKEN)")
        headers["Authorization"] = f"Bearer {t}"
    try:
        res = httpx.request(method, f"{api_url()}{path}", json=body, params=params, headers=headers, timeout=30)
    except httpx.HTTPError as e:
        die(f"cannot reach {api_url()} — is the API running? ({e.__class__.__name__})")
    if res.status_code >= 400:
        try:
            err = res.json()["error"]
            die(f"{err['code']}: {err['message']}")
        except (KeyError, ValueError):
            die(f"HTTP {res.status_code}: {res.text[:200]}")
    return res.json() if res.text else None


def print_resources(rows: list[dict]) -> None:
    if not rows:
        print(f"{DIM}no resources{RESET}")
        return
    for r in rows:
        scope = r.get("scope_label") or r["scope_type"]
        author = (r.get("author") or {}).get("username", "?")
        pub = " 🌐" if r.get("is_public") else ""
        print(
            f"{GLYPH.get(r['type'], '·')} {BOLD}{r['title']}{RESET} {DIM}v{r['version']}{RESET}"
            f"  [{r['id']}]  {DIM}{scope.lower()} · @{author} · ★{r['stars_count']}{pub}{RESET}"
        )
        if r.get("description"):
            print(f"    {r['description'][:100]}")


# ---------------- commands ----------------

def cmd_login(args) -> None:
    url = (args.api or input(f"API URL [{api_url()}]: ").strip() or api_url()).rstrip("/")
    email = args.email or input("Email: ").strip()
    password = getpass.getpass("Password: ")
    res = httpx.post(f"{url}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if res.status_code >= 400:
        die(res.json().get("error", {}).get("message", f"login failed (HTTP {res.status_code})"))
    jwt = res.json()["access_token"]
    # mint a long-lived PAT with the short-lived JWT
    name = f"cli@{os.uname().nodename}" if hasattr(os, "uname") else "cli"
    pat = httpx.post(
        f"{url}/api/auth/tokens",
        json={"name": name},
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=30,
    ).json()
    _save_creds({"api_url": url, "token": pat["token"], "token_id": pat["id"], "email": email})
    user = res.json()["user"]
    print(f"Logged in as {BOLD}@{user['username']}{RESET} — token \"{name}\" stored in {CREDS_FILE}")


def cmd_logout(_args) -> None:
    creds = _load_creds()
    if creds.get("token_id") and creds.get("token"):
        try:
            request("DELETE", f"/api/auth/tokens/{creds['token_id']}")
            print("Token revoked on the server.")
        except SystemExit:
            print("Could not revoke remotely — removing local credentials anyway.", file=sys.stderr)
    if CREDS_FILE.exists():
        CREDS_FILE.unlink()
    print("Logged out.")


def cmd_whoami(_args) -> None:
    u = request("GET", "/api/auth/me")
    print(f"{BOLD}{u['display_name']}{RESET} (@{u['username']}) — {u['email']}")
    print(f"{DIM}publisher: {'yes' if u['is_publisher'] else 'no'} · api: {api_url()}{RESET}")


def cmd_orgs(_args) -> None:
    for o in request("GET", "/api/orgs"):
        print(f"{BOLD}{o['name']}{RESET}  {DIM}{o['slug']} · {o['my_role']} · {o['plan']}{RESET}")


def cmd_tokens(_args) -> None:
    for t in request("GET", "/api/auth/tokens"):
        last = str(t["last_used_at"] or "never")[:19]
        print(f"{t['token_prefix']}…  {BOLD}{t['name']}{RESET}  {DIM}[{t['id']}] last used {last}{RESET}")


def cmd_search(args) -> None:
    params = {"q": args.query, "sort": args.sort}
    if args.type:
        params["type"] = args.type.upper()
    if args.tag:
        params["tag"] = args.tag
    print_resources(request("GET", "/api/public/resources", params=params, auth=False))


def attachments_md(r) -> str:
    """Render typed attachments as a portable '## Resources' markdown section
    (hybrid content model — content_md stays canonical, this appends media)."""
    items = r.get("attachments") or []
    if not items:
        return ""
    lines = ["", "## Resources", ""]
    for a in items:
        title = a.get("title") or a.get("url")
        cap = f" — {a['caption']}" if a.get("caption") else ""
        lines.append(f"- **{a.get('kind', 'link')}**: [{title}]({a['url']}){cap}")
    return "\n".join(lines) + "\n"


def cmd_get(args) -> None:
    path = f"/api/resources/{args.id}" if token() else f"/api/public/resources/{args.id}"
    r = request("GET", path, auth=bool(token()))
    author = (r.get("author") or {}).get("username", "?")
    print(f"{GLYPH.get(r['type'], '·')} {BOLD}{r['title']}{RESET} v{r['version']}  {DIM}{r['type']} · @{author} · ★{r['stars_count']}{RESET}")
    print(f"{DIM}{r['description']}{RESET}\n")
    if r["type"] == "MCP":
        if r.get("server_url"):
            print(f"{BOLD}server url:{RESET} {r['server_url']}")
        if r.get("config_json"):
            print(f"{BOLD}config:{RESET}\n{r['config_json']}")
        if r.get("content_md"):
            print(f"\n{r['content_md']}")
    else:
        print(r.get("content_md") or "(no content)")
    section = attachments_md(r)
    if section:
        print(section)


def cmd_pull(args) -> None:
    path = f"/api/resources/{args.id}" if token() else f"/api/public/resources/{args.id}"
    r = request("GET", path, auth=bool(token()))
    out = Path(args.output).expanduser()
    slug = re.sub(r"[^a-z0-9]+", "-", r["title"].lower()).strip("-")
    target = out / slug
    target.mkdir(parents=True, exist_ok=True)
    if r["type"] == "SKILL":
        (target / "SKILL.md").write_text((r.get("content_md") or "") + attachments_md(r))
        print(f"wrote {target / 'SKILL.md'}")
        if r.get("file_url"):
            print(f"{DIM}package: {r['file_url']} (download manually or via the dashboard){RESET}")
    elif r["type"] == "MCP":
        cfg = r.get("config_json") or "{}"
        (target / "mcp-config.json").write_text(cfg)
        print(f"wrote {target / 'mcp-config.json'}")
        if r.get("attachments"):
            (target / "README.md").write_text((r.get("content_md") or "") + attachments_md(r))
            print(f"wrote {target / 'README.md'}")
    else:
        (target / f"{slug}.md").write_text((r.get("content_md") or "") + attachments_md(r))
        print(f"wrote {target / (slug + '.md')}")


def cmd_list(args) -> None:
    params = {}
    if args.query:
        params["q"] = args.query
    if args.type:
        params["type"] = args.type.upper()
    if args.pod:
        params["scope"] = args.scope
        rows = request("GET", f"/api/pods/{args.pod}/resources", params=params)
    elif args.org:
        rows = request("GET", f"/api/orgs/{args.org}/resources", params=params)
    else:
        die("provide --org <slug> or --pod <id>")
    print_resources(rows)


def cmd_add_note(args) -> None:
    content = Path(args.file).read_text() if args.file else sys.stdin.read()
    if args.pod:
        scope = {"scope_type": "POD", "scope_id": args.pod}
    elif args.org:
        org = request("GET", f"/api/orgs/{args.org}")
        scope = {"scope_type": "ORG", "scope_id": org["id"]}
    else:
        die("provide --org <slug> or --pod <id>")
    r = request(
        "POST",
        "/api/resources",
        body={
            "type": "NOTE",
            "title": args.title,
            "description": args.description or "",
            "content_md": content,
            "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
            **scope,
        },
    )
    print(f"created {BOLD}{r['title']}{RESET} [{r['id']}] in {r['scope_type'].lower()} scope")


def cmd_star(args) -> None:
    r = request("POST", f"/api/resources/{args.id}/star")
    print(f"★ starred {BOLD}{r['title']}{RESET} ({r['stars_count']} stars)")


def cmd_publish(args) -> None:
    r = request("POST", f"/api/resources/{args.id}/publish")
    print(f"🌐 published {BOLD}{r['title']}{RESET} to the public marketplace")


def cmd_import(args) -> None:
    r = request("POST", f"/api/resources/{args.id}/import", body={"org_slug": args.org})
    print(f"imported {BOLD}{r['title']}{RESET} into {args.org} [{r['id']}]")


def main() -> None:
    p = argparse.ArgumentParser(prog="skillshare", description="SkillShare registry CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("login", help="log in and store a personal access token")
    sp.add_argument("--api", help=f"API base URL (default {DEFAULT_API})")
    sp.add_argument("--email")
    sp.set_defaults(fn=cmd_login)

    sub.add_parser("logout", help="revoke the stored token and remove credentials").set_defaults(fn=cmd_logout)
    sub.add_parser("whoami", help="show the authenticated user").set_defaults(fn=cmd_whoami)
    sub.add_parser("orgs", help="list my organizations").set_defaults(fn=cmd_orgs)
    sub.add_parser("tokens", help="list my personal access tokens").set_defaults(fn=cmd_tokens)

    sp = sub.add_parser("search", help="search the public marketplace")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--type", choices=["skill", "mcp", "note", "SKILL", "MCP", "NOTE"])
    sp.add_argument("--tag")
    sp.add_argument("--sort", default="stars", choices=["stars", "installs", "newest", "updated"])
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("get", help="show a resource's full content")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_get)

    sp = sub.add_parser("pull", help="save a resource locally (SKILL.md / mcp-config.json / note.md)")
    sp.add_argument("id")
    sp.add_argument("-o", "--output", default=".", help="output directory (default .)")
    sp.set_defaults(fn=cmd_pull)

    sp = sub.add_parser("list", help="list org or pod resources (incl. inherited)")
    sp.add_argument("--org", help="org slug")
    sp.add_argument("--pod", help="pod id")
    sp.add_argument("--scope", default="all", choices=["all", "pod", "project", "org"])
    sp.add_argument("--type", choices=["skill", "mcp", "note", "SKILL", "MCP", "NOTE"])
    sp.add_argument("-q", "--query", default="")
    sp.set_defaults(fn=cmd_list)

    add = sub.add_parser("add", help="create a resource").add_subparsers(dest="kind", required=True)
    sp = add.add_parser("note", help="create a NOTE from a file or stdin")
    sp.add_argument("--title", required=True)
    sp.add_argument("--org", help="org slug (org-level note)")
    sp.add_argument("--pod", help="pod id (pod-level note)")
    sp.add_argument("-f", "--file", help="markdown file (default: read stdin)")
    sp.add_argument("--description")
    sp.add_argument("--tags", help="comma-separated")
    sp.set_defaults(fn=cmd_add_note)

    sp = sub.add_parser("star", help="star a resource")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_star)

    sp = sub.add_parser("publish", help="publish a resource to the marketplace")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_publish)

    sp = sub.add_parser("import", help="copy a public resource into your org")
    sp.add_argument("id")
    sp.add_argument("--org", required=True, help="target org slug")
    sp.set_defaults(fn=cmd_import)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
