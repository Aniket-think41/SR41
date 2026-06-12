"use client";

/**
 * Typed-media editor for the hybrid content model (frontend spec §4.3).
 * The markdown body stays the canonical prose; this manages a structured list
 * of {kind, url, title, caption} items — links, images, videos, files.
 */

import { Link2, Image as ImageIcon, Video, Paperclip, X, GripVertical } from "lucide-react";
import type { Attachment, AttachmentKind } from "@/lib/types";

const KINDS: { kind: AttachmentKind; label: string; icon: typeof Link2; urlPlaceholder: string }[] = [
  { kind: "link", label: "Link", icon: Link2, urlPlaceholder: "https://…" },
  { kind: "image", label: "Image", icon: ImageIcon, urlPlaceholder: "https://…/image.png" },
  { kind: "video", label: "Video", icon: Video, urlPlaceholder: "https://youtube.com/watch?v=… or .mp4" },
  { kind: "file", label: "File", icon: Paperclip, urlPlaceholder: "https://…/file.pdf" },
];

const META = Object.fromEntries(KINDS.map((k) => [k.kind, k])) as Record<AttachmentKind, (typeof KINDS)[number]>;

export function AttachmentsEditor({
  value,
  onChange,
}: {
  value: Attachment[];
  onChange: (next: Attachment[]) => void;
}) {
  const add = (kind: AttachmentKind) => onChange([...value, { kind, url: "", title: "", caption: "" }]);
  const update = (i: number, patch: Partial<Attachment>) =>
    onChange(value.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  const remove = (i: number) => onChange(value.filter((_, idx) => idx !== i));
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= value.length) return;
    const next = [...value];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {KINDS.map(({ kind, label, icon: Icon }) => (
          <button
            key={kind}
            type="button"
            onClick={() => add(kind)}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-body transition hover:border-primary hover:text-primary"
          >
            <Icon className="h-3.5 w-3.5" /> Add {label}
          </button>
        ))}
      </div>

      {value.length > 0 && (
        <ul className="space-y-2">
          {value.map((a, i) => {
            const m = META[a.kind];
            const Icon = m.icon;
            return (
              <li key={i} className="rounded-2xl border border-line bg-surface p-3">
                <div className="flex items-center gap-2">
                  <span className="flex flex-col">
                    <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="text-muted hover:text-ink disabled:opacity-30" aria-label="Move up">
                      <GripVertical className="h-3.5 w-3.5" />
                    </button>
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs font-bold capitalize text-ink">
                    <Icon className="h-3.5 w-3.5" /> {a.kind}
                  </span>
                  <input
                    value={a.url}
                    onChange={(e) => update(i, { url: e.target.value })}
                    placeholder={m.urlPlaceholder}
                    className="field code !py-1.5 flex-1 text-[0.8rem]"
                  />
                  <button type="button" onClick={() => remove(i)} className="rounded-full p-1.5 text-muted transition hover:bg-white hover:text-note" aria-label="Remove">
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 pl-7">
                  <input
                    value={a.title ?? ""}
                    onChange={(e) => update(i, { title: e.target.value })}
                    placeholder={a.kind === "file" ? "File name (optional)" : "Title (optional)"}
                    className="field !py-1.5 text-[0.8rem]"
                  />
                  <input
                    value={a.caption ?? ""}
                    onChange={(e) => update(i, { caption: e.target.value })}
                    placeholder="Caption / note (optional)"
                    className="field !py-1.5 text-[0.8rem]"
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
