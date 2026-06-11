"use client";

/**
 * TypeIcon + ScopeBadge (frontend spec §5.2 / §5.3) — the glyph language
 * matches the marketing site: ◆ Skill · ▣ MCP · ▤ Note.
 * Scope labels honor the org's custom terminology (e.g. Pod → Team).
 */

import { TYPE_META, SCOPE_META } from "@/lib/utils";
import { useTerms } from "@/lib/hooks";
import type { ResourceType, ScopeType } from "@/lib/types";

export function TypeBadge({ type, withLabel = true }: { type: ResourceType; withLabel?: boolean }) {
  const meta = TYPE_META[type];
  return (
    <span className={`tag ${meta.chip}`}>
      <span aria-hidden>{meta.glyph}</span>
      {withLabel && meta.label}
    </span>
  );
}

export function TypeGlyph({ type, className = "" }: { type: ResourceType; className?: string }) {
  const meta = TYPE_META[type];
  return (
    <span className={className} style={{ color: meta.color }} aria-label={meta.label}>
      {meta.glyph}
    </span>
  );
}

export function ScopeBadge({ scope }: { scope: ScopeType }) {
  const meta = SCOPE_META[scope];
  const terms = useTerms();
  const label =
    scope === "POD" ? terms.pod : scope === "PROJECT" ? terms.project : meta.label;
  return (
    <span className={`tag ${meta.chip}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
      {label}
    </span>
  );
}
