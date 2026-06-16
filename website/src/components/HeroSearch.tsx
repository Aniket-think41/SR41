"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const SUGGESTIONS = ["code review", "retrieval", "postgres", "design system"];

/**
 * Marketplace hero search. Pushes `?q=` so the MarketplaceBrowser below
 * (which reads the URL) filters live, then scrolls to the results.
 */
export function HeroSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");

  const run = (value: string) => {
    const v = value.trim();
    router.push(v ? `/?q=${encodeURIComponent(v)}#browse` : "/#browse", { scroll: false });
    if (typeof document !== "undefined") {
      document.getElementById("browse")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="mx-auto w-full max-w-xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(q);
        }}
        className="flex items-center gap-2 rounded-full border border-line bg-white p-1.5 pl-5 shadow-[0_12px_40px_-16px_rgba(115,90,229,0.45)]"
      >
        <span aria-hidden className="text-lg text-muted">⌕</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search skills, MCP servers, notes…"
          aria-label="Search the marketplace"
          className="flex-1 bg-transparent text-base outline-none placeholder:text-muted"
        />
        <button type="submit" className="btn btn-primary px-6 py-2.5 text-sm">
          Search
        </button>
      </form>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-sm text-muted">
        <span>Try:</span>
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => {
              setQ(s);
              run(s);
            }}
            className="rounded-full border border-line bg-white px-3 py-1 font-medium text-body transition hover:border-primary hover:text-primary"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
