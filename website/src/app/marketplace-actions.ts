"use server";

import { getResourcesPage, type ResourcePage, type ResourceQuery } from "@/lib/data";

/**
 * Server action backing the marketplace "Load more" / filter flow. Runs on the
 * server so API_URL stays server-side (no CORS, no client API exposure); the
 * client component calls it from event handlers and awaits the page.
 */
export async function loadResourcesAction(opts: ResourceQuery): Promise<ResourcePage> {
  return getResourcesPage(opts);
}
