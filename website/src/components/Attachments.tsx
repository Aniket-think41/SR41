import type { Attachment } from "@/lib/data";

function ytId(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
}
function vimeoId(url: string): string | null {
  const m = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  return m ? m[1] : null;
}

function Video({ url }: { url: string }) {
  const yt = ytId(url);
  if (yt) return <iframe className="aspect-video w-full rounded-xl" src={`https://www.youtube.com/embed/${yt}`} title="Video" allowFullScreen />;
  const vm = vimeoId(url);
  if (vm) return <iframe className="aspect-video w-full rounded-xl" src={`https://player.vimeo.com/video/${vm}`} title="Video" allowFullScreen />;
  if (/\.(mp4|webm|ogg)(\?|$)/i.test(url)) return <video controls className="w-full rounded-xl" src={url} />;
  return <a href={url} className="text-primary hover:underline">{url}</a>;
}

export function Attachments({ items }: { items?: Attachment[] }) {
  if (!items?.length) return null;
  return (
    <div className="mt-8">
      <h2 className="kicker">Attachments</h2>
      <div className="mt-3 space-y-4">
        {items.map((a, i) => {
          if (a.kind === "video")
            return (
              <figure key={i}>
                <Video url={a.url} />
                {(a.title || a.caption) && (
                  <figcaption className="mt-1.5 text-sm text-muted">
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
                {(a.title || a.caption) && <figcaption className="mt-1.5 text-sm text-muted">{a.title || a.caption}</figcaption>}
              </figure>
            );
          return (
            <a key={i} href={a.url} className="card card-hover block p-4">
              <span className="block text-sm font-semibold text-ink">{a.title || a.url}</span>
              {a.caption && <span className="mt-0.5 block text-sm text-body">{a.caption}</span>}
              <span className="mt-0.5 block truncate text-xs text-muted">
                {a.kind === "file" ? "↓ " : "↗ "}
                {a.url}
              </span>
            </a>
          );
        })}
      </div>
    </div>
  );
}
