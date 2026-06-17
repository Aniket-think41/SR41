"""GitHub-URL ingestion (server-side).

Given a public GitHub URL, fetch the repo over the GitHub REST API (no clone) and
detect the skill(s) / MCP server(s) / note(s) inside it, following the ecosystem
conventions:

  * SKILL  — any ``SKILL.md`` (root, ``skills/*/SKILL.md``, ``.claude/skills/*``,
             or under a plugin's ``skills/``). YAML frontmatter → name/description.
  * MCP    — ``server.json`` (MCP Registry format) and ``.mcp.json`` / ``mcp.json``
             ``mcpServers`` blocks (one MCP resource per server key).
  * NOTE   — fallback: ``README.md`` becomes a note when nothing else is found.

The network layer is a small injectable ``Fetcher`` protocol so detection is unit
-testable with an in-memory fake and **no network**. This module is self-contained:
it does not import the separate CLI integration package.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .errors import not_found, validation

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

# Only these files are ever fetched raw — we never download the whole repo.
_SKILL_RE = re.compile(r"(^|/)SKILL\.md$", re.IGNORECASE)
_MCP_JSON_RE = re.compile(r"(^|/)(\.mcp\.json|mcp\.json)$", re.IGNORECASE)
_SERVER_JSON_RE = re.compile(r"(^|/)server\.json$", re.IGNORECASE)
_MARKETPLACE_RE = re.compile(r"\.claude-plugin/marketplace\.json$", re.IGNORECASE)
_README_RE = re.compile(r"(^|/)README\.md$", re.IGNORECASE)


# ----------------------------- URL parsing -----------------------------

@dataclass
class GitHubRef:
    owner: str
    repo: str
    ref: str | None = None       # branch / tag / sha (None → repo default branch)
    subpath: str | None = None   # narrow detection to this dir, or a single file


def parse_github_url(url: str) -> GitHubRef:
    """Parse the URL forms we accept into an (owner, repo, ref, subpath) ref.

    Accepts ``https://github.com/o/r``, ``…/tree/<ref>/<sub>``,
    ``…/blob/<ref>/<path>``, a trailing ``.git``, and the ``o/r`` shorthand.
    """
    raw = (url or "").strip()
    if not raw:
        raise validation("A GitHub URL is required")

    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/(.+)$", raw, re.IGNORECASE)
    path = m.group(1) if m else raw  # bare "owner/repo" shorthand
    path = path.strip("/")
    parts = path.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise validation("Not a GitHub repository URL (expected github.com/owner/repo)")

    owner, repo = parts[0], parts[1]
    repo = re.sub(r"\.git$", "", repo)
    ref: str | None = None
    subpath: str | None = None
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        ref = parts[3]
        if len(parts) > 4:
            subpath = "/".join(parts[4:])
    return GitHubRef(owner=owner, repo=repo, ref=ref, subpath=subpath)


# ----------------------------- fetching -----------------------------

class Fetcher(Protocol):
    def meta(self) -> dict: ...
    def tree(self, ref: str) -> list[str]: ...
    def raw(self, ref: str, path: str) -> str | None: ...


class HttpFetcher:
    """Default fetcher backed by the public (unauthenticated) GitHub API + raw CDN."""

    def __init__(self, owner: str, repo: str):
        self.owner = owner
        self.repo = repo

    def _client(self):
        import httpx  # already a backend dependency (requirements.txt)

        return httpx.Client(
            timeout=15.0,
            headers={
                "User-Agent": "skillshare-registry",
                "Accept": "application/vnd.github+json",
            },
            follow_redirects=True,
        )

    def meta(self) -> dict:
        import httpx

        with self._client() as c:
            r = c.get(f"{GITHUB_API}/repos/{self.owner}/{self.repo}")
        if r.status_code == 404:
            raise not_found("GitHub repository (is it public?)")
        if r.status_code == 403:
            raise validation("GitHub rate limit hit — try again in a minute")
        if r.status_code >= 400:
            raise validation(f"GitHub returned {r.status_code} for that repository")
        data = r.json()
        return {
            "default_branch": data.get("default_branch") or "main",
            "description": data.get("description") or "",
            "topics": data.get("topics") or [],
            "html_url": data.get("html_url") or f"https://github.com/{self.owner}/{self.repo}",
        }

    def tree(self, ref: str) -> list[str]:
        with self._client() as c:
            r = c.get(f"{GITHUB_API}/repos/{self.owner}/{self.repo}/git/trees/{ref}?recursive=1")
        if r.status_code >= 400:
            raise validation(f"Could not read the repository tree (HTTP {r.status_code})")
        data = r.json()
        return [n["path"] for n in data.get("tree", []) if n.get("type") == "blob"]

    def raw(self, ref: str, path: str) -> str | None:
        with self._client() as c:
            r = c.get(f"{GITHUB_RAW}/{self.owner}/{self.repo}/{ref}/{path}")
        return r.text if r.status_code == 200 else None


# ----------------------------- redaction (compact) -----------------------------
# Mirrors backend/integration/cli/.../local/redact.py so MCP configs from a repo
# never carry real secrets into the registry. Kept compact + self-contained.

_SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"client[_-]?secret|auth|authorization|bearer|private[_-]?key|"
    r"connection[_-]?string|dsn|credential)"
)
_VALUE_PATTERNS = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("url_creds", re.compile(r"\b([a-z][a-z0-9+.\-]*://)[^\s/@:]+:[^\s/@]+@")),
]
_PLACEHOLDER = "${REDACTED}"


def _redact_text(text: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    out = text
    for label, pat in _VALUE_PATTERNS:
        if label == "url_creds":
            def _u(m: re.Match) -> str:
                findings.append("url_creds")
                return f"{m.group(1)}${{REDACTED}}@"
            out = pat.sub(_u, out)
            continue

        def _r(_m: re.Match, _label=label) -> str:
            findings.append(_label)
            return _PLACEHOLDER

        out = pat.sub(_r, out)
    return out, findings


def _redact_obj(obj, _key: str | None = None):
    findings: list[str] = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and _SECRET_KEY_RE.search(str(k)):
                out[k] = _PLACEHOLDER
                findings.append(str(k))
            else:
                rv, f = _redact_obj(v, k)
                out[k] = rv
                findings.extend(f)
        return out, findings
    if isinstance(obj, list):
        out_list = []
        for v in obj:
            rv, f = _redact_obj(v, _key)
            out_list.append(rv)
            findings.extend(f)
        return out_list, findings
    if isinstance(obj, str):
        if _key and _SECRET_KEY_RE.search(str(_key)):
            findings.append(str(_key))
            return _PLACEHOLDER, findings
        return _redact_text(obj)
    return obj, findings


# ----------------------------- detected resource -----------------------------

@dataclass
class DetectedResource:
    kind: str                       # skill | mcp | note
    title: str
    description: str = ""
    content_md: str = ""
    server_url: str | None = None
    config_json: str | None = None
    tags: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    source_path: str = ""           # path within the repo (provenance/UI)
    fingerprint: str = ""
    redaction: list[str] = field(default_factory=list)

    @property
    def type(self) -> str:
        return {"skill": "SKILL", "mcp": "MCP", "note": "NOTE"}[self.kind]

    def to_create_payload(self, scope_type: str, scope_id: str | None) -> dict:
        return {
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "content_md": self.content_md,
            "server_url": self.server_url,
            "config_json": self.config_json,
            "tags": list(self.tags),
            "attachments": list(self.attachments),
            "scope_type": scope_type,
            "scope_id": scope_id,
            "source_fingerprint": self.fingerprint,
        }

    def preview(self) -> dict:
        """Compact shape for the preview endpoint / CLI / MCP."""
        return {
            "kind": self.kind,
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "source_path": self.source_path,
            "fingerprint": self.fingerprint,
            "redaction": list(self.redaction),
            "server_url": self.server_url,
            "has_config": bool(self.config_json),
            "content_preview": (self.content_md or "")[:500],
            "attachments": list(self.attachments),
        }


# ----------------------------- parsing helpers -----------------------------

def _h1(text: str) -> str | None:
    m = re.search(r"^\s*#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip("\"'")
    return out


def _fingerprint(ref: GitHubRef, path: str, content: str) -> str:
    h = hashlib.sha256()
    h.update(f"github:{ref.owner}/{ref.repo}:{path}\n".encode())
    h.update(content.encode("utf-8", errors="replace"))
    return f"fp_{h.hexdigest()[:24]}"


def _github_link(ref: GitHubRef, ref_name: str, path: str) -> dict:
    url = f"https://github.com/{ref.owner}/{ref.repo}/blob/{ref_name}/{path}"
    return {"kind": "link", "url": url, "title": "Source on GitHub", "caption": path}


def _server_json_to_config(name: str, doc: dict) -> tuple[str, str | None]:
    """Turn an MCP Registry server.json into a Claude-style mcpServers config_json
    and a best-effort server_url. Returns (config_json, server_url)."""
    server: dict = {}
    server_url: str | None = None

    remotes = doc.get("remotes") or []
    if isinstance(remotes, list) and remotes:
        r0 = remotes[0] if isinstance(remotes[0], dict) else {}
        server_url = r0.get("url")
        server = {"type": r0.get("type") or "streamable-http", "url": server_url}
    else:
        pkgs = doc.get("packages") or []
        p0 = pkgs[0] if (isinstance(pkgs, list) and pkgs and isinstance(pkgs[0], dict)) else {}
        registry = (p0.get("registryType") or p0.get("registry_type") or "").lower()
        identifier = p0.get("identifier") or p0.get("name") or name
        runtime = (p0.get("runtimeHint") or p0.get("runtime_hint") or "").lower()
        if registry == "pypi" or runtime == "uvx":
            server = {"command": "uvx", "args": [identifier]}
        elif registry == "oci":
            server = {"command": "docker", "args": ["run", "-i", "--rm", identifier]}
        else:  # npm / default
            server = {"command": "npx", "args": ["-y", identifier]}

    config = {"mcpServers": {name: server}}
    return json.dumps(config, indent=2), server_url


def _short_name(full: str) -> str:
    """`io.github.user/my-server` → `my-server`; otherwise the trailing segment."""
    tail = full.split("/")[-1]
    return tail or full


# ----------------------------- detection -----------------------------

def detect(ref: GitHubRef, fetcher: Fetcher) -> tuple[list[DetectedResource], dict]:
    """Return (detected resources, repo meta). Pure given the fetcher."""
    meta = fetcher.meta()
    ref_name = ref.ref or meta["default_branch"]
    topics = list(meta.get("topics") or [])
    paths = fetcher.tree(ref_name)

    if ref.subpath:
        prefix = ref.subpath.rstrip("/")
        # a single file (e.g. blob → SKILL.md) or a directory prefix
        paths = [p for p in paths if p == prefix or p.startswith(prefix + "/")]

    found: list[DetectedResource] = []
    seen: set[str] = set()

    def _add(d: DetectedResource) -> None:
        if d.fingerprint in seen:
            return
        seen.add(d.fingerprint)
        found.append(d)

    # --- skills ---
    for p in paths:
        if not _SKILL_RE.search(p):
            continue
        text = fetcher.raw(ref_name, p)
        if not text:
            continue
        fm = _frontmatter(text)
        folder = p.rsplit("/", 2)[-2] if "/" in p else ref.repo
        title = fm.get("name") or _h1(text) or folder
        body, red = _redact_text(text)
        _add(DetectedResource(
            kind="skill", title=title, description=fm.get("description", ""),
            content_md=body, tags=topics[:6],
            attachments=[_github_link(ref, ref_name, p)],
            source_path=p, fingerprint=_fingerprint(ref, p, text), redaction=sorted(set(red)),
        ))

    # --- MCP from server.json (MCP Registry format) ---
    for p in paths:
        if not _SERVER_JSON_RE.search(p):
            continue
        text = fetcher.raw(ref_name, p)
        if not text:
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        if not isinstance(doc, dict) or "name" not in doc:
            continue  # not an MCP server.json
        full = str(doc.get("name"))
        name = _short_name(full)
        config_json, server_url = _server_json_to_config(name, doc)
        red_doc, red = _redact_obj(json.loads(config_json))
        _add(DetectedResource(
            kind="mcp", title=doc.get("title") or name,
            description=doc.get("description", ""),
            server_url=server_url, config_json=json.dumps(red_doc, indent=2),
            tags=topics[:6], attachments=[_github_link(ref, ref_name, p)],
            source_path=p, fingerprint=_fingerprint(ref, p, config_json),
            redaction=sorted(set(red)),
        ))

    # --- MCP from .mcp.json / mcp.json (Claude-style mcpServers) ---
    for p in paths:
        if not _MCP_JSON_RE.search(p):
            continue
        text = fetcher.raw(ref_name, p)
        if not text:
            continue
        try:
            doc = json.loads(text)
        except ValueError:
            continue
        servers = doc.get("mcpServers") if isinstance(doc, dict) else None
        if not isinstance(servers, dict):
            continue
        for name, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            raw = {"mcpServers": {name: cfg}}
            red_doc, red = _redact_obj(raw)
            _add(DetectedResource(
                kind="mcp", title=name,
                description=cfg.get("command") or cfg.get("url") or "",
                server_url=cfg.get("url"),
                config_json=json.dumps(red_doc, indent=2),
                tags=topics[:6], attachments=[_github_link(ref, ref_name, p)],
                source_path=f"{p}#{name}",
                fingerprint=_fingerprint(ref, f"{p}#{name}", json.dumps(raw, sort_keys=True)),
                redaction=sorted(set(red)),
            ))

    # --- NOTE fallback (only when nothing else surfaced) ---
    if not found:
        readme = next((p for p in paths if _README_RE.search(p)), None)
        text = fetcher.raw(ref_name, readme) if readme else None
        if text:
            body, red = _redact_text(text)
            _add(DetectedResource(
                kind="note", title=_h1(text) or ref.repo,
                description=meta.get("description", ""), content_md=body,
                tags=topics[:6],
                attachments=[{"kind": "link", "url": meta.get("html_url", ""),
                              "title": "Repository", "caption": f"{ref.owner}/{ref.repo}"}],
                source_path=readme, fingerprint=_fingerprint(ref, readme, text),
                redaction=sorted(set(red)),
            ))

    return found, meta


def detect_from_url(url: str, fetcher_factory: Callable[[GitHubRef], Fetcher] | None = None):
    """Convenience: parse the URL, build a fetcher, run detection.

    ``fetcher_factory`` is injectable for tests; defaults to the real HttpFetcher.
    """
    ref = parse_github_url(url)
    factory = fetcher_factory or (lambda r: HttpFetcher(r.owner, r.repo))
    found, meta = detect(ref, factory(ref))
    return ref, found, meta
