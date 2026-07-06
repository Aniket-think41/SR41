"use client";

import { useState, useTransition } from "react";
import { submitFeedbackAction } from "@/app/feedback/actions";

const CATEGORIES = [
  { key: "praise", label: "Praise" },
  { key: "feature", label: "Feature request" },
  { key: "bug", label: "Bug" },
  { key: "other", label: "Other" },
];

export function FeedbackForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [category, setCategory] = useState("praise");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!message.trim()) {
      setError("Please share a short message.");
      return;
    }
    startTransition(async () => {
      const res = await submitFeedbackAction({
        message,
        rating: rating || null,
        category,
        name,
        email,
      });
      if (res.ok) {
        setDone(true);
      } else {
        setError("Something went wrong. Please try again.");
      }
    });
  }

  if (done) {
    return (
      <div className="card flex flex-col items-center p-10 text-center">
        <span aria-hidden className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-50 text-2xl text-primary">✓</span>
        <h3 className="font-display mt-5 text-2xl font-semibold">Thanks for the feedback!</h3>
        <p className="mt-2 max-w-sm text-body">
          Your note is pending review. Approved testimonials appear on this page.
        </p>
        <button
          type="button"
          onClick={() => {
            setDone(false);
            setName("");
            setEmail("");
            setMessage("");
            setRating(0);
            setCategory("praise");
          }}
          className="btn btn-secondary mt-6"
        >
          Send another
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="card flex flex-col gap-5 p-7 md:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Name <span className="text-muted">(optional)</span></span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ada Rao"
            className="rounded-xl border border-line bg-white px-4 py-2.5 text-sm outline-none focus:border-primary"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Email <span className="text-muted">(optional)</span></span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="rounded-xl border border-line bg-white px-4 py-2.5 text-sm outline-none focus:border-primary"
          />
        </label>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Rating</span>
          <div className="flex items-center gap-1" role="radiogroup" aria-label="Rating">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRating(n === rating ? 0 : n)}
                onMouseEnter={() => setHover(n)}
                onMouseLeave={() => setHover(0)}
                aria-label={`${n} star${n === 1 ? "" : "s"}`}
                aria-pressed={rating >= n}
                className={`text-2xl leading-none transition ${
                  (hover || rating) >= n ? "text-primary" : "text-line"
                }`}
              >
                ★
              </button>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink">Category</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-medium text-ink outline-none focus:border-primary"
          >
            {CATEGORIES.map((c) => (
              <option key={c.key} value={c.key}>{c.label}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium text-ink">Message</span>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          required
          placeholder="What's working well? What could be better?"
          className="rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-primary"
        />
      </label>

      {error && <p className="text-sm font-medium text-note">{error}</p>}

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted">Approved notes appear publicly. No account required.</p>
        <button type="submit" disabled={isPending} className="btn btn-primary disabled:opacity-60">
          {isPending ? "Sending…" : "Send feedback →"}
        </button>
      </div>
    </form>
  );
}
