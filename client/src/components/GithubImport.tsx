"use client";

/**
 * Import skills / MCP servers / notes from a public GitHub repo URL. Detection
 * runs server-side (or in the mock detector): paste a URL → see what was found →
 * pick which to import and into which scope.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Github, Loader2, Search, ShieldAlert } from "lucide-react";
import { api, type GithubDetected } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import type { ScopeType } from "@/lib/types";
import { TYPE_META } from "@/lib/utils";
import { useToast } from "./Toast";

interface ScopeOpt {
  scope_type: ScopeType;
  scope_id: string | null;
  label: string;
}

export function GithubImport({
  scopeOptions,
  defaultScope,
  onBack,
  onDone,
}: {
  scopeOptions: ScopeOpt[];
  defaultScope?: { scope_type: ScopeType; scope_id: string | null };
  onBack: () => void;
  onDone: () => void | Promise<void>;
}) {
  const { toast } = useToast();
  const [url, setUrl] = useState("");
  const [detected, setDetected] = useState<GithubDetected[] | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const initial = defaultScope ?? scopeOptions[0];
  const [scope, setScope] = useState(`${initial?.scope_type}:${initial?.scope_id ?? ""}`);

  const previewMut = useMutation({
    mutationFn: () => api.githubPreview(url.trim()),
    onSuccess: (res) => {
      setDetected(res.detected);
      setChecked(new Set(res.detected.map((d) => d.fingerprint)));
      if (!res.detected.length) toast("No skills, MCP servers, or notes detected", "error");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const importMut = useMutation({
    mutationFn: () => {
      const [st, si] = scope.split(":");
      return api.githubImport({
        url: url.trim(),
        scope_type: st as ScopeType,
        scope_id: si || null,
        select: [...checked],
      });
    },
    onSuccess: async (res) => {
      const n = res.created.length;
      const s = res.skipped.length;
      toast(`Imported ${n} ${n === 1 ? "resource" : "resources"}${s ? ` · ${s} already there` : ""}`);
      await onDone();
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const toggle = (fp: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(fp) ? next.delete(fp) : next.add(fp);
      return next;
    });

  const detect = () => {
    if (url.trim()) previewMut.mutate();
  };

  return (
    <>
      <div className="thin-scroll flex-1 overflow-y-auto p-6">
        <button type="button" onClick={onBack} className="btn btn-secondary btn-sm mb-4">
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>

        <label className="field-label" htmlFor="gh-url">Repository URL</label>
        <div className="flex gap-2">
          <span className="flex flex-1 items-center gap-2 rounded-xl border border-line bg-white px-3">
            <Github className="h-4 w-4 shrink-0 text-muted" />
            <input
              id="gh-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && detect()}
              placeholder="github.com/owner/repo"
              className="flex-1 bg-transparent py-2.5 text-sm outline-none placeholder:text-muted"
            />
          </span>
          <button type="button" onClick={detect} className="btn btn-primary btn-sm" disabled={previewMut.isPending || !url.trim()}>
            {previewMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            Detect
          </button>
        </div>
        <p className="mt-1.5 text-xs text-muted">
          Public repos only. We look for SKILL.md skills, server.json / .mcp.json MCP servers, or a README note.
        </p>

        {detected && detected.length > 0 && (
          <div className="mt-6">
            <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">
              {detected.length} detected — pick what to import
            </p>
            <ul className="space-y-2">
              {detected.map((d) => {
                const meta = TYPE_META[d.type];
                const on = checked.has(d.fingerprint);
                return (
                  <li key={d.fingerprint}>
                    <button
                      type="button"
                      onClick={() => toggle(d.fingerprint)}
                      className={`card flex w-full items-start gap-3 p-4 text-left transition ${
                        on ? "!border-primary ring-2 ring-primary/15" : "opacity-70 hover:opacity-100"
                      }`}
                    >
                      <input type="checkbox" checked={on} readOnly className="mt-1 h-4 w-4 accent-primary" />
                      <span
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-sm text-white"
                        style={{ backgroundColor: meta.color }}
                        aria-hidden
                      >
                        {meta.glyph}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="font-display truncate font-semibold">{d.title}</span>
                          <span className={`tag ${meta.chip}`}>{meta.label}</span>
                        </span>
                        {d.description && <span className="mt-0.5 block truncate text-sm text-body">{d.description}</span>}
                        <span className="mt-0.5 block truncate font-mono text-xs text-muted">{d.source_path}</span>
                        {d.redaction.length > 0 && (
                          <span className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-note">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            {d.redaction.length} secret{d.redaction.length === 1 ? "" : "s"} redacted
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            <div className="mt-5">
              <label className="field-label" htmlFor="gh-scope">Import into</label>
              <select id="gh-scope" className="field" value={scope} onChange={(e) => setScope(e.target.value)}>
                {scopeOptions.map((o) => (
                  <option key={`${o.scope_type}:${o.scope_id}`} value={`${o.scope_type}:${o.scope_id ?? ""}`}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {detected && detected.length === 0 && (
          <div className="mt-6 rounded-2xl border border-dashed border-line bg-surface p-8 text-center">
            <p className="font-display text-lg font-semibold">Nothing detected</p>
            <p className="mt-1 text-sm text-body">No SKILL.md, MCP config, or README found in that repo.</p>
          </div>
        )}
      </div>

      <div className="flex items-center justify-end border-t border-line bg-surface p-4">
        <button
          type="button"
          onClick={() => importMut.mutate()}
          className="btn btn-primary btn-sm"
          disabled={importMut.isPending || !checked.size}
        >
          {importMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {checked.size ? `Import ${checked.size}` : "Select items"}
        </button>
      </div>
    </>
  );
}
