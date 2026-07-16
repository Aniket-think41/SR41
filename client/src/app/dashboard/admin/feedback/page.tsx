"use client";

/**
 * Platform-admin feedback triage + public moderation (spec §4). Lists all
 * product feedback; admins can approve/reject each item for public display on
 * the marketing site (public_status) and flip its triage status. Gated on
 * User.is_admin.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, Star, ShieldCheck, Check, X, Eye } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useSession } from "@/lib/hooks";
import type { Feedback } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { useToast } from "@/components/Toast";
import { timeAgo } from "@/lib/utils";

const PUBLIC_BADGE: Record<string, string> = {
  approved: "!bg-lime !text-ink",
  rejected: "!bg-red-100 !text-red-700",
  pending: "",
};

export default function AdminFeedbackPage() {
  const { data: me } = useSession();
  const qc = useQueryClient();
  const { toast } = useToast();

  const { data: items, isLoading } = useQuery({
    queryKey: qk.adminFeedback(),
    queryFn: () => api.adminFeedback(),
    enabled: !!me?.is_admin,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["admin", "feedback"] });

  const moderateMut = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      api.moderateFeedback(id, decision),
    onSuccess: async (_r, vars) => {
      await invalidate();
      toast(vars.decision === "approve" ? "Approved for public display" : "Rejected for public display");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "open" | "reviewed" }) =>
      api.setFeedbackStatus(id, status),
    onSuccess: invalidate,
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (me && !me.is_admin) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center">
        <ShieldCheck className="mx-auto h-10 w-10 text-muted" />
        <h1 className="font-display mt-3 text-2xl font-semibold">Admins only</h1>
        <p className="mt-1 text-sm text-body">This page requires platform-admin access.</p>
      </div>
    );
  }

  const list: Feedback[] = items ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <p className="kicker flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" /> Platform admin
        </p>
        <h1 className="font-display mt-1 flex items-center gap-2 text-3xl font-semibold">
          <MessagesSquare className="h-7 w-7 text-primary" /> Feedback
        </h1>
        <p className="mt-1.5 text-sm text-body">
          Triage product feedback and choose which items appear publicly on the marketing site.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-card/60 p-14 text-center">
          <p className="font-display text-xl font-semibold">No feedback yet.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {list.map((f) => {
            const pub = f.public_status ?? "pending";
            return (
              <li key={f.id} className="card p-5">
                <div className="flex flex-wrap items-start gap-3">
                  <Avatar name={f.user?.display_name ?? "?"} src={f.user?.avatar_url} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold text-ink">{f.user?.display_name ?? "Someone"}</span>
                      <span className="tag capitalize">{f.category}</span>
                      {f.rating ? (
                        <span className="flex items-center gap-0.5 text-xs text-muted">
                          <Star className="h-3 w-3 fill-current text-[var(--color-warning,#f5a623)]" /> {f.rating}
                        </span>
                      ) : null}
                      <span className="text-xs text-muted">· {f.source} · {timeAgo(f.created_at)}</span>
                      <span className={`tag ${PUBLIC_BADGE[pub]}`} title="Public display status">
                        <Eye className="h-3 w-3" /> {pub}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm text-body">{f.message}</p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
                  <button
                    onClick={() => moderateMut.mutate({ id: f.id, decision: "approve" })}
                    disabled={moderateMut.isPending || pub === "approved"}
                    className="btn btn-lime btn-sm"
                  >
                    <Check className="h-3.5 w-3.5" /> Approve for public
                  </button>
                  <button
                    onClick={() => moderateMut.mutate({ id: f.id, decision: "reject" })}
                    disabled={moderateMut.isPending || pub === "rejected"}
                    className="btn btn-secondary btn-sm"
                  >
                    <X className="h-3.5 w-3.5" /> Reject
                  </button>
                  <button
                    onClick={() => statusMut.mutate({ id: f.id, status: f.status === "open" ? "reviewed" : "open" })}
                    disabled={statusMut.isPending}
                    className="btn btn-secondary btn-sm ml-auto"
                  >
                    {f.status === "open" ? "Mark reviewed" : "Reopen"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
