"use client";

/**
 * Platform-admin review queue (spec §3). Lists resources submitted for public
 * listing across the whole platform; the admin approves or rejects with a note.
 * Gated on User.is_admin.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Check, X, Loader2 } from "lucide-react";
import { api, type ApprovalFilter } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import type { Resource } from "@/lib/types";
import { TypeBadge } from "@/components/badges";
import { useToast } from "@/components/Toast";

const TABS: ApprovalFilter[] = ["pending", "approved", "rejected"];

export default function AdminReviewPage() {
  const { data: me } = useSession();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { openDetail } = useUi();
  const [status, setStatus] = useState<ApprovalFilter>("pending");
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const { data: queue, isLoading } = useQuery({
    queryKey: qk.adminReviewQueue(status),
    queryFn: () => api.adminReviewQueue(status),
    enabled: !!me?.is_admin,
  });

  const reviewMut = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: "approve" | "reject"; note?: string }) =>
      api.reviewResource(id, { decision, note }),
    onSuccess: async (_r, vars) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["admin", "review"] }),
        qc.invalidateQueries({ queryKey: ["resource"] }),
        qc.invalidateQueries({ queryKey: ["public"] }),
      ]);
      setRejecting(null);
      setNote("");
      toast(vars.decision === "approve" ? "Approved — now live" : "Rejected");
    },
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

  const items: Resource[] = queue ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <p className="kicker flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" /> Platform admin
        </p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Review queue</h1>
        <p className="mt-1.5 text-sm text-body">
          Resources submitted for the public marketplace. Approve to list them, or reject with a note.
        </p>
      </div>

      <div className="flex gap-1 rounded-xl border border-line bg-surface p-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setStatus(t)}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-bold capitalize transition ${
              status === t ? "bg-white text-primary shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-white/60 p-14 text-center">
          <p className="font-display text-xl font-semibold">Nothing {status}.</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <li key={r.id} className="card p-5">
              <div className="flex flex-wrap items-center gap-3">
                <TypeBadge type={r.type} withLabel={false} />
                <button onClick={() => openDetail(r)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-base font-bold text-ink">{r.title}</span>
                  <span className="block truncate text-xs text-muted">
                    by {r.author?.display_name ?? "—"} · {r.scope_type}
                    {r.review_note ? ` · note: ${r.review_note}` : ""}
                  </span>
                </button>
                {status === "pending" && rejecting !== r.id && (
                  <div className="flex shrink-0 gap-2">
                    <button
                      onClick={() => reviewMut.mutate({ id: r.id, decision: "approve" })}
                      disabled={reviewMut.isPending}
                      className="btn btn-lime btn-sm"
                    >
                      <Check className="h-3.5 w-3.5" /> Approve
                    </button>
                    <button onClick={() => { setRejecting(r.id); setNote(""); }} className="btn btn-secondary btn-sm">
                      <X className="h-3.5 w-3.5" /> Reject
                    </button>
                  </div>
                )}
                {status === "rejected" && (
                  <button
                    onClick={() => reviewMut.mutate({ id: r.id, decision: "approve" })}
                    disabled={reviewMut.isPending}
                    className="btn btn-lime btn-sm shrink-0"
                  >
                    <Check className="h-3.5 w-3.5" /> Approve now
                  </button>
                )}
              </div>
              {rejecting === r.id && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <input
                    autoFocus
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Reason (optional)"
                    className="field flex-1 !py-2 text-sm"
                  />
                  <button
                    onClick={() => reviewMut.mutate({ id: r.id, decision: "reject", note: note.trim() || undefined })}
                    disabled={reviewMut.isPending}
                    className="btn btn-danger btn-sm"
                  >
                    {reviewMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Confirm reject
                  </button>
                  <button onClick={() => setRejecting(null)} className="btn btn-secondary btn-sm">Cancel</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
