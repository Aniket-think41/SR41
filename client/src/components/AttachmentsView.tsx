"use client";

/**
 * Renders a resource's typed attachments (hybrid content model): videos are
 * embedded (YouTube / Vimeo / direct mp4), images shown inline, links and
 * files as cards. Read-only counterpart of AttachmentsEditor.
 */

import { Link2, Paperclip, ExternalLink } from "lucide-react";
import type { Attachment } from "@/lib/types";

function ytId(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
}
function vimeoId(url: string): string | null {
  const m = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  return m ? m[1] : null;
}

function VideoEmbed({ url }: { url: string }) {
  const yt = ytId(url);
  if (yt)
    return (
      <iframe
        className="aspect-video w-full rounded-xl"
        src={`https://www.youtube.com/embed/${yt}`}
        title="Video"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
      />
    );
  const vm = vimeoId(url);
  if (vm)
    return <iframe className="aspect-video w-full rounded-xl" src={`https://player.vimeo.com/video/${vm}`} title="Video" allowFullScreen />;
  if (/\.(mp4|webm|ogg)(\?|$)/i.test(url))
    return <video controls className="w-full rounded-xl" src={url} />;
  // Unknown provider — fall back to a link.
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
      <ExternalLink className="h-3.5 w-3.5" /> {url}
    </a>
  );
}

export function AttachmentsView({ items }: { items?: Attachment[] }) {
  if (!items?.length) return null;
  return (
    <section className="mt-6">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Attachments</h3>
      <div className="space-y-4">
        {items.map((a, i) => {
          if (a.kind === "video")
            return (
              <figure key={i}>
                <VideoEmbed url={a.url} />
                {(a.title || a.caption) && (
                  <figcaption className="mt-1.5 text-xs text-muted">
                    {a.title && <span className="font-medium text-ink">{a.title}</span>}
                    {a.title && a.caption ? " — " : ""}
                    {a.caption}
                  </figcaption>
                )}
              </figure>
            );
          if (a.kind === "image")
            return (
              <figure key={i}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={a.url} alt={a.title ?? a.caption ?? "attachment"} className="w-full rounded-xl border border-line" />
                {(a.title || a.caption) && (
                  <figcaption className="mt-1.5 text-xs text-muted">{a.title || a.caption}</figcaption>
                )}
              </figure>
            );
          // link or file → a card
          const Icon = a.kind === "file" ? Paperclip : Link2;
          return (
            <a
              key={i}
              href={a.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-3 transition hover:border-primary"
            >
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-card text-muted">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-ink">
                  {a.title || a.url}
                </span>
                {a.caption && <span className="block truncate text-xs text-body">{a.caption}</span>}
                <span className="block truncate text-xs text-muted">{a.url}</span>
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
