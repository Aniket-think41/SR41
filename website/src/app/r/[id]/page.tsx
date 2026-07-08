/**
 * Canonical share resolver — one link per resource, shared from either the
 * website or the dashboard: /r/{id}.
 *
 *   - PUBLIC (approved) resource  → render the public marketplace page (anyone).
 *   - private / pending / unknown → bounce to the dashboard's /dashboard/r/{id},
 *     which enforces auth + access (a leaked link never leaks private content —
 *     the public API only 200s for approved-public resources, so we never even
 *     confirm a private resource exists from here).
 */

import { redirect } from "next/navigation";
import { getResource } from "@/lib/data";
import { SITE } from "@/lib/site";

// The access decision depends on live resource state, so never statically cache.
export const dynamic = "force-dynamic";

export default async function ShareResolver({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await getResource(id); // GET /api/public/resources/{id} — 200 only if public+approved
  if (r) redirect(`/marketplace/${id}`);
  // Not publicly visible → let the authenticated dashboard decide access.
  redirect(`${SITE.dashboard.origin}/dashboard/r/${id}`);
}
