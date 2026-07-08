"use client";

/**
 * Copy the canonical share link for a resource: {origin}/r/{id}. Built from the
 * live origin so it matches wherever the site is served. On the public website
 * every resource here is public, so the link opens for anyone.
 */

import { useState } from "react";

export function ShareButton({ id, className = "" }: { id: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  const share = async () => {
    const url = `${typeof window !== "undefined" ? window.location.origin : ""}/r/${id}`;
    try {
      if (typeof navigator !== "undefined" && navigator.share) {
        await navigator.share({ url });
        return;
      }
    } catch {
      /* user dismissed the native sheet — fall through to copy */
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — no-op */
    }
  };

  return (
    <button onClick={share} className={`btn btn-secondary ${className}`} title="Copy a public link anyone can open">
      {copied ? (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M20 6 9 17l-5-5" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <path d="m8.6 13.5 6.8 4M15.4 6.5 8.6 10.5" />
        </svg>
      )}
      {copied ? "Link copied" : "Share"}
    </button>
  );
}
