"use client";

/**
 * Marketplace resource detail — full page (not drawer) with
 * "Add to my org" for the signed-in user (frontend spec §4.4).
 */

import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, Check, Copy, Download, Loader2, PackagePlus, Star,
} from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useInvalidateResources } from "@/lib/hooks";
import { fmt, longDate } from "@/lib/utils";
import { Markdown } from "@/lib/markdown";
import { Avatar } from "@/components/Avatar";
import { TypeBadge } from "@/components/badges";
import { useToast } from "@/components/Toast";
import { FeatureGate } from "@/components/FeatureGate";

function CopyBtn({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="btn btn-secondary btn-sm"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[var(--color-success)]" /> : <Copy className="h-3.5 w-3.5" />}
      {copied ? "Copied" : label}
    </button>
  );
}

export default function MarketplaceDetail({ params }: { params: Promise<{ id: string }> }) {
  return (
    <FeatureGate feature="marketplace" title="The public marketplace">
      <Detail params={params} />
    </FeatureGate>
  );
}

function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { org } = useCurrentOrg();
  const invalidate = useInvalidateResources();
  const { toast } = useToast();

  const { data: r, isLoading } = useQuery({
    queryKey: qk.publicResource(id),
    queryFn: () => api.publicResource(id),
  });

  const starMut = useMutation({
    mutationFn: () => (r?.starred_by_me ? api.unstar(id) : api.star(id)),
    onSuccess: invalidate,
  });

  const importMut = useMutation({
    mutationFn: () => api.importResource(id, org!.slug),
    onSuccess: async (copy) => {
      await invalidate();
      toast(`"${copy.title}" added to ${org?.name} — find it in Org Resources`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (isLoading)
    return <div className="skeleton mx-auto h-96 max-w-3xl" />;
  if (!r)
    return (
      <div className="py-20 text-center">
        <p className="font-display text-2xl font-semibold">Resource not found.</p>
        <Link href="/dashboard/marketplace" className="btn btn-secondary btn-sm mt-4">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to marketplace
        </Link>
      </div>
    );

  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/dashboard/marketplace" className="mb-5 inline-flex items-center gap-1.5 text-sm font-semibold text-muted transition hover:text-primary">
        <ArrowLeft className="h-3.5 w-3.5" /> Marketplace
      </Link>

      <div className="card overflow-hidden">
        {/* Header */}
        <div className="border-b border-line bg-gradient-to-br from-white to-surface-2 p-8">
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge type={r.type} />
            <span className="code text-xs text-muted">v{r.version}</span>
          </div>
          <h1 className="font-display mt-3 text-3xl font-semibold sm:text-4xl">{r.title}</h1>
          <p className="mt-2 max-w-2xl text-[0.95rem] leading-relaxed text-body">{r.description}</p>

          <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3">
            {r.scope_type === "ORG" && r.scope_name ? (
              <span className="flex items-center gap-2" title={`Published by ${r.scope_name}`}>
                <Avatar name={r.scope_name} size="sm" />
                <span>
                  <span className="block text-sm font-bold text-ink">{r.scope_name}</span>
                  <span className="block text-xs text-muted">Organization</span>
                </span>
              </span>
            ) : (
              <Link
                href={r.author?.username ? `/dashboard/publishers/${r.author.username}` : "#"}
                className="group flex items-center gap-2"
                title={`View ${r.author?.display_name}'s publisher page`}
              >
                <Avatar name={r.author?.display_name ?? "?"} src={r.author?.avatar_url} size="sm" />
                <span>
                  <span className="block text-sm font-bold text-ink group-hover:text-primary group-hover:underline">
                    {r.author?.display_name}
                    {r.author?.verified && <span className="ml-1 text-primary" title="Think41-verified">✦</span>}
                  </span>
                  <span className="block text-xs text-muted">@{r.author?.username}</span>
                </span>
              </Link>
            )}
            <span className="text-sm text-muted">↓ {fmt(r.installs_count ?? 0)} installs</span>
            <span className="text-sm text-muted">★ {fmt(r.stars_count)} stars</span>
            <span className="text-sm text-muted">Updated {longDate(r.updated_at)}</span>
          </div>

          <div className="mt-6 flex flex-wrap gap-2">
            <button onClick={() => importMut.mutate()} disabled={importMut.isPending || !org} className="btn btn-primary btn-sm">
              {importMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PackagePlus className="h-3.5 w-3.5" />}
              Add to {org?.name ?? "my org"}
            </button>
            <button
              onClick={() => starMut.mutate()}
              className={`btn btn-sm ${r.starred_by_me ? "btn-primary" : "btn-secondary"}`}
            >
              <Star className="h-3.5 w-3.5" fill={r.starred_by_me ? "currentColor" : "none"} />
              {r.starred_by_me ? "Starred" : "Star"}
            </button>
            {r.type === "SKILL" && r.file_url && (
              <a href={r.file_url} className="btn btn-lime btn-sm" download>
                <Download className="h-3.5 w-3.5" /> Download .skill
              </a>
            )}
            {r.type === "SKILL" && <CopyBtn text={r.content_md} label="Copy SKILL.md" />}
            {r.type === "MCP" && r.server_url && <CopyBtn text={r.server_url} label="Copy server URL" />}
            {r.type === "MCP" && r.config_json && <CopyBtn text={r.config_json} label="Copy config JSON" />}
          </div>
        </div>

        {/* Body */}
        <div className="p-8">
          {r.type === "MCP" && r.config_json && (
            <pre className="thin-scroll mb-6 overflow-x-auto rounded-2xl bg-navy p-5 text-xs leading-relaxed text-[#e8e6ff]">
              <code className="code">{r.config_json}</code>
            </pre>
          )}
          <Markdown source={r.content_md || "_No content provided._"} />

          {r.tags.length > 0 && (
            <div className="mt-8 flex flex-wrap gap-1.5 border-t border-line pt-5">
              {r.tags.map((t) => (
                <span key={t} className="tag">#{t}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
