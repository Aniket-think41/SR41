import Link from "next/link";
import { Resource, TYPE_META, fmt, initialsOf, resourceOwner } from "@/lib/data";
import { saveResource } from "@/lib/redirects";

const TYPE_STYLES: Record<string, string> = {
  SKILL: "bg-primary-50 text-primary",
  MCP: "bg-[#e7f0ff] text-mcp",
  NOTE: "bg-[#fdece5] text-note",
};

export function ResourceCard({ r }: { r: Resource }) {
  const meta = TYPE_META[r.type];
  // Org-published resources are attributed to the org; personal ones to the author.
  const owner = resourceOwner(r);

  return (
    <article className="card card-hover group relative flex h-full flex-col p-6">
      {/* Star → "Sign in to save" (logged-out path per spec §5) */}
      <Link
        href={saveResource(r.id)}
        className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-line bg-white text-muted opacity-0 transition hover:border-primary hover:text-primary group-hover:opacity-100"
        title="Sign in to save"
        aria-label="Sign in to save"
      >
        <span aria-hidden>☆</span>
      </Link>

      <Link href={`/marketplace/${r.id}`} className="flex flex-1 flex-col">
        <div className="flex items-center gap-2">
          <span className={`tag ${TYPE_STYLES[r.type]}`}>
            <span aria-hidden>{meta.glyph}</span> {meta.label}
          </span>
          <span className="text-xs text-muted">v{r.version}</span>
        </div>

        <h3 className="font-display mt-4 text-2xl font-semibold leading-tight transition group-hover:text-primary">
          {r.title}
        </h3>
        <p className="mt-2 line-clamp-3 flex-1 text-[0.95rem] leading-relaxed text-body">{r.description}</p>

        <div className="mt-4 flex flex-wrap gap-1.5">
          {r.tags.slice(0, 3).map((t) => (
            <span key={t} className="text-xs text-muted">#{t}</span>
          ))}
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <span className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-[0.6rem] font-bold text-white ${
                owner?.kind === "org" ? "bg-ink" : "bg-primary"
              }`}
              title={owner?.kind === "org" ? "Published by an organization" : undefined}
            >
              {owner ? initialsOf(owner.name) : "?"}
            </span>
            <span className="text-xs font-medium text-ink">
              {owner?.name}
              {owner?.verified && <span className="ml-1 text-primary" title="Think41-verified">✦</span>}
            </span>
          </span>
          <span className="text-xs text-muted">↓ {fmt(r.installs_count)} · ★ {fmt(r.stars_count)}</span>
        </div>
      </Link>
    </article>
  );
}
