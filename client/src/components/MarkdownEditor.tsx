"use client";

/**
 * GitHub-style write/preview markdown editor for Notes and SKILL.md, with a
 * lightweight formatting toolbar. Dependency-free for v1; the TipTap upgrade
 * slots in behind this same value/onChange interface (frontend spec §1).
 */

import { useRef, useState } from "react";
import { Bold, Italic, Heading, List, Quote, Code, Link2 } from "lucide-react";
import { Markdown } from "@/lib/markdown";

type Tool = {
  icon: typeof Bold;
  label: string;
  /** wrap the selection: before + selection + after */
  wrap?: [string, string];
  /** prefix each selected line (lists, quotes, headings) */
  linePrefix?: string;
  placeholder: string;
};

const TOOLS: Tool[] = [
  { icon: Bold, label: "Bold", wrap: ["**", "**"], placeholder: "bold text" },
  { icon: Italic, label: "Italic", wrap: ["_", "_"], placeholder: "italic text" },
  { icon: Heading, label: "Heading", linePrefix: "## ", placeholder: "Heading" },
  { icon: List, label: "List", linePrefix: "- ", placeholder: "list item" },
  { icon: Quote, label: "Quote", linePrefix: "> ", placeholder: "quote" },
  { icon: Code, label: "Code", wrap: ["`", "`"], placeholder: "code" },
  { icon: Link2, label: "Link", wrap: ["[", "](https://)"], placeholder: "link text" },
];

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
  const ref = useRef<HTMLTextAreaElement>(null);

  const apply = (t: Tool) => {
    const ta = ref.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const selected = value.slice(start, end) || t.placeholder;
    let next: string;
    let cursorStart: number;
    let cursorEnd: number;

    if (t.linePrefix) {
      // prefix every line of the selection (or the current line)
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const block = value.slice(lineStart, end) || t.placeholder;
      const prefixed = block.split("\n").map((l) => t.linePrefix + l).join("\n");
      next = value.slice(0, lineStart) + prefixed + value.slice(end);
      cursorStart = lineStart;
      cursorEnd = lineStart + prefixed.length;
    } else if (t.wrap) {
      const [b, a] = t.wrap;
      next = value.slice(0, start) + b + selected + a + value.slice(end);
      cursorStart = start + b.length;
      cursorEnd = cursorStart + selected.length;
    } else {
      return;
    }

    onChange(next);
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(cursorStart, cursorEnd);
    });
  };

  return (
    <div className="overflow-hidden rounded-2xl border-[1.5px] border-line bg-card focus-within:border-primary">
      <div className="flex items-center gap-1 border-b border-line bg-surface px-2 py-1.5">
        {(["write", "preview"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-full px-3.5 py-1 text-xs font-bold capitalize transition ${
              tab === t ? "bg-card text-ink shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}

        {tab === "write" && (
          <span className="ml-1 flex items-center gap-0.5 border-l border-line pl-1.5">
            {TOOLS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.label}
                  type="button"
                  title={t.label}
                  aria-label={t.label}
                  onClick={() => apply(t)}
                  className="rounded-lg p-1.5 text-muted transition hover:bg-card hover:text-ink"
                >
                  <Icon className="h-3.5 w-3.5" />
                </button>
              );
            })}
          </span>
        )}

        <span className="ml-auto pr-2 font-mono text-[0.65rem] text-muted">markdown</span>
      </div>

      {tab === "write" ? (
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={rows}
          className="code w-full resize-y bg-card p-4 text-[0.83rem] leading-relaxed text-ink outline-none placeholder:text-muted"
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
