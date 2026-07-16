"use client";

/**
 * Right-side drawer (frontend spec §4.2 / §4.3) — one component, two modes:
 * detail view and add/edit form. Controlled by the zustand drawer state so
 * any screen (pod view, org resources, palette) can open it in context.
 */

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  X, Star, Pin, PinOff, Pencil, Trash2, Globe, Copy, Download, Check, ExternalLink, Eye,
  Clock, AlertTriangle, Share2,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useFeature, useInvalidateResources, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import type { Resource } from "@/lib/types";
import { fmt, longDate, SCOPE_META } from "@/lib/utils";
import { Markdown } from "@/lib/markdown";
import { AttachmentsView } from "./AttachmentsView";
import { Avatar } from "./Avatar";
import { ScopeBadge, TypeBadge } from "./badges";
import { useToast } from "./Toast";
import { useConfirm } from "./ConfirmDelete";
import { ResourceForm } from "./ResourceForm";

const VISIBILITY_LABEL: Record<string, string> = {
  POD: "Pod only",
  PROJECT: "Project",
  ORG: "Org-wide",
};

// Public origin of the marketing/marketplace site, where the canonical /r/{id}
// share link lives. Set NEXT_PUBLIC_WEB_URL in prod; falls back to the brand URL.
const WEB_URL = (process.env.NEXT_PUBLIC_WEB_URL ?? "https://skillshare.think41.com").replace(/\/$/, "");

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      }}
      className="btn btn-secondary btn-sm"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[var(--color-success)]" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function DetailView({ resource: initial, onClose }: { resource: Resource; onClose: () => void }) {
  // Re-fetch by id so stars/edits/publishes reflect live (drawer stays open).
  const { data: live } = useQuery({
    queryKey: qk.resource(initial.id),
    queryFn: () => api.resource(initial.id),
    initialData: initial,
  });
  const r = live ?? initial;
  const { data: me } = useSession();
  const { openEdit } = useUi();
  const invalidate = useInvalidateResources();
  const { toast } = useToast();
  const confirm = useConfirm();

  const canEdit = me && r.author_id === me.id;
  const publishing = useFeature("publishing");

  const starMut = useMutation({
    mutationFn: () => (r.starred_by_me ? api.unstar(r.id) : api.star(r.id)),
    onSuccess: invalidate,
  });
  const pinMut = useMutation({
    mutationFn: () => (r.pinned_by_me ? api.unpin(r.id) : api.pin(r.id)),
    onSuccess: async () => {
      await invalidate();
      toast(r.pinned_by_me ? "Unpinned from your profile" : "Pinned to your profile");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const publishMut = useMutation({
    mutationFn: () => (r.is_public ? api.unpublish(r.id) : api.publish(r.id)),
    onSuccess: async (updated) => {
      await invalidate();
      if (r.is_public) toast("Removed from the public marketplace");
      else if (updated.approval_status === "pending")
        toast("Submitted for review — it will go live once approved");
      else toast("Published to the public marketplace 🎉");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const deleteMut = useMutation({
    mutationFn: () => api.deleteResource(r.id),
    onSuccess: async () => {
      await invalidate();
      toast(`"${r.title}" deleted`);
      onClose();
    },
  });

  return (
    <>
      {/* Header */}
      <div className="border-b border-line p-6 pb-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge type={r.type} />
            {r.scope_label && <ScopeBadge scope={r.scope_label} />}
            {!r.is_public && r.visibility && (
              <span className="tag" title="Who can see this resource">
                <Eye className="h-3 w-3" /> {VISIBILITY_LABEL[r.visibility] ?? r.visibility}
              </span>
            )}
            {r.is_public && r.approval_status === "approved" && (
              <span className={`tag ${SCOPE_META.PUBLIC.chip}`}>
                <Globe className="h-3 w-3" /> Marketplace
              </span>
            )}
            {r.is_public && r.approval_status === "pending" && (
              <span className="tag !bg-amber-100 !text-amber-800" title="Awaiting a reviewer's decision">
                <Clock className="h-3 w-3" /> Pending review
              </span>
            )}
            {r.approval_status === "rejected" && (
              <span className="tag !bg-red-100 !text-red-700" title={r.review_note ?? undefined}>
                <AlertTriangle className="h-3 w-3" /> Rejected
              </span>
            )}
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 text-muted transition hover:bg-surface hover:text-ink" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <h2 className="font-display mt-3 break-words text-2xl font-semibold">{r.title}</h2>
        <p className="mt-1.5 break-words text-sm leading-relaxed text-body">{r.description}</p>

        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <Avatar name={r.author?.display_name ?? "?"} src={r.author?.avatar_url} size="xs" />
            <span className="font-semibold text-ink">{r.author?.display_name}</span>
          </span>
          <span className="code">v{r.version}</span>
          <span>★ {fmt(r.stars_count)}</span>
          <span>Updated {longDate(r.updated_at)}</span>
        </div>

        {r.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {r.tags.map((t) => (
              <span key={t} className="tag">#{t}</span>
            ))}
          </div>
        )}
      </div>

      {/* Body */}
      <div className="thin-scroll flex-1 overflow-y-auto p-6">
        {r.approval_status === "pending" && r.is_public && (
          <div className="mb-5 flex items-start gap-2.5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            <Clock className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              <span className="font-bold">Pending review.</span> This resource won&rsquo;t appear on the
              marketplace until a reviewer approves it.
            </p>
          </div>
        )}
        {r.approval_status === "rejected" && (
          <div className="mb-5 flex items-start gap-2.5 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              <span className="font-bold">Not approved for the marketplace.</span>
              {r.review_note ? <> Reviewer note: “{r.review_note}”.</> : null} Edit and republish to resubmit.
            </p>
          </div>
        )}
        {r.type === "MCP" ? (
          <div className="space-y-5">
            {r.server_url && (
              <section>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted">Server URL</h3>
                <div className="flex items-center gap-2">
                  <code className="code flex-1 truncate rounded-xl border border-line bg-surface px-3 py-2 text-xs text-ink">
                    {r.server_url}
                  </code>
                  <CopyButton text={r.server_url} label="Copy URL" />
                </div>
              </section>
            )}
            {r.config_json && (
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-muted">Config JSON</h3>
                  <CopyButton text={r.config_json} label="Copy config" />
                </div>
                <pre className="thin-scroll overflow-x-auto rounded-2xl bg-navy p-4 text-xs leading-relaxed text-[#e8e6ff]">
                  <code className="code">{r.config_json}</code>
                </pre>
              </section>
            )}
            {r.content_md && (
              <section>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted">About</h3>
                <Markdown source={r.content_md} />
              </section>
            )}
          </div>
        ) : (
          <div className="space-y-5">
            {r.type === "SKILL" && (
              <div className="flex flex-wrap gap-2">
                <CopyButton text={r.content_md} label="Copy SKILL.md" />
                {r.file_url && (
                  <a href={r.file_url} className="btn btn-lime btn-sm" download>
                    <Download className="h-3.5 w-3.5" /> Download .skill
                  </a>
                )}
              </div>
            )}
            <Markdown source={r.content_md || "_No content yet._"} />
          </div>
        )}
        <AttachmentsView items={r.attachments} />
      </div>

      {/* Audience & location (author only, not for marketplace resources) */}
      {canEdit && !r.is_public && r.scope_type !== "PUBLIC" && <VisibilityMoveControl resource={r} />}

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface p-4">
        <button
          onClick={() => starMut.mutate()}
          className={`btn btn-sm ${r.starred_by_me ? "btn-primary" : "btn-secondary"}`}
          disabled={starMut.isPending}
        >
          <Star className="h-3.5 w-3.5" fill={r.starred_by_me ? "currentColor" : "none"} />
          {r.starred_by_me ? "Starred" : "Star"}
        </button>

        <button
          onClick={() => pinMut.mutate()}
          className={`btn btn-sm ${r.pinned_by_me ? "btn-primary" : "btn-secondary"}`}
          disabled={pinMut.isPending}
          title={r.pinned_by_me ? "Unpin from your profile" : "Pin to your profile"}
        >
          {r.pinned_by_me ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
          {r.pinned_by_me ? "Pinned" : "Pin"}
        </button>

        <button
          onClick={async () => {
            // One canonical link for every resource. Public → opens for anyone;
            // private → only people with access can open it (enforced on open).
            await navigator.clipboard.writeText(`${WEB_URL}/r/${r.id}`);
            toast(
              r.is_public && r.approval_status === "approved"
                ? "Public link copied — anyone can open it"
                : "Private link copied — only people with access can open it"
            );
          }}
          className="btn btn-secondary btn-sm"
          title={
            r.is_public && r.approval_status === "approved"
              ? "Copy a public link anyone can open"
              : "Copy a private link — only people with access can open it"
          }
        >
          <Share2 className="h-3.5 w-3.5" /> Share
        </button>

        {canEdit && (
          <>
            <button onClick={() => openEdit(r)} className="btn btn-secondary btn-sm">
              <Pencil className="h-3.5 w-3.5" /> Edit
            </button>
            {(publishing.enabled || r.is_public) && (
              <button
                onClick={() => publishMut.mutate()}
                className={`btn btn-sm ${r.is_public ? "btn-secondary" : "btn-lime"}`}
                disabled={publishMut.isPending}
                title={r.is_public ? "Remove from marketplace" : "Publish to marketplace"}
              >
                <Globe className="h-3.5 w-3.5" />
                {r.is_public ? "Unpublish" : "Publish"}
              </button>
            )}
            <button
              onClick={async () => {
                if (
                  await confirm({
                    title: `Delete "${r.title}"?`,
                    message: "This permanently removes the resource. This cannot be undone.",
                  })
                )
                  deleteMut.mutate();
              }}
              className="btn btn-danger btn-sm ml-auto"
              disabled={deleteMut.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </>
        )}
        {r.is_public && (
          <a
            href={`/dashboard/marketplace/${r.id}`}
            className={`btn btn-secondary btn-sm ${canEdit ? "" : "ml-auto"}`}
            title="View marketplace page"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Marketplace page
          </a>
        )}
      </div>
    </>
  );
}

const VIS_BY_SCOPE: Record<string, ("POD" | "PROJECT" | "ORG")[]> = {
  POD: ["POD", "PROJECT", "ORG"],
  PROJECT: ["PROJECT", "ORG"],
  ORG: ["ORG"],
};

/** Author control to change a resource's audience (visibility) and move it
 *  between pod / project / org. Cascading pickers fetch projects then pods. */
function VisibilityMoveControl({ resource: r }: { resource: Resource }) {
  const { org } = useCurrentOrg();
  const invalidate = useInvalidateResources();
  const { toast } = useToast();
  const [moving, setMoving] = useState(false);
  const [destType, setDestType] = useState<"ORG" | "PROJECT" | "POD">("PROJECT");
  const [destProject, setDestProject] = useState("");
  const [destPod, setDestPod] = useState("");

  const { data: projects } = useQuery({
    queryKey: qk.projects(org?.slug ?? ""),
    queryFn: () => api.projects(org!.slug),
    enabled: !!org && moving,
  });
  const { data: pods } = useQuery({
    queryKey: qk.pods(destProject),
    queryFn: () => api.pods(destProject),
    enabled: !!destProject && destType === "POD",
  });

  const visMut = useMutation({
    mutationFn: (visibility: string) => api.updateResource(r.id, { visibility } as Partial<Resource>),
    onSuccess: async () => {
      await invalidate();
      toast("Audience updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const moveMut = useMutation({
    mutationFn: () => {
      const scope_id = destType === "ORG" ? org!.id : destType === "PROJECT" ? destProject : destPod;
      return api.moveResource(r.id, { scope_type: destType, scope_id });
    },
    onSuccess: async () => {
      await invalidate();
      toast("Resource moved");
      setMoving(false);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const visOptions = VIS_BY_SCOPE[r.scope_type] ?? [];
  const canMove =
    destType === "ORG" || (destType === "PROJECT" && destProject) || (destType === "POD" && destPod);

  return (
    <div className="border-t border-line bg-surface/60 p-4">
      <div className="flex flex-wrap items-center gap-3">
        {visOptions.length > 1 && (
          <label className="flex items-center gap-2 text-xs font-semibold text-muted">
            <Eye className="h-3.5 w-3.5" /> Who can see this
            <select
              value={r.visibility ?? r.scope_type}
              onChange={(e) => visMut.mutate(e.target.value)}
              disabled={visMut.isPending}
              className="rounded-full border border-line bg-card px-3 py-1 text-xs font-bold text-ink"
            >
              {visOptions.map((v) => (
                <option key={v} value={v}>{VISIBILITY_LABEL[v]}</option>
              ))}
            </select>
          </label>
        )}
        <button onClick={() => setMoving((m) => !m)} className="btn btn-secondary btn-sm ml-auto">
          <ExternalLink className="h-3.5 w-3.5" /> Move
        </button>
      </div>

      {moving && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={destType}
            onChange={(e) => { setDestType(e.target.value as "ORG" | "PROJECT" | "POD"); setDestPod(""); }}
            className="field !w-auto !py-1.5 text-sm"
          >
            <option value="ORG">Org</option>
            <option value="PROJECT">Project</option>
            <option value="POD">Pod</option>
          </select>
          {destType !== "ORG" && (
            <select value={destProject} onChange={(e) => { setDestProject(e.target.value); setDestPod(""); }} className="field !w-auto !py-1.5 text-sm">
              <option value="">Choose project…</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name.split("—")[0].trim()}</option>
              ))}
            </select>
          )}
          {destType === "POD" && destProject && (
            <select value={destPod} onChange={(e) => setDestPod(e.target.value)} className="field !w-auto !py-1.5 text-sm">
              <option value="">Choose pod…</option>
              {(pods ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          <button onClick={() => moveMut.mutate()} disabled={!canMove || moveMut.isPending} className="btn btn-primary btn-sm">
            Move here
          </button>
        </div>
      )}
    </div>
  );
}

export function ResourceDrawer() {
  const { drawer, closeDrawer } = useUi();
  const open = drawer.mode !== null;

  // lock scroll while open
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeDrawer();
    };
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closeDrawer]);

  if (!open) return null;

  return (
    <div
      className="overlay-fade fixed inset-0 z-[80] bg-navy/35 backdrop-blur-[2px]"
      onClick={closeDrawer}
      role="dialog"
      aria-modal
    >
      <div
        className="drawer-panel absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-card shadow-[-24px_0_64px_-24px_rgba(10,8,64,0.4)]"
        onClick={(e) => e.stopPropagation()}
      >
        {drawer.mode === "detail" && drawer.resource ? (
          <DetailView resource={drawer.resource} onClose={closeDrawer} />
        ) : (
          <ResourceForm
            mode={drawer.mode as "add" | "edit"}
            resource={drawer.resource}
            defaultScope={drawer.scope}
            onClose={closeDrawer}
          />
        )}
      </div>
    </div>
  );
}
