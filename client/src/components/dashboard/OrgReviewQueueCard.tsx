"use client";

/**
 * Org settings → Review queue (spec §3). Org admins approve or reject org-owned
 * resources that members have submitted for public listing.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Check, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg } from "@/lib/hooks";
import type { Resource } from "@/lib/types";
import { useUi } from "@/lib/store";
import { TypeBadge } from "@/components/badges";
import { useToast } from "@/components/Toast";

export function OrgReviewQueueCard() {
  const { org } = useCurrentOrg();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { openDetail } = useUi();
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const isAdmin = org?.my_role === "ADMIN";

  const { data: queue, isLoading } = useQuery({
    queryKey: qk.orgReviewQueue(org?.slug ?? "", "pending"),
    queryFn: () => api.orgReviewQueue(org!.slug, "pending"),
    enabled: !!org && isAdmin,
  });

  const reviewMut = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: "approve" | "reject"; note?: string }) =>
      api.reviewResource(id, { decision, note }),
    onSuccess: async (_r, vars) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["org", org!.slug, "review-queue"] }),
        qc.invalidateQueries({ queryKey: ["resource"] }),
        qc.invalidateQueries({ queryKey: ["public"] }),
      ]);
      setRejecting(null);
      setNote("");
      toast(vars.decision === "approve" ? "Resource approved — now live" : "Resource rejected");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (!isAdmin) return null;

  const items: Resource[] = queue ?? [];

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-display flex items-center gap-2 text-lg font-semibold">
          <ClipboardCheck className="h-5 w-5 text-primary" /> Review queue
        </h2>
        {items.length > 0 && <span className="tag">{items.length} pending</span>}
      </div>
      <p className="mt-1 text-sm text-body">
        Org resources members submitted for the public marketplace. Approve to list, or reject with a note.
      </p>

      {isLoading ? (
        <p className="mt-4 text-sm text-muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-dashed border-line bg-surface p-4 text-sm text-muted">
          Nothing awaiting review. 🎉
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {items.map((r) => (
            <li key={r.id} className="rounded-2xl border border-line p-4">
              <div className="flex flex-wrap items-center gap-3">
                <TypeBadge type={r.type} withLabel={false} />
                <button onClick={() => openDetail(r)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-sm font-bold text-ink">{r.title}</span>
                  <span className="block truncate text-xs text-muted">by {r.author?.display_name ?? "—"}</span>
                </button>
                {rejecting !== r.id && (
                  <div className="flex shrink-0 gap-2">
                    <button
                      onClick={() => reviewMut.mutate({ id: r.id, decision: "approve" })}
                      disabled={reviewMut.isPending}
                      className="btn btn-lime btn-sm"
                    >
                      <Check className="h-3.5 w-3.5" /> Approve
                    </button>
                    <button
                      onClick={() => { setRejecting(r.id); setNote(""); }}
                      className="btn btn-secondary btn-sm"
                    >
                      <X className="h-3.5 w-3.5" /> Reject
                    </button>
                  </div>
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
