"use client";

/**
 * GitHub-style write/preview markdown editor for Notes and SKILL.md.
 * Dependency-free for v1; the TipTap upgrade slots in behind this same
 * value/onChange interface (frontend spec §1).
 */

import { useState } from "react";
import { Markdown } from "@/lib/markdown";

export function MarkdownEditor({
  value,
  onChange,
  placeholder = "Write markdown…",
  rows = 12,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  const [tab, setTab] = useState<"write" | "preview">("write");

  return (
    <div className="overflow-hidden rounded-2xl border-[1.5px] border-line bg-white focus-within:border-primary">
      <div className="flex items-center gap-1 border-b border-line bg-surface px-2 py-1.5">
        {(["write", "preview"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-full px-3.5 py-1 text-xs font-bold capitalize transition ${
              tab === t ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
        <span className="ml-auto pr-2 font-mono text-[0.65rem] text-muted">markdown</span>
      </div>

      {tab === "write" ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="code w-full resize-y bg-white p-4 text-[0.83rem] leading-relaxed text-ink outline-none placeholder:text-muted"
        />
      ) : (
        <div className="thin-scroll max-h-96 overflow-y-auto p-4">
          {value.trim() ? (
            <Markdown source={value} />
          ) : (
            <p className="text-sm text-muted">Nothing to preview yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
