"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, FolderKanban, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useTerms } from "@/lib/hooks";
import { useToast } from "@/components/Toast";

export default function ProjectsPage() {
  const { org } = useCurrentOrg();
  const terms = useTerms();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const { data: projects, isLoading } = useQuery({
    queryKey: qk.projects(org?.slug ?? ""),
    queryFn: () => api.projects(org!.slug),
    enabled: !!org,
  });

  const createMut = useMutation({
    mutationFn: () => api.createProject(org!.slug, { name: name.trim(), description: description.trim() }),
    onSuccess: async (p) => {
      await qc.invalidateQueries({ queryKey: qk.projects(org!.slug) });
      toast(`Project "${p.name}" created`);
      setCreating(false);
      setName("");
      setDescription("");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker">{org?.name}</p>
          <h1 className="font-display mt-1 text-3xl font-semibold">{terms.projects}</h1>
          <p className="mt-1.5 text-sm text-body">
            A {terms.project.toLowerCase()} groups related {terms.pods.toLowerCase()} together — structure work the way your team thinks.
          </p>
        </div>
        <button onClick={() => setCreating(true)} className="btn btn-primary">
          <Plus className="h-4 w-4" /> New {terms.project.toLowerCase()}
        </button>
      </div>

      {creating && (
        <div className="card pop mt-6 p-6">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold">Create a {terms.project.toLowerCase()}</h2>
            <button onClick={() => setCreating(false)} className="text-muted hover:text-ink" aria-label="Cancel">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="proj-name">Name *</label>
              <input id="proj-name" value={name} onChange={(e) => setName(e.target.value)} className="field" placeholder="Atlas — Customer Platform" autoFocus />
            </div>
            <div>
              <label className="field-label" htmlFor="proj-desc">Description</label>
              <input id="proj-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="field" placeholder="What is this body of work?" />
            </div>
          </div>
          <button
            onClick={() => createMut.mutate()}
            disabled={!name.trim() || createMut.isPending}
            className="btn btn-primary btn-sm mt-4"
          >
            {createMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create {terms.project.toLowerCase()}
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-40" />
          ))}
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {(projects ?? []).map((p, i) => (
            <Link
              key={p.id}
              href={`/dashboard/projects/${p.id}`}
              className="card card-hover reveal flex flex-col p-6"
              style={{ animationDelay: `${i * 0.05}s` }}
            >
              <div className="flex items-start justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary">
                  <FolderKanban className="h-5 w-5" />
                </span>
                <span className="tag">{p.visibility === "ORG" ? "Org-visible" : "Public"}</span>
              </div>
              <h2 className="font-display mt-4 text-xl font-semibold">{p.name}</h2>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-body">{p.description}</p>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
                <span className="flex gap-1.5">
                  {p.tags.map((t) => (
                    <span key={t} className="text-xs text-muted">#{t}</span>
                  ))}
                </span>
                <span className="text-xs font-semibold text-muted">
                  {p.pods_count} {terms.pods.toLowerCase()} · {p.resources_count} resources
                </span>
              </div>
            </Link>
          ))}
          {projects?.length === 0 && !creating && (
            <div className="col-span-full rounded-2xl border border-dashed border-line bg-white/60 p-16 text-center">
              <p className="font-display text-xl font-semibold">No {terms.projects.toLowerCase()} yet.</p>
              <p className="mt-1 text-sm text-body">Create the first one — {terms.pods.toLowerCase()} and resources live inside.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
