"use client";

/**
 * Generic member list + management, shared by project & pod settings.
 * Admins can add people (pick an existing org member OR type any email —
 * unknown emails are auto-provisioned and emailed a temp password), change a
 * member's role (Admin | Member), and remove them.
 */

import { useState } from "react";
import { UserPlus, Loader2, Mail, Users, Trash2 } from "lucide-react";
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

/** Display any legacy role (LEAD/OWNER) as ADMIN in the UI. */
const asAdminMember = (role: string) => (role.toUpperCase() === "MEMBER" ? "MEMBER" : "ADMIN");

export function MembersCard({
  members,
  onAdd,
  onChangeRole,
  onRemove,
  adding,
  canManage = true,
  selfUserId,
}: {
  members: MemberRow[];
  /** Add by an existing org member (user_id) or a raw email. */
  onAdd: (payload: { user_id?: string; email?: string }, role: string) => void;
  onChangeRole?: (userId: string, role: string) => void;
  onRemove?: (userId: string) => void;
  adding?: boolean;
  canManage?: boolean;
  selfUserId?: string;
}) {
  const { org } = useCurrentOrg();
  const [mode, setMode] = useState<"member" | "email">("member");
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("MEMBER");

  const { data: orgMembers } = useQuery({
    queryKey: qk.orgMembers(org?.slug ?? ""),
    queryFn: () => api.orgMembers(org!.slug),
    enabled: !!org && canManage,
  });

  const existing = new Set(members.map((m) => m.user_id));
  const candidates = (orgMembers ?? []).filter((m) => !existing.has(m.user_id));

  const submit = () => {
    if (mode === "email") {
      if (email.includes("@")) onAdd({ email: email.trim() }, role);
    } else if (userId) {
      onAdd({ user_id: userId }, role);
    }
    setEmail("");
    setUserId("");
  };

  return (
    <div className="card p-6">
      <h2 className="font-display text-lg font-semibold">Members</h2>

      <ul className="mt-4 divide-y divide-line">
        {members.map((m) => {
          const isSelf = m.user_id === selfUserId;
          return (
            <li key={m.id} className="flex items-center gap-3 py-3">
              <Avatar name={m.user?.display_name ?? "?"} src={m.user?.avatar_url} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold text-ink">
                  {m.user?.display_name}
                  {isSelf && <span className="ml-1.5 text-xs font-semibold text-muted">(you)</span>}
                </span>
                <span className="block truncate text-xs text-muted">@{m.user?.username}</span>
              </span>
              {canManage && onChangeRole && !isSelf ? (
                <select
                  value={asAdminMember(m.role)}
                  onChange={(e) => onChangeRole(m.user_id, e.target.value)}
                  className="rounded-full border border-line bg-white px-3 py-1 text-xs font-bold"
                >
                  <option value="ADMIN">ADMIN</option>
                  <option value="MEMBER">MEMBER</option>
                </select>
              ) : (
                <span className="tag">{asAdminMember(m.role)}</span>
              )}
              {canManage && onRemove && !isSelf && (
                <button
                  onClick={() => onRemove(m.user_id)}
                  className="text-muted transition-colors hover:text-[var(--color-danger)]"
                  aria-label={`Remove ${m.user?.display_name}`}
                  title="Remove"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {canManage && (
        <div className="mt-4 border-t border-line pt-4">
          {/* mode toggle */}
          <div className="mb-3 flex gap-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setMode("member")}
              className={`flex items-center gap-1 rounded-full px-3 py-1 ${mode === "member" ? "bg-primary text-white" : "bg-surface-2 text-body"}`}
            >
              <Users className="h-3 w-3" /> Org member
            </button>
            <button
              type="button"
              onClick={() => setMode("email")}
              className={`flex items-center gap-1 rounded-full px-3 py-1 ${mode === "email" ? "bg-primary text-white" : "bg-surface-2 text-body"}`}
            >
              <Mail className="h-3 w-3" /> By email
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {mode === "member" ? (
              <select
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                className="field !w-auto flex-1 !py-2 text-sm"
              >
                <option value="">
                  {candidates.length ? "Add an org member…" : "Everyone's already here — use “By email”"}
                </option>
                {candidates.map((c) => (
                  <option key={c.user_id} value={c.user_id}>
                    {c.user?.display_name} (@{c.user?.username})
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder="teammate@company.com"
                type="email"
                className="field !w-auto flex-1 !py-2 text-sm"
              />
            )}
            <select value={role} onChange={(e) => setRole(e.target.value)} className="field !w-auto !py-2 text-sm">
              <option value="MEMBER">MEMBER</option>
              <option value="ADMIN">ADMIN</option>
            </select>
            <button
              onClick={submit}
              disabled={adding || (mode === "email" ? !email.includes("@") : !userId)}
              className="btn btn-primary btn-sm"
            >
              {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
              Add
            </button>
          </div>
          {mode === "email" && (
            <p className="mt-2 text-xs text-muted">
              New to SkillShare? We&apos;ll create their account and email a temporary password.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
