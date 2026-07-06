"use client";

/**
 * A slim top progress bar shown whenever ANY React Query request is in flight
 * (including slow Cloud Run cold starts). It reassures the user the app is
 * working even on screens that already show partial data — the fix for "nothing
 * happened, is it stuck?". Purely presentational; driven by useIsFetching.
 */

import { useIsFetching, useIsMutating } from "@tanstack/react-query";

export function GlobalFetchingBar() {
  const busy = useIsFetching() + useIsMutating();
  if (!busy) return null;
  return (
    <div className="fetch-bar" role="progressbar" aria-label="Loading">
      <span />
    </div>
  );
}
