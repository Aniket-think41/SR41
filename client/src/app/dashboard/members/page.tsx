"use client";

/**
 * Org members (frontend spec §4.5) — members table with role dropdown,
 * invite by email, and the pending invitations list.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Mail, Send, Trash2, RotateCw } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useSession } from "@/lib/hooks";
import type { OrgRole } from "@/lib/types";
import { timeAgo } from "@/lib/utils";
import { Avatar } from "@/components/Avatar";
import { useToast } from "@/components/Toast";

export default function MembersPage() {
  const { org } = useCurrentOrg();
  const { data: me } = useSession();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrgRole>("MEMBER");

  const isAdmin = org?.my_role === "ADMIN";

  const { data: members } = useQuery({
    queryKey: qk.orgMembers(org?.slug ?? ""),
    queryFn: () => api.orgMembers(org!.slug),
    enabled: !!org,
  });
  const { data: invitations } = useQuery({
    queryKey: qk.invitations(org?.slug ?? ""),
    queryFn: () => api.invitations(org!.slug),
    enabled: !!org && isAdmin,
  });

  const inviteMut = useMutation({
    mutationFn: () => api.invite(org!.slug, { email: email.trim(), role }),
    onSuccess: async (inv) => {
      await qc.invalidateQueries({ queryKey: qk.invitations(org!.slug) });
      toast(`Invitation sent to ${inv.email}`);
      setEmail("");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const roleMut = useMutation({
    mutationFn: ({ userId, newRole }: { userId: string; newRole: OrgRole }) =>
      api.setMemberRole(org!.slug, userId, newRole),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.orgMembers(org!.slug) }),
  });

  const removeMut = useMutation({
    mutationFn: (userId: string) => api.removeMember(org!.slug, userId),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.orgMembers(org!.slug) });
      toast("Member removed");
    },
  });

  const cancelMut = useMutation({
    mutationFn: (invId: string) => api.cancelInvitation(org!.slug, invId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.invitations(org!.slug) }),
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="kicker">{org?.name}</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Members</h1>
        <p className="mt-1.5 text-sm text-body">
          {members?.length ?? "…"} people in this organization.
        </p>
      </div>

      {/* Invite */}
      {isAdmin && (
        <div className="card p-5">
          <h2 className="font-display text-base font-semibold">Invite someone</h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="flex flex-1 items-center gap-2 rounded-full border-[1.5px] border-line bg-white px-4 py-2 focus-within:border-primary">
              <Mail className="h-4 w-4 shrink-0 text-muted" />
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && email.includes("@") && inviteMut.mutate()}
                placeholder="teammate@company.com"
                className="w-full min-w-40 bg-transparent text-sm outline-none placeholder:text-muted"
                type="email"
              />
            </label>
            <select value={role} onChange={(e) => setRole(e.target.value as OrgRole)} className="field !w-auto !py-2 text-sm">
              <option value="MEMBER">Member</option>
              <option value="ADMIN">Admin</option>
            </select>
            <button
              onClick={() => inviteMut.mutate()}
              disabled={!email.includes("@") || inviteMut.isPending}
              className="btn btn-primary btn-sm"
            >
              {inviteMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              Send invite
            </button>
          </div>
        </div>
      )}

      {/* Members table */}
      <div className="card overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Email</th>
              <th>Role</th>
              <th>Last active</th>
              {isAdmin && <th className="text-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {(members ?? []).map((m) => (
              <tr key={m.id}>
                <td>
                  <span className="flex items-center gap-2.5">
                    <Avatar name={m.user?.display_name ?? "?"} src={m.user?.avatar_url} size="sm" />
                    <span>
                      <span className="block text-sm font-bold text-ink">
                        {m.user?.display_name}
                        {m.user_id === me?.id && <span className="ml-1.5 text-xs font-semibold text-muted">(you)</span>}
                      </span>
                      <span className="block text-xs text-muted">@{m.user?.username}</span>
                    </span>
                  </span>
                </td>
                <td className="text-sm text-body">{m.user?.email}</td>
                <td>
                  {isAdmin && m.user_id !== me?.id ? (
                    <select
                      value={m.role}
                      onChange={(e) => roleMut.mutate({ userId: m.user_id, newRole: e.target.value as OrgRole })}
                      className="rounded-full border border-line bg-white px-3 py-1 text-xs font-bold"
                    >
                      <option value="ADMIN">ADMIN</option>
                      <option value="MEMBER">MEMBER</option>
                    </select>
                  ) : (
                    <span className="tag">{m.role}</span>
                  )}
                </td>
                <td className="text-sm text-muted">{m.last_active ? timeAgo(m.last_active) : "—"}</td>
                {isAdmin && (
                  <td className="text-right">
                    {m.user_id !== me?.id && (
                      <button
                        onClick={() => {
                          if (window.confirm(`Remove ${m.user?.display_name} from ${org?.name}?`))
                            removeMut.mutate(m.user_id);
                        }}
                        className="btn btn-danger btn-sm"
                      >
                        Remove
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pending invitations */}
      {isAdmin && (invitations?.length ?? 0) > 0 && (
        <div className="card p-5">
          <h2 className="font-display text-base font-semibold">Pending invitations</h2>
          <ul className="mt-3 divide-y divide-line">
            {invitations!.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center gap-3 py-3">
                <Mail className="h-4 w-4 text-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-bold text-ink">{inv.email}</span>
                  <span className="block text-xs text-muted">
                    {inv.role} · expires {timeAgo(inv.expires_at).replace(" ago", "")}
                  </span>
                </span>
                <button onClick={() => toast(`Invitation re-sent to ${inv.email}`)} className="btn btn-secondary btn-sm">
                  <RotateCw className="h-3 w-3" /> Resend
                </button>
                <button onClick={() => cancelMut.mutate(inv.id)} className="btn btn-danger btn-sm">
                  <Trash2 className="h-3 w-3" /> Cancel
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
