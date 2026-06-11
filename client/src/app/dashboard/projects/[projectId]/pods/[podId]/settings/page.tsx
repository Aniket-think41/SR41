"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import { MembersCard } from "@/components/dashboard/MembersCard";
import { useToast } from "@/components/Toast";

export default function PodSettings({
  params,
}: {
  params: Promise<{ projectId: string; podId: string }>;
}) {
  const { projectId, podId } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: pod } = useQuery({
    queryKey: qk.pod(podId),
    queryFn: () => api.pod(projectId, podId),
  });
  const { data: members } = useQuery({
    queryKey: [...qk.pod(podId), "members"],
    queryFn: () => api.podMembers(projectId, podId),
  });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState("");
  // hydrate once the pod loads — render-time adjust
  const [loadedId, setLoadedId] = useState<string | null>(null);
  if (pod && pod.id !== loadedId) {
    setLoadedId(pod.id);
    setName(pod.name);
    setDescription(pod.description);
    setPurpose(pod.purpose_tag);
  }

  const saveMut = useMutation({
    mutationFn: () =>
      api.updatePod(projectId, podId, {
        name: name.trim(),
        description: description.trim(),
        purpose_tag: purpose.trim(),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.pod(podId) });
      await qc.invalidateQueries({ queryKey: qk.pods(projectId) });
      toast("Pod updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const addMemberMut = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.addPodMember(projectId, podId, { user_id: userId, role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...qk.pod(podId), "members"] }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deletePod(projectId, podId),
    onSuccess: async () => {
      await qc.invalidateQueries();
      toast("Pod deleted");
      router.replace(`/dashboard/projects/${projectId}`);
    },
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <p className="kicker">Pod settings</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">{pod?.name ?? "…"}</h1>
      </div>

      <div className="card p-6">
        <h2 className="font-display text-lg font-semibold">General</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="field-label" htmlFor="pod-name">Name</label>
            <input id="pod-name" value={name} onChange={(e) => setName(e.target.value)} className="field" />
          </div>
          <div>
            <label className="field-label" htmlFor="pod-desc">Description</label>
            <textarea id="pod-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="field resize-y" rows={3} />
          </div>
          <div>
            <label className="field-label" htmlFor="pod-purpose">Purpose tag</label>
            <input id="pod-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} className="field" placeholder="rag, frontend, devex…" />
          </div>
          <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !name.trim()} className="btn btn-primary btn-sm">
            {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save changes
          </button>
        </div>
      </div>

      <MembersCard
        members={members ?? []}
        roles={["OWNER", "MEMBER"]}
        onAdd={(userId, role) => addMemberMut.mutate({ userId, role })}
        adding={addMemberMut.isPending}
      />

      <div className="card border-[var(--color-danger)]/30 p-6">
        <h2 className="font-display text-lg font-semibold text-[var(--color-danger)]">Danger zone</h2>
        <p className="mt-1 text-sm text-body">Deleting a pod removes its pod-scoped resources.</p>
        <button
          onClick={() => {
            if (window.confirm(`Delete "${pod?.name}"?`)) deleteMut.mutate();
          }}
          className="btn btn-danger btn-sm mt-4"
          disabled={deleteMut.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete pod
        </button>
      </div>
    </div>
  );
}
