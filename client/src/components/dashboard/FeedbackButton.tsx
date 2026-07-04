"use client";

/**
 * Feedback CTA — a topbar button that opens a lightweight modal for sending
 * product feedback: a 1–5 star rating, a category, and a message. Posts to
 * /api/feedback (source="dashboard"). The same feedback surface is available in
 * the CLI (`skillshare feedback`) and the MCP (`submit_feedback`).
 */

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation } from "@tanstack/react-query";
import { MessageSquarePlus, Star, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { useToast } from "../Toast";
import type { FeedbackCategory } from "@/lib/types";

const CATEGORIES: { key: FeedbackCategory; label: string }[] = [
  { key: "idea", label: "Idea" },
  { key: "bug", label: "Bug" },
  { key: "praise", label: "Praise" },
  { key: "question", label: "Question" },
  { key: "other", label: "Other" },
];

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>("idea");
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [message, setMessage] = useState("");
  const { toast } = useToast();

  const submit = useMutation({
    mutationFn: () =>
      api.submitFeedback({
        message: message.trim(),
        rating: rating || null,
        category,
        context: { page: typeof window !== "undefined" ? window.location.pathname : undefined },
      }),
    onSuccess: () => {
      toast("Thanks for the feedback!");
      reset();
      setOpen(false);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  function reset() {
    setMessage("");
    setRating(0);
    setHover(0);
    setCategory("idea");
  }

  // close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="hidden items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 text-sm font-semibold text-muted transition hover:border-primary hover:text-primary sm:flex"
      >
        <MessageSquarePlus className="h-3.5 w-3.5" />
        Feedback
      </button>

      {open && typeof document !== "undefined" && createPortal(
        <div
          className="fixed inset-0 z-[80] flex items-start justify-center bg-ink/30 px-4 pt-[12vh] backdrop-blur-sm"
          onMouseDown={() => setOpen(false)}
        >
          <div
            className="pop w-[min(30rem,100%)] overflow-hidden rounded-3xl border border-line bg-white shadow-[0_32px_80px_-24px_rgba(10,8,64,0.45)]"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between border-b border-line px-6 py-5">
              <div>
                <h2 className="font-display text-lg font-bold text-ink">Send feedback</h2>
                <p className="mt-0.5 text-sm text-muted">Tell us what&rsquo;s working and what isn&rsquo;t.</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-muted transition hover:text-ink"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              {/* category */}
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.map((c) => (
                  <button
                    key={c.key}
                    onClick={() => setCategory(c.key)}
                    className={`rounded-full border px-3 py-1 text-xs font-bold transition ${
                      category === c.key
                        ? "border-primary bg-primary text-white"
                        : "border-line text-muted hover:border-primary hover:text-primary"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>

              {/* rating */}
              <div>
                <span className="mb-1.5 block text-xs font-bold uppercase tracking-wide text-muted">
                  How&rsquo;s your experience? <span className="font-medium normal-case">(optional)</span>
                </span>
                <div className="flex items-center gap-1" onMouseLeave={() => setHover(0)}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => setRating(n === rating ? 0 : n)}
                      onMouseEnter={() => setHover(n)}
                      aria-label={`${n} star${n > 1 ? "s" : ""}`}
                      className="p-0.5 transition"
                    >
                      <Star
                        className={`h-6 w-6 transition ${
                          (hover || rating) >= n
                            ? "fill-[var(--color-warning,#f5a623)] text-[var(--color-warning,#f5a623)]"
                            : "text-line"
                        }`}
                      />
                    </button>
                  ))}
                </div>
              </div>

              {/* message */}
              <div>
                <label htmlFor="fb-msg" className="mb-1.5 block text-xs font-bold uppercase tracking-wide text-muted">
                  Your feedback
                </label>
                <textarea
                  id="fb-msg"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={4}
                  autoFocus
                  placeholder="Share an idea, report a bug, or tell us what you love…"
                  className="w-full resize-none rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none transition placeholder:text-muted focus:border-primary focus:bg-white"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-line bg-surface px-6 py-4">
              <button
                onClick={() => setOpen(false)}
                className="rounded-full px-4 py-2 text-sm font-bold text-muted transition hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={() => submit.mutate()}
                disabled={!message.trim() || submit.isPending}
                className="rounded-full bg-primary px-5 py-2 text-sm font-bold text-white transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submit.isPending ? "Sending…" : "Send feedback"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
