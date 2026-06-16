"use client";

/**
 * Generic member list + add picker, shared by project & pod settings.
 * Candidates are org members not already in the list.
 */

import { useState } from "react";
import { UserPlus, Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { qk, useCurrentOrg } from "@/lib/hooks";
import type { User } from "@/lib/types";
import { Avatar } from "../Avatar";

export interface MemberRow {
  id: string;
  user_id: string;
  role: string;
  user?: User;
}

export function MembersCard({
  members,
  roles,
  onAdd,
  adding,
}: {
  members: MemberRow[];
  roles: string[];
  onAdd: (userId: string, role: string) => void;
  adding?: boolean;
}) {
  const { org } = useCurrentOrg();
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState(roles[roles.length - 1]);

  const { data: orgMembers } = useQuery({
    queryKey: qk.orgMembers(org?.slug ?? ""),
    queryFn: () => api.orgMembers(org!.slug),
    enabled: !!org,
  });

  const existing = new Set(members.map((m) => m.user_id));
  const candidates = (orgMembers ?? []).filter((m) => !existing.has(m.user_id));

  return (
    <div className="card p-6">
      <h2 className="font-display text-lg font-semibold">Members</h2>

      <ul className="mt-4 divide-y divide-line">
        {members.map((m) => (
          <li key={m.id} className="flex items-center gap-3 py-3">
            <Avatar name={m.user?.display_name ?? "?"} src={m.user?.avatar_url} size="sm" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold text-ink">{m.user?.display_name}</span>
              <span className="block truncate text-xs text-muted">@{m.user?.username}</span>
            </span>
            <span className="tag">{m.role}</span>
          </li>
        ))}
      </ul>

      {candidates.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <select value={userId} onChange={(e) => setUserId(e.target.value)} className="field !w-auto flex-1 !py-2 text-sm">
            <option value="">Add an org member…</option>
            {candidates.map((c) => (
              <option key={c.user_id} value={c.user_id}>
                {c.user?.display_name} (@{c.user?.username})
              </option>
            ))}
          </select>
          <select value={role} onChange={(e) => setRole(e.target.value)} className="field !w-auto !py-2 text-sm">
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            onClick={() => userId && onAdd(userId, role)}
            disabled={!userId || adding}
            className="btn btn-primary btn-sm"
          >
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
            Add
          </button>
        </div>
      )}
    </div>
  );
}
