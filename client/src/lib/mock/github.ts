/**
 * Mock-mode GitHub ingestion — mirrors backend/app/github.py compactly so the
 * dashboard's "Import from GitHub" works without a backend. Fetches the public
 * GitHub API + raw files directly from the browser (both are CORS-enabled).
 *
 * Kept in sync with the backend detector: SKILL.md → SKILL, server.json /
 * .mcp.json → MCP, README.md → NOTE fallback. Secrets in MCP configs are redacted.
 */

import type { GithubDetected, GithubPreview } from "../api";

/** Full detected item — carries untruncated content for the import handler. */
export interface GithubItemFull {
  kind: "skill" | "mcp" | "note";
  type: "SKILL" | "MCP" | "NOTE";
  title: string;
  description: string;
  tags: string[];
  source_path: string;
  fingerprint: string;
  redaction: string[];
  server_url: string | null;
  config_json: string | null;
  content_md: string;
  attachments: { kind: "link" | "image" | "video" | "file"; url: string; title?: string; caption?: string }[];
}

interface Ref {
  owner: string;
  repo: string;
  ref: string | null;
  subpath: string | null;
}

export function parseGithubUrl(url: string): Ref {
  const raw = (url || "").trim();
  if (!raw) throw new Error("A GitHub URL is required");
  const m = raw.match(/^(?:https?:\/\/)?(?:www\.)?github\.com\/(.+)$/i);
  const path = (m ? m[1] : raw).replace(/^\/+|\/+$/g, "");
  const parts = path.split("/");
  if (parts.length < 2 || !parts[0] || !parts[1])
    throw new Error("Not a GitHub repository URL (expected github.com/owner/repo)");
  const owner = parts[0];
  const repo = parts[1].replace(/\.git$/, "");
  let ref: string | null = null;
  let subpath: string | null = null;
  if (parts.length >= 4 && (parts[2] === "tree" || parts[2] === "blob")) {
    ref = parts[3];
    if (parts.length > 4) subpath = parts.slice(4).join("/");
  }
  return { owner, repo, ref, subpath };
}

// ---- light secret redaction (mirrors backend value patterns) ----
const VALUE_PATTERNS: [string, RegExp][] = [
  ["aws_access_key", /\bAKIA[0-9A-Z]{16}\b/g],
  ["github_token", /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g],
  ["openai_key", /\bsk-[A-Za-z0-9]{20,}\b/g],
  ["slack_token", /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g],
];
const SECRET_KEY = /(password|passwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret|auth|bearer|private[_-]?key|credential)/i;

function redactConfig(obj: unknown, key?: string): [unknown, string[]] {
  const findings: string[] = [];
  if (Array.isArray(obj)) {
    const out = obj.map((v) => {
      const [rv, f] = redactConfig(v, key);
      findings.push(...f);
      return rv;
    });
    return [out, findings];
  }
  if (obj && typeof obj === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      if (typeof v === "string" && SECRET_KEY.test(k)) {
        out[k] = "${REDACTED}";
        findings.push(k);
      } else {
        const [rv, f] = redactConfig(v, k);
        out[k] = rv;
        findings.push(...f);
      }
    }
    return [out, findings];
  }
  if (typeof obj === "string") {
    if (key && SECRET_KEY.test(key)) {
      findings.push(key);
      return ["${REDACTED}", findings];
    }
    let s = obj;
    for (const [label, re] of VALUE_PATTERNS) {
      if (re.test(s)) {
        findings.push(label);
        s = s.replace(re, "${REDACTED}");
      }
    }
    return [s, findings];
  }
  return [obj, findings];
}

// ---- parsing helpers ----
const h1 = (t: string) => t.match(/^\s*#\s+(.+)$/m)?.[1]?.trim() ?? null;

function frontmatter(text: string): Record<string, string> {
  if (!text.startsWith("---")) return {};
  const end = text.indexOf("\n---", 3);
  if (end === -1) return {};
  const out: Record<string, string> = {};
  for (const line of text.slice(3, end).split("\n")) {
    const i = line.indexOf(":");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
  }
  return out;
}

// deterministic, stable fingerprint (mock-only; need not match backend sha256)
function fingerprint(ref: Ref, path: string, content: string): string {
  const s = `github:${ref.owner}/${ref.repo}:${path}\n${content}`;
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return `fp_${h.toString(16).padStart(8, "0")}${s.length.toString(16)}`;
}

const ghLink = (ref: Ref, refName: string, path: string) => ({
  kind: "link" as const,
  url: `https://github.com/${ref.owner}/${ref.repo}/blob/${refName}/${path}`,
  title: "Source on GitHub",
  caption: path,
});

function serverJsonToConfig(name: string, doc: Record<string, unknown>): [string, string | null] {
  let server: Record<string, unknown> = {};
  let serverUrl: string | null = null;
  const remotes = doc.remotes as { type?: string; url?: string }[] | undefined;
  if (Array.isArray(remotes) && remotes.length) {
    serverUrl = remotes[0].url ?? null;
    server = { type: remotes[0].type ?? "streamable-http", url: serverUrl };
  } else {
    const pkgs = doc.packages as Record<string, unknown>[] | undefined;
    const p0 = (Array.isArray(pkgs) && pkgs[0]) || {};
    const registry = String(p0.registryType ?? p0.registry_type ?? "").toLowerCase();
    const id = String(p0.identifier ?? p0.name ?? name);
    const runtime = String(p0.runtimeHint ?? p0.runtime_hint ?? "").toLowerCase();
    if (registry === "pypi" || runtime === "uvx") server = { command: "uvx", args: [id] };
    else if (registry === "oci") server = { command: "docker", args: ["run", "-i", "--rm", id] };
    else server = { command: "npx", args: ["-y", id] };
  }
  return [JSON.stringify({ mcpServers: { [name]: server } }, null, 2), serverUrl];
}

const shortName = (full: string) => full.split("/").pop() || full;

async function ghJson(url: string): Promise<unknown> {
  const res = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
  if (res.status === 404) throw new Error("GitHub repository not found (is it public?)");
  if (res.status === 403) throw new Error("GitHub rate limit hit — try again in a minute");
  if (!res.ok) throw new Error(`GitHub returned ${res.status}`);
  return res.json();
}

async function ghRaw(ref: Ref, refName: string, path: string): Promise<string | null> {
  const res = await fetch(`https://raw.githubusercontent.com/${ref.owner}/${ref.repo}/${refName}/${path}`);
  return res.ok ? res.text() : null;
}

const SKILL_RE = /(^|\/)SKILL\.md$/i;
const SERVER_JSON_RE = /(^|\/)server\.json$/i;
const MCP_JSON_RE = /(^|\/)(\.mcp\.json|mcp\.json)$/i;
const README_RE = /(^|\/)README\.md$/i;

export interface GithubDetection {
  repo: { owner: string; repo: string; ref: string | null; description: string; html_url: string };
  items: GithubItemFull[];
}

/** Full detection (untruncated content). Backs both preview and import. */
export async function detectGithubFull(url: string): Promise<GithubDetection> {
  const ref = parseGithubUrl(url);
  const meta = (await ghJson(`https://api.github.com/repos/${ref.owner}/${ref.repo}`)) as Record<string, unknown>;
  const refName = ref.ref || String(meta.default_branch || "main");
  const description = String(meta.description ?? "");
  const htmlUrl = String(meta.html_url ?? `https://github.com/${ref.owner}/${ref.repo}`);
  const topics = ((meta.topics as string[]) ?? []).slice(0, 6);

  const treeDoc = (await ghJson(
    `https://api.github.com/repos/${ref.owner}/${ref.repo}/git/trees/${refName}?recursive=1`
  )) as { tree?: { path: string; type: string }[] };
  let paths = (treeDoc.tree ?? []).filter((n) => n.type === "blob").map((n) => n.path);
  if (ref.subpath) {
    const prefix = ref.subpath.replace(/\/+$/, "");
    paths = paths.filter((p) => p === prefix || p.startsWith(prefix + "/"));
  }

  const items: GithubItemFull[] = [];
  const seen = new Set<string>();
  const add = (d: GithubItemFull) => {
    if (seen.has(d.fingerprint)) return;
    seen.add(d.fingerprint);
    items.push(d);
  };

  // skills
  for (const p of paths.filter((x) => SKILL_RE.test(x))) {
    const text = await ghRaw(ref, refName, p);
    if (!text) continue;
    const fm = frontmatter(text);
    const folder = p.includes("/") ? p.split("/").slice(-2)[0] : ref.repo;
    add({
      kind: "skill", type: "SKILL", title: fm.name || h1(text) || folder,
      description: fm.description ?? "", tags: topics, source_path: p,
      fingerprint: fingerprint(ref, p, text), redaction: [],
      server_url: null, config_json: null, content_md: text,
      attachments: [ghLink(ref, refName, p)],
    });
  }

  // MCP from server.json
  for (const p of paths.filter((x) => SERVER_JSON_RE.test(x))) {
    const text = await ghRaw(ref, refName, p);
    if (!text) continue;
    let doc: Record<string, unknown>;
    try { doc = JSON.parse(text); } catch { continue; }
    if (!doc || typeof doc !== "object" || !("name" in doc)) continue;
    const name = shortName(String(doc.name));
    const [rawConfig, serverUrl] = serverJsonToConfig(name, doc);
    const [red, findings] = redactConfig(JSON.parse(rawConfig));
    add({
      kind: "mcp", type: "MCP", title: String(doc.title ?? name),
      description: String(doc.description ?? ""), tags: topics, source_path: p,
      fingerprint: fingerprint(ref, p, rawConfig), redaction: [...new Set(findings)],
      server_url: serverUrl, config_json: JSON.stringify(red, null, 2), content_md: "",
      attachments: [ghLink(ref, refName, p)],
    });
  }

  // MCP from .mcp.json / mcp.json
  for (const p of paths.filter((x) => MCP_JSON_RE.test(x))) {
    const text = await ghRaw(ref, refName, p);
    if (!text) continue;
    let doc: Record<string, unknown>;
    try { doc = JSON.parse(text); } catch { continue; }
    const servers = doc?.mcpServers as Record<string, Record<string, unknown>> | undefined;
    if (!servers || typeof servers !== "object") continue;
    for (const [name, cfg] of Object.entries(servers)) {
      if (!cfg || typeof cfg !== "object") continue;
      const [red, findings] = redactConfig({ mcpServers: { [name]: cfg } });
      add({
        kind: "mcp", type: "MCP", title: name,
        description: String(cfg.command ?? cfg.url ?? ""), tags: topics,
        source_path: `${p}#${name}`,
        fingerprint: fingerprint(ref, `${p}#${name}`, JSON.stringify({ mcpServers: { [name]: cfg } })),
        redaction: [...new Set(findings)], server_url: (cfg.url as string) ?? null,
        config_json: JSON.stringify(red, null, 2), content_md: "",
        attachments: [ghLink(ref, refName, p)],
      });
    }
  }

  // NOTE fallback
  if (items.length === 0) {
    const readme = paths.find((x) => README_RE.test(x));
    const text = readme ? await ghRaw(ref, refName, readme) : null;
    if (text) {
      add({
        kind: "note", type: "NOTE", title: h1(text) || ref.repo,
        description, tags: topics, source_path: readme!,
        fingerprint: fingerprint(ref, readme!, text), redaction: [],
        server_url: null, config_json: null, content_md: text,
        attachments: [{ kind: "link", url: htmlUrl, title: "Repository", caption: `${ref.owner}/${ref.repo}` }],
      });
    }
  }

  return {
    repo: { owner: ref.owner, repo: ref.repo, ref: ref.ref, description, html_url: htmlUrl },
    items,
  };
}

/** Truncated, API-shaped preview built from a full detection. */
export function toPreview(det: GithubDetection): GithubPreview {
  const detected: GithubDetected[] = det.items.map((d) => ({
    kind: d.kind, type: d.type, title: d.title, description: d.description,
    tags: d.tags, source_path: d.source_path, fingerprint: d.fingerprint,
    redaction: d.redaction, server_url: d.server_url, has_config: !!d.config_json,
    content_preview: (d.config_json || d.content_md || "").slice(0, 500),
    attachments: d.attachments,
  }));
  return { repo: det.repo, detected };
}

/** Resource-create body from a full detected item. */
export function detectedToCreateBody(d: GithubItemFull) {
  return {
    type: d.type,
    title: d.title,
    description: d.description,
    content_md: d.content_md,
    server_url: d.server_url ?? undefined,
    config_json: d.config_json ?? undefined,
    tags: d.tags,
    attachments: d.attachments,
    source_fingerprint: d.fingerprint,
  };
}
