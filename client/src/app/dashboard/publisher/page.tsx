"use client";

/**
 * Publisher home — the whole publisher workspace on one screen: the resources
 * you've authored (skills, MCP servers, notes) with live search + type filters,
 * and a "New" action that creates straight onto the public marketplace (PUBLIC
 * scope). No org, projects, pods, or members here — just your marketplace shelf.
 */

import { useEffect } from "react";
import Link from "next/link";
import { Rocket, Store, Globe2 } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useSession } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { ResourceBrowser } from "@/components/ResourceBrowser";

export default function PublisherHome() {
  const { data: me } = useSession();
  const { setWorkspace } = useUi();
  const username = me?.username ?? "";

  // Landing here means we're in the publisher space — keep the sidebar in sync.
  useEffect(() => {
    setWorkspace("publisher");
  }, [setWorkspace]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker flex items-center gap-1.5">
            <Rocket className="h-3.5 w-3.5" /> Publisher space
          </p>
          <h1 className="font-display mt-1 text-3xl font-semibold">My resources</h1>
          <p className="mt-1.5 max-w-2xl text-sm text-body">
            Everything you&apos;ve authored as <span className="font-bold text-ink">@{username}</span>. New resources
            start as private drafts you own — hit <span className="font-semibold text-ink">Publish</span> to put one on
            the public <Globe2 className="mb-0.5 inline h-3.5 w-3.5" /> marketplace.
          </p>
        </div>
        <Link href="/dashboard/marketplace" className="btn btn-secondary btn-sm">
          <Store className="h-3.5 w-3.5" /> Browse marketplace
        </Link>
      </div>

      {username && (
        <ResourceBrowser
          queryKey={[...qk.profile(username), "resources"]}
          fetcher={(q) => api.userResources(username, q)}
          contextScope="PUBLIC"
          addScope={{ scope_type: "PUBLIC", scope_id: null }}
          emptyHint="Add your first skill, MCP server, or note — it starts as a private draft you own; publish it to the marketplace when it's ready."
        />
      )}
    </div>
  );
}
