"use client";

import { api } from "@/lib/api";
import { useCurrentOrg } from "@/lib/hooks";
import { ResourceBrowser } from "@/components/ResourceBrowser";

export default function OrgResourcesPage() {
  const { org } = useCurrentOrg();

  if (!org) return null;

  return (
    <div>
      <div className="mb-6">
        <p className="kicker">{org.name}</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Org resources</h1>
        <p className="mt-1.5 max-w-2xl text-sm text-body">
          Defined once at the org level — every project and pod inherits these automatically.
        </p>
      </div>

      <ResourceBrowser
        queryKey={["org", org.slug, "resources"]}
        fetcher={(q) => api.orgResources(org.slug, q)}
        contextScope="ORG"
        addScope={{ scope_type: "ORG", scope_id: org.id }}
        emptyHint="Org-level resources cascade to every pod — start with your handbook or a shared MCP."
      />
    </div>
  );
}
