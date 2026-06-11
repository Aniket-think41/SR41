"use client";

/**
 * Add / Edit resource form (frontend spec §4.3) — three steps:
 *   1. choose type (visual cards)   2. details   3. content per type.
 * Scope defaults to the opening context but can be overridden.
 */

import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Loader2, Upload, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useInvalidateResources, useTerms } from "@/lib/hooks";
import type { Resource, ResourceType, ScopeType } from "@/lib/types";
import { TYPE_META, SCOPE_META } from "@/lib/utils";
import { MarkdownEditor } from "./MarkdownEditor";
import { useToast } from "./Toast";

const schema = z.object({
  title: z.string().min(1, "Title is required").max(120),
  description: z.string().max(500).optional().or(z.literal("")),
  version: z
    .string()
    .regex(/^\d+\.\d+\.\d+$/, "Use semver, e.g. 1.0.0")
    .optional()
    .or(z.literal("")),
});
type Details = z.infer<typeof schema>;

const TYPE_CARDS: { type: ResourceType; blurb: string }[] = [
  { type: "SKILL", blurb: "A reusable capability for agents — packaged with a SKILL.md." },
  { type: "MCP", blurb: "A server your agents connect to — URL plus config JSON." },
  { type: "NOTE", blurb: "Team knowledge in markdown — playbooks, conventions, decisions." },
];

interface ScopeOption {
  scope_type: ScopeType;
  scope_id: string | null;
  label: string;
}

export function ResourceForm({
  mode,
  resource,
  defaultScope,
  onClose,
}: {
  mode: "add" | "edit";
  resource: Resource | null;
  defaultScope?: { scope_type: ScopeType; scope_id: string | null };
  onClose: () => void;
}) {
  const editing = mode === "edit" && resource;
  const { org } = useCurrentOrg();
  const invalidate = useInvalidateResources();
  const { toast } = useToast();
  const terms = useTerms();
  const scopeLabel = (s: ScopeType) =>
    s === "POD" ? terms.pod : s === "PROJECT" ? terms.project : SCOPE_META[s].label;

  const [step, setStep] = useState(editing ? 2 : 1);
  const [type, setType] = useState<ResourceType>(resource?.type ?? "SKILL");
  const [tags, setTags] = useState<string[]>(resource?.tags ?? []);
  const [tagInput, setTagInput] = useState("");
  const [contentMd, setContentMd] = useState(resource?.content_md ?? "");
  const [serverUrl, setServerUrl] = useState(resource?.server_url ?? "");
  const [configJson, setConfigJson] = useState(resource?.config_json ?? "");
  const [fileUrl, setFileUrl] = useState<string | null>(resource?.file_url ?? null);
  const [uploading, setUploading] = useState(false);

  // Scope options: current context + parents (override allowed, spec §4.3)
  const { data: projects } = useQuery({
    queryKey: qk.projects(org?.slug ?? ""),
    queryFn: () => api.projects(org!.slug),
    enabled: !!org,
  });
  const scopeOptions = useMemo<ScopeOption[]>(() => {
    const opts: ScopeOption[] = [];
    if (org) opts.push({ scope_type: "ORG", scope_id: org.id, label: `Org — ${org.name}` });
    for (const p of projects ?? [])
      opts.push({ scope_type: "PROJECT", scope_id: p.id, label: `${terms.project} — ${p.name.split("—")[0].trim()}` });
    return opts;
  }, [org, projects, terms.project]);

  const initialScope = editing
    ? { scope_type: resource.scope_type, scope_id: resource.scope_id }
    : defaultScope ?? scopeOptions[0];
  const [scope, setScope] = useState<{ scope_type: ScopeType; scope_id: string | null } | undefined>(initialScope);

  // If opened from a pod, that pod is the first (default) option.
  const allScopeOptions = useMemo<ScopeOption[]>(() => {
    const opts = [...scopeOptions];
    const cur = initialScope;
    if (cur && !opts.some((o) => o.scope_type === cur.scope_type && o.scope_id === cur.scope_id)) {
      opts.unshift({ ...cur, label: `${scopeLabel(cur.scope_type)} — current` });
    }
    return opts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeOptions]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Details>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: resource?.title ?? "",
      description: resource?.description ?? "",
      version: resource?.version ?? "0.1.0",
    },
  });

  const addTag = () => {
    const t = tagInput.trim().toLowerCase().replace(/\s+/g, "-");
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setTagInput("");
  };

  const mutation = useMutation({
    mutationFn: async (details: Details) => {
      const body = {
        type,
        title: details.title,
        description: details.description ?? "",
        version: details.version || "0.1.0",
        tags,
        content_md: contentMd,
        server_url: type === "MCP" ? serverUrl : undefined,
        config_json: type === "MCP" ? configJson : undefined,
        file_url: fileUrl,
        scope_type: scope?.scope_type ?? "ORG",
        scope_id: scope?.scope_id ?? null,
      };
      return editing ? api.updateResource(resource.id, body) : api.createResource(body);
    },
    onSuccess: async (r) => {
      await invalidate();
      toast(editing ? `"${r.title}" updated` : `"${r.title}" added to ${scopeLabel(r.scope_type)}`);
      onClose();
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const mockUpload = async (file: File) => {
    setUploading(true);
    try {
      const { file_url } = await api.upload(file.name);
      setFileUrl(file_url);
      toast(`"${file.name}" uploaded`);
    } finally {
      setUploading(false);
    }
  };

  const onSubmit = handleSubmit((d) => mutation.mutate(d));

  return (
    <form onSubmit={onSubmit} className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line p-6 pb-4">
        <div>
          <p className="kicker">{editing ? "Edit resource" : `Step ${step} of 3`}</p>
          <h2 className="font-display mt-1 text-xl font-semibold">
            {editing ? resource.title : step === 1 ? "What are you adding?" : step === 2 ? "The details" : "The content"}
          </h2>
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-1.5 text-muted transition hover:bg-surface hover:text-ink" aria-label="Close">
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Body */}
      <div className="thin-scroll flex-1 overflow-y-auto p-6">
        {step === 1 && (
          <div className="space-y-3">
            {TYPE_CARDS.map((c) => {
              const meta = TYPE_META[c.type];
              const active = type === c.type;
              return (
                <button
                  key={c.type}
                  type="button"
                  onClick={() => setType(c.type)}
                  className={`card flex w-full items-start gap-4 p-5 text-left transition ${
                    active ? "!border-primary ring-2 ring-primary/20" : "hover:!border-primary/40"
                  }`}
                >
                  <span
                    className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-lg text-white"
                    style={{ backgroundColor: meta.color }}
                    aria-hidden
                  >
                    {meta.glyph}
                  </span>
                  <span>
                    <span className="font-display block text-lg font-semibold">{meta.label}</span>
                    <span className="mt-0.5 block text-sm text-body">{c.blurb}</span>
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            <div>
              <label className="field-label" htmlFor="rf-title">Title *</label>
              <input id="rf-title" {...register("title")} className="field" placeholder="e.g. PR Reviewer" />
              {errors.title && <p className="field-error">{errors.title.message}</p>}
            </div>

            <div>
              <label className="field-label" htmlFor="rf-desc">Description</label>
              <textarea
                id="rf-desc"
                {...register("description")}
                className="field resize-y"
                rows={3}
                placeholder="One or two sentences on what this does and when to use it."
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="field-label" htmlFor="rf-version">Version</label>
                <input id="rf-version" {...register("version")} className="field code" placeholder="1.0.0" />
                {errors.version && <p className="field-error">{errors.version.message}</p>}
              </div>
              <div>
                <label className="field-label" htmlFor="rf-scope">Scope</label>
                <select
                  id="rf-scope"
                  className="field"
                  value={`${scope?.scope_type}:${scope?.scope_id ?? ""}`}
                  onChange={(e) => {
                    const [st, si] = e.target.value.split(":");
                    setScope({ scope_type: st as ScopeType, scope_id: si || null });
                  }}
                >
                  {allScopeOptions.map((o) => (
                    <option key={`${o.scope_type}:${o.scope_id}`} value={`${o.scope_type}:${o.scope_id ?? ""}`}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="field-label" htmlFor="rf-tags">Tags</label>
              <div className="field flex flex-wrap items-center gap-1.5 !py-2">
                {tags.map((t) => (
                  <span key={t} className="tag">
                    #{t}
                    <button type="button" onClick={() => setTags(tags.filter((x) => x !== t))} aria-label={`Remove ${t}`}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                <input
                  id="rf-tags"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      addTag();
                    }
                  }}
                  onBlur={addTag}
                  placeholder={tags.length ? "" : "code-review, github, …"}
                  className="min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
                />
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            {type === "MCP" ? (
              <>
                <div>
                  <label className="field-label" htmlFor="rf-url">Server URL</label>
                  <input
                    id="rf-url"
                    value={serverUrl}
                    onChange={(e) => setServerUrl(e.target.value)}
                    className="field code"
                    placeholder="https://mcp.example.com/server"
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="rf-config">Config JSON</label>
                  <textarea
                    id="rf-config"
                    value={configJson}
                    onChange={(e) => setConfigJson(e.target.value)}
                    className="field code resize-y"
                    rows={8}
                    placeholder='{ "mcpServers": { … } }'
                  />
                </div>
                <div>
                  <label className="field-label">Notes (optional)</label>
                  <MarkdownEditor value={contentMd} onChange={setContentMd} rows={5} placeholder="Anything teammates should know before connecting…" />
                </div>
              </>
            ) : (
              <>
                {type === "SKILL" && (
                  <div>
                    <label className="field-label">Skill package (.skill)</label>
                    <label className="flex cursor-pointer items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line bg-surface px-4 py-6 text-sm font-semibold text-muted transition hover:border-primary hover:text-primary">
                      {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                      {fileUrl ? fileUrl.split("/").pop() : "Upload .skill package (max 10 MB)"}
                      <input
                        type="file"
                        accept=".skill,.zip"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) mockUpload(f);
                        }}
                      />
                    </label>
                  </div>
                )}
                <div>
                  <label className="field-label">{type === "SKILL" ? "SKILL.md" : "Note content"}</label>
                  <MarkdownEditor
                    value={contentMd}
                    onChange={setContentMd}
                    rows={type === "SKILL" ? 12 : 14}
                    placeholder={type === "SKILL" ? "# My Skill\n\nWhat it does, inputs, behavior…" : "# Title\n\nWrite the note…"}
                  />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-line bg-surface p-4">
        {step > (editing ? 2 : 1) ? (
          <button type="button" onClick={() => setStep(step - 1)} className="btn btn-secondary btn-sm">
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
        ) : (
          <span />
        )}

        {step < 3 ? (
          <button
            type="button"
            onClick={async () => {
              // validate details before leaving step 2
              if (step === 2) {
                const valid = await new Promise<boolean>((resolve) =>
                  handleSubmit(() => resolve(true), () => resolve(false))()
                );
                if (!valid) return;
              }
              setStep(step + 1);
            }}
            className="btn btn-primary btn-sm"
          >
            Continue <ArrowRight className="h-3.5 w-3.5" />
          </button>
        ) : (
          <button type="submit" className="btn btn-primary btn-sm" disabled={mutation.isPending}>
            {mutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {editing ? "Save changes" : "Add resource"}
          </button>
        )}
      </div>
    </form>
  );
}
