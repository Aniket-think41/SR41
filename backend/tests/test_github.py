"""Unit tests for GitHub-URL ingestion detection (app/github.py).

Detection is driven by an in-memory FakeFetcher — no network. Run with:
    cd backend && .venv/bin/python -m pytest tests -q
or standalone:
    cd backend && .venv/bin/python tests/test_github.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.github import (  # noqa: E402
    GitHubRef,
    detect,
    parse_github_url,
)


class FakeFetcher:
    def __init__(self, files, default_branch="main", description="", topics=None):
        self.files = files
        self._meta = {
            "default_branch": default_branch,
            "description": description,
            "topics": topics or [],
            "html_url": "https://github.com/o/r",
        }

    def meta(self):
        return dict(self._meta)

    def tree(self, ref):
        return list(self.files.keys())

    def raw(self, ref, path):
        return self.files.get(path)


REF = GitHubRef(owner="o", repo="r")


# ----------------------------- URL parsing -----------------------------

def test_parse_url_variants():
    assert parse_github_url("https://github.com/anthropics/skills") == GitHubRef("anthropics", "skills")
    assert parse_github_url("github.com/anthropics/skills.git") == GitHubRef("anthropics", "skills")
    assert parse_github_url("anthropics/skills") == GitHubRef("anthropics", "skills")
    r = parse_github_url("https://github.com/o/r/tree/dev/skills/foo")
    assert (r.ref, r.subpath) == ("dev", "skills/foo")
    b = parse_github_url("https://github.com/o/r/blob/main/SKILL.md")
    assert (b.ref, b.subpath) == ("main", "SKILL.md")

    for bad in ("", "https://gitlab.com/o/r", "https://github.com/onlyowner"):
        try:
            parse_github_url(bad)
            assert False, f"expected rejection for {bad!r}"
        except Exception:
            pass


# ----------------------------- skills -----------------------------

def test_root_skill_with_frontmatter():
    md = "---\nname: PR Reviewer\ndescription: Reviews pull requests\n---\n# PR Reviewer\nBody."
    found, _ = detect(REF, FakeFetcher({"SKILL.md": md}, topics=["ci", "review"]))
    assert len(found) == 1
    s = found[0]
    assert s.type == "SKILL" and s.title == "PR Reviewer"
    assert s.description == "Reviews pull requests"
    assert "Body." in s.content_md
    assert s.tags == ["ci", "review"]
    assert s.attachments and s.attachments[0]["kind"] == "link"
    assert s.fingerprint.startswith("fp_")


def test_multiple_skills_in_skills_dir():
    files = {
        "skills/alpha/SKILL.md": "# Alpha\nalpha",
        "skills/beta/SKILL.md": "# Beta\nbeta",
        ".claude/skills/gamma/SKILL.md": "---\nname: Gamma\n---\ngamma",
    }
    found, _ = detect(REF, FakeFetcher(files))
    titles = sorted(d.title for d in found)
    assert titles == ["Alpha", "Beta", "Gamma"]
    assert all(d.type == "SKILL" for d in found)


# ----------------------------- MCP -----------------------------

def test_server_json_remote():
    doc = {
        "name": "io.github.acme/search",
        "title": "Acme Search",
        "description": "Search server",
        "remotes": [{"type": "streamable-http", "url": "https://mcp.acme.com/search"}],
    }
    found, _ = detect(REF, FakeFetcher({"server.json": json.dumps(doc)}))
    assert len(found) == 1
    m = found[0]
    assert m.type == "MCP" and m.title == "Acme Search"
    assert m.server_url == "https://mcp.acme.com/search"
    cfg = json.loads(m.config_json)
    assert cfg["mcpServers"]["search"]["url"] == "https://mcp.acme.com/search"


def test_server_json_npm_package():
    doc = {
        "name": "io.github.acme/tool",
        "description": "A tool",
        "packages": [{"registryType": "npm", "identifier": "@acme/mcp-tool", "version": "1.0.0"}],
    }
    found, _ = detect(REF, FakeFetcher({"server.json": json.dumps(doc)}))
    cfg = json.loads(found[0].config_json)
    server = cfg["mcpServers"]["tool"]
    assert server["command"] == "npx" and "@acme/mcp-tool" in server["args"]


def test_mcp_json_multi_server():
    doc = {"mcpServers": {
        "github": {"url": "https://mcp.example.com/github"},
        "postgres": {"command": "uvx", "args": ["mcp-postgres"]},
    }}
    found, _ = detect(REF, FakeFetcher({".mcp.json": json.dumps(doc)}))
    assert len(found) == 2
    assert sorted(d.title for d in found) == ["github", "postgres"]
    assert all(d.type == "MCP" for d in found)


def test_mcp_secret_redaction():
    doc = {"mcpServers": {"svc": {
        "url": "https://mcp.example.com",
        "env": {"API_KEY": "sk-abcdefghijklmnopqrstuvwxyz123456"},
    }}}
    found, _ = detect(REF, FakeFetcher({".mcp.json": json.dumps(doc)}))
    m = found[0]
    assert "${REDACTED}" in m.config_json
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in m.config_json
    assert m.redaction  # findings reported


# ----------------------------- NOTE fallback + precedence -----------------------------

def test_readme_only_becomes_note():
    found, _ = detect(REF, FakeFetcher(
        {"README.md": "# Cookbook\nuseful stuff"}, description="A handy repo"))
    assert len(found) == 1
    n = found[0]
    assert n.type == "NOTE" and n.title == "Cookbook"
    assert n.description == "A handy repo"


def test_skill_suppresses_note_fallback():
    found, _ = detect(REF, FakeFetcher({
        "SKILL.md": "# A skill\nbody",
        "README.md": "# Readme\nx",
    }))
    assert len(found) == 1 and found[0].type == "SKILL"


# ----------------------------- mixed + fingerprint -----------------------------

def test_mixed_repo_and_fingerprint_stability():
    files = {
        "skills/x/SKILL.md": "# X\nx",
        "server.json": json.dumps({"name": "io.github.o/y", "remotes": [{"type": "sse", "url": "https://y"}]}),
        "README.md": "# Z\nz",
    }
    found1, _ = detect(REF, FakeFetcher(files))
    found2, _ = detect(REF, FakeFetcher(files))
    types = sorted(d.type for d in found1)
    assert types == ["MCP", "SKILL"]  # README suppressed because skill/mcp found
    # fingerprints are deterministic across runs
    assert sorted(d.fingerprint for d in found1) == sorted(d.fingerprint for d in found2)
    # all unique
    assert len({d.fingerprint for d in found1}) == 2


def test_subpath_narrows_detection():
    files = {"skills/a/SKILL.md": "# A\na", "skills/b/SKILL.md": "# B\nb"}
    ref = GitHubRef(owner="o", repo="r", subpath="skills/a")
    found, _ = detect(ref, FakeFetcher(files))
    assert len(found) == 1 and found[0].title == "A"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
