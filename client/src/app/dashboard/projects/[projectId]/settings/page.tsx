"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg } from "@/lib/hooks";
import { MembersCard } from "@/components/dashboard/MembersCard";
import { useToast } from "@/components/Toast";

export default function ProjectSettings({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { org } = useCurrentOrg();
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: project } = useQuery({
    queryKey: qk.project(projectId),
    queryFn: () => api.project(org!.slug, projectId),
    enabled: !!org,
  });
  const { data: members } = useQuery({
    queryKey: [...qk.project(projectId), "members"],
    queryFn: () => api.projectMembers(org!.slug, projectId),
    enabled: !!org,
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  // hydrate once the project loads — render-time adjust
  const [loadedId, setLoadedId] = useState<string | null>(null);
  if (project && project.id !== loadedId) {
    setLoadedId(project.id);
    setName(project.name);
    setDescription(project.description);
    setTags(project.tags.join(", "));
  }

  const saveMut = useMutation({
    mutationFn: () =>
      api.updateProject(org!.slug, projectId, {
        name: name.trim(),
        description: description.trim(),
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.project(projectId) });
      await qc.invalidateQueries({ queryKey: qk.projects(org!.slug) });
      toast("Project updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const addMemberMut = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.addProjectMember(org!.slug, projectId, { user_id: userId, role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...qk.project(projectId), "members"] }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deleteProject(org!.slug, projectId),
    onSuccess: async () => {
      await qc.invalidateQueries();
      toast("Project deleted");
      router.replace("/dashboard/projects");
    },
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <p className="kicker">Project settings</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">{project?.name ?? "…"}</h1>
      </div>

      <div className="card p-6">
        <h2 className="font-display text-lg font-semibold">General</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="field-label" htmlFor="ps-name">Name</label>
            <input id="ps-name" value={name} onChange={(e) => setName(e.target.value)} className="field" />
          </div>
          <div>
            <label className="field-label" htmlFor="ps-desc">Description</label>
            <textarea id="ps-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="field resize-y" rows={3} />
          </div>
          <div>
            <label className="field-label" htmlFor="ps-tags">Tags (comma-separated)</label>
            <input id="ps-tags" value={tags} onChange={(e) => setTags(e.target.value)} className="field" placeholder="platform, rag, api" />
          </div>
          <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !name.trim()} className="btn btn-primary btn-sm">
            {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save changes
          </button>
        </div>
      </div>

      <MembersCard
        members={members ?? []}
        roles={["LEAD", "MEMBER"]}
        onAdd={(userId, role) => addMemberMut.mutate({ userId, role })}
        adding={addMemberMut.isPending}
      />

      <div className="card border-[var(--color-danger)]/30 p-6">
        <h2 className="font-display text-lg font-semibold text-[var(--color-danger)]">Danger zone</h2>
        <p className="mt-1 text-sm text-body">
          Deleting a project removes its pods and all pod/project-scoped resources.
        </p>
        <button
          onClick={() => {
            if (window.confirm(`Delete "${project?.name}" and everything inside it?`)) deleteMut.mutate();
          }}
          className="btn btn-danger btn-sm mt-4"
          disabled={deleteMut.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete project
        </button>
      </div>
    </div>
  );
}
