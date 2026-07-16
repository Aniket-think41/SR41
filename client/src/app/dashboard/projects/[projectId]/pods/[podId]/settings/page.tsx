"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useSession } from "@/lib/hooks";
import { MembersCard } from "@/components/dashboard/MembersCard";
import { ScopeRepoLinks } from "@/components/dashboard/ScopeRepoLinks";
import { useToast } from "@/components/Toast";
import { useConfirm } from "@/components/ConfirmDelete";

export default function PodSettings({
  params,
}: {
  params: Promise<{ projectId: string; podId: string }>;
}) {
  const { projectId, podId } = use(params);
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { org } = useCurrentOrg();
  const { data: me } = useSession();

  const { data: pod } = useQuery({
    queryKey: qk.pod(podId),
    queryFn: () => api.pod(projectId, podId),
  });
  const { data: members } = useQuery({
    queryKey: [...qk.pod(podId), "members"],
    queryFn: () => api.podMembers(podId),
  });
  const selfRole = members?.find((m) => m.user_id === me?.id)?.role;
  const canManage =
    org?.my_role === "ADMIN" || selfRole === "ADMIN" || selfRole === "OWNER";

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

  const invalidateMembers = () =>
    qc.invalidateQueries({ queryKey: [...qk.pod(podId), "members"] });

  const addMemberMut = useMutation({
    mutationFn: ({ payload, role }: { payload: { user_id?: string; email?: string }; role: string }) =>
      api.addPodMember(podId, { ...payload, role }),
    onSuccess: async (m) => {
      await invalidateMembers();
      toast(`Added ${m.user?.display_name ?? "member"}`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const roleMut = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.setPodMemberRole(podId, userId, role),
    onSuccess: invalidateMembers,
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const removeMut = useMutation({
    mutationFn: (userId: string) => api.removePodMember(podId, userId),
    onSuccess: async () => {
      await invalidateMembers();
      toast("Member removed");
    },
    onError: (e) => toast(errorMessage(e), "error"),
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
        onAdd={(payload, role) => addMemberMut.mutate({ payload, role })}
        onChangeRole={(userId, role) => roleMut.mutate({ userId, role })}
        onRemove={async (userId) => {
          if (await confirm({ title: "Remove this member?", message: "They lose access to this pod.", requireType: null, confirmLabel: "Remove" }))
            removeMut.mutate(userId);
        }}
        adding={addMemberMut.isPending}
        canManage={canManage}
        selfUserId={me?.id}
      />

      {/* GitHub repos attached to this pod (only when GitHub is connected) */}
      <ScopeRepoLinks scopeType="POD" scopeId={podId} title="Pod repositories" />

      <div className="card border-[var(--color-danger)]/30 p-6">
        <h2 className="font-display text-lg font-semibold text-[var(--color-danger)]">Danger zone</h2>
        <p className="mt-1 text-sm text-body">Deleting a pod removes its pod-scoped resources.</p>
        <button
          onClick={async () => {
            if (
              await confirm({
                title: `Delete "${pod?.name}"?`,
                message: "This removes the pod and its pod-scoped resources. This cannot be undone.",
              })
            )
              deleteMut.mutate();
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
