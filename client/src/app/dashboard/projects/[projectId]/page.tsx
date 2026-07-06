"use client";

/**
 * Project detail — pods list + project-level resources (frontend spec route map).
 */

import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Plus, Settings, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useTerms } from "@/lib/hooks";
import { ResourceBrowser } from "@/components/ResourceBrowser";
import { useToast } from "@/components/Toast";

export default function ProjectDetail({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { org } = useCurrentOrg();
  const terms = useTerms();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");

  const { data: project } = useQuery({
    queryKey: qk.project(projectId),
    queryFn: () => api.project(org!.slug, projectId),
    enabled: !!org,
  });
  const { data: pods, isLoading: podsLoading } = useQuery({
    queryKey: qk.pods(projectId),
    queryFn: () => api.pods(projectId),
  });

  const createPod = useMutation({
    mutationFn: () => api.createPod(projectId, { name: name.trim(), purpose_tag: purpose.trim() }),
    onSuccess: async (pod) => {
      await qc.invalidateQueries({ queryKey: qk.pods(projectId) });
      toast(`Pod "${pod.name}" created`);
      setCreating(false);
      setName("");
      setPurpose("");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker">{terms.project}</p>
          <h1 className="font-display mt-1 text-3xl font-semibold">{project?.name ?? "…"}</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-body">{project?.description}</p>
          <div className="mt-2 flex gap-1.5">
            {project?.tags.map((t) => (
              <span key={t} className="tag">#{t}</span>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <Link href={`/dashboard/projects/${projectId}/settings`} className="btn btn-secondary btn-sm">
            <Settings className="h-3.5 w-3.5" /> Settings
          </Link>
          <button onClick={() => setCreating(true)} className="btn btn-primary btn-sm">
            <Plus className="h-3.5 w-3.5" /> New {terms.pod.toLowerCase()}
          </button>
        </div>
      </div>

      {/* Pods */}
      <section>
        <h2 className="font-display mb-4 text-lg font-semibold">{terms.pods}</h2>

        {creating && (
          <div className="card pop mb-4 p-5">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-semibold">Create a {terms.pod.toLowerCase()}</h3>
              <button onClick={() => setCreating(false)} className="text-muted hover:text-ink" aria-label="Cancel">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_200px_auto]">
              <input value={name} onChange={(e) => setName(e.target.value)} className="field" placeholder={`${terms.pod} name — e.g. Retrieval ${terms.pod}`} autoFocus />
              <input value={purpose} onChange={(e) => setPurpose(e.target.value)} className="field" placeholder="Purpose tag — e.g. rag" />
              <button onClick={() => createPod.mutate()} disabled={!name.trim() || createPod.isPending} className="btn btn-primary btn-sm">
                {createPod.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
              </button>
            </div>
          </div>
        )}

        {podsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="skeleton h-36" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {(pods ?? []).map((pod) => (
              <Link
                key={pod.id}
                href={`/dashboard/projects/${projectId}/pods/${pod.id}`}
                className="card card-hover flex flex-col p-5"
              >
                <div className="flex items-start justify-between">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-scope-pod-bg)] text-[var(--color-scope-pod)]">
                    <Boxes className="h-4.5 w-4.5" />
                  </span>
                  {pod.purpose_tag && <span className="tag">{pod.purpose_tag}</span>}
                </div>
                <h3 className="font-display mt-3 text-lg font-semibold">{pod.name}</h3>
                <p className="mt-1 line-clamp-2 flex-1 text-sm text-body">{pod.description}</p>
                <p className="mt-3 border-t border-line pt-3 text-xs font-semibold text-muted">
                  {pod.members_count} members · {pod.resources_count} own resources
                </p>
              </Link>
            ))}
            {pods?.length === 0 && !creating && (
              <div className="col-span-full rounded-2xl border border-dashed border-line bg-white/60 p-12 text-center">
                <p className="font-display text-lg font-semibold">No {terms.pods.toLowerCase()} yet.</p>
                <p className="mt-1 text-sm text-body">{terms.pods} hold the people and the resources they share.</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Project-level resources */}
      <section>
        <h2 className="font-display mb-4 text-lg font-semibold">{terms.project} resources</h2>
        <ResourceBrowser
          queryKey={["project", projectId, "resources"]}
          fetcher={(q) => api.projectResources(projectId, q)}
          contextScope="PROJECT"
          addScope={{ scope_type: "PROJECT", scope_id: projectId }}
          emptyHint={`Resources added here are inherited by every ${terms.pod.toLowerCase()} in this ${terms.project.toLowerCase()}.`}
        />
      </section>
    </div>
  );
}
