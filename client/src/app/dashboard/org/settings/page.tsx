"use client";

/**
 * Org settings — name, logo, description (frontend spec route map).
 * Member management lives on /dashboard/members.
 */

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Users, ArrowRight, RefreshCcw } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage, USING_MOCK } from "@/lib/api/http";
import { useCurrentOrg } from "@/lib/hooks";
import { Avatar } from "@/components/Avatar";
import { FeaturesCard } from "@/components/dashboard/FeaturesCard";
import { TerminologyCard } from "@/components/dashboard/TerminologyCard";
import { useToast } from "@/components/Toast";

export default function OrgSettingsPage() {
  const { org } = useCurrentOrg();
  const qc = useQueryClient();
  const { toast } = useToast();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // hydrate the form when the (possibly switched) org loads — render-time adjust
  const [loadedOrg, setLoadedOrg] = useState<string | null>(null);
  if (org && org.id !== loadedOrg) {
    setLoadedOrg(org.id);
    setName(org.name);
    setDescription(org.description);
  }

  const isAdmin = org?.my_role === "ADMIN";

  const saveMut = useMutation({
    mutationFn: () => api.updateOrg(org!.slug, { name: name.trim(), description: description.trim() }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["orgs"] });
      await qc.invalidateQueries({ queryKey: ["org", org!.slug] });
      toast("Organization updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <p className="kicker">Settings</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Organization</h1>
      </div>

      <div className="card p-6">
        <div className="flex items-center gap-4">
          <Avatar name={org?.name ?? "?"} size="lg" className="!rounded-2xl" />
          <div>
            <h2 className="font-display text-lg font-semibold">{org?.name}</h2>
            <p className="code text-xs text-muted">skillshare.think41.com/{org?.slug}</p>
          </div>
        </div>

        <div className="mt-6 space-y-4">
          <div>
            <label className="field-label" htmlFor="org-name">Name</label>
            <input id="org-name" value={name} onChange={(e) => setName(e.target.value)} className="field" disabled={!isAdmin} />
          </div>
          <div>
            <label className="field-label" htmlFor="org-desc">Description</label>
            <textarea id="org-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="field resize-y" rows={3} disabled={!isAdmin} />
          </div>
          {isAdmin ? (
            <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !name.trim()} className="btn btn-primary btn-sm">
              {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save changes
            </button>
          ) : (
            <p className="text-xs text-muted">Only org admins can edit these settings.</p>
          )}
        </div>
      </div>

      <FeaturesCard />

      <TerminologyCard />

      <Link href="/dashboard/members" className="card card-hover flex items-center gap-4 p-6">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary">
          <Users className="h-5 w-5" />
        </span>
        <span className="flex-1">
          <span className="font-display block text-lg font-semibold">Members & invitations</span>
          <span className="text-sm text-body">Roles, invites, and removals.</span>
        </span>
        <ArrowRight className="h-4 w-4 text-muted" />
      </Link>

      {USING_MOCK && (
        <div className="card border-dashed p-6">
          <h2 className="font-display text-lg font-semibold">Demo data</h2>
          <p className="mt-1 text-sm text-body">
            This workspace runs on local mock data (the backend attaches via{" "}
            <code className="code text-xs">NEXT_PUBLIC_API_URL</code>). Reset to the original seed anytime.
          </p>
          <button
            onClick={async () => {
              const { resetDb } = await import("@/lib/mock/db");
              resetDb();
              qc.clear();
              window.location.href = "/login";
            }}
            className="btn btn-secondary btn-sm mt-4"
          >
            <RefreshCcw className="h-3.5 w-3.5" /> Reset demo data
          </button>
        </div>
      )}
    </div>
  );
}
