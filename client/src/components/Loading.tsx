"use client";

/**
 * Shared loading primitives so no screen ever renders a blank content area while
 * data is in flight (which reads as "the app is stuck"):
 *  - <Spinner> — a small branded spinner for buttons/inline use.
 *  - <Skeleton> — a shimmering placeholder block.
 *  - <PageLoader> — a centered logo-pulse loader for whole-page fetches.
 *  - <CardGridSkeleton> — a grid of card skeletons for list screens.
 * A global top progress bar lives in <GlobalFetchingBar> (dashboard layout).
 */

import { Logo } from "./Logo";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent align-[-0.125em] ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function PageLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 text-center">
      <Logo className="h-11 w-11 animate-pulse" />
      <p className="flex items-center gap-2 text-sm font-semibold text-muted">
        <Spinner className="h-4 w-4 text-primary" /> {label}
      </p>
    </div>
  );
}

export function CardGridSkeleton({ count = 6, height = "h-40" }: { count?: number; height?: string }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className={height} />
      ))}
    </div>
  );
}
