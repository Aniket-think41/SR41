"use client";

/**
 * Org settings — name, logo, description (frontend spec route map).
 * Member management lives on /dashboard/members.
 */

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Users, ArrowRight, RefreshCcw, Camera } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage, USING_MOCK } from "@/lib/api/http";
import { useCurrentOrg } from "@/lib/hooks";
import { Avatar } from "@/components/Avatar";
import { FeaturesCard } from "@/components/dashboard/FeaturesCard";
import { PlanUsageCard } from "@/components/dashboard/PlanUsageCard";
import { OrgReviewQueueCard } from "@/components/dashboard/OrgReviewQueueCard";
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
  const logoInput = useRef<HTMLInputElement>(null);

  const refreshOrg = async () => {
    await qc.invalidateQueries({ queryKey: ["orgs"] });
    await qc.invalidateQueries({ queryKey: ["org", org!.slug] });
  };

  const saveMut = useMutation({
    mutationFn: () => api.updateOrg(org!.slug, { name: name.trim(), description: description.trim() }),
    onSuccess: async () => {
      await refreshOrg();
      toast("Organization updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const logoMut = useMutation({
    mutationFn: (file: File) => api.uploadOrgLogo(org!.slug, file),
    onSuccess: async () => {
      await refreshOrg();
      toast("Logo updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const onPickLogo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) logoMut.mutate(f);
    e.target.value = "";
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <p className="kicker">Settings</p>
        <h1 className="font-display mt-1 text-3xl font-semibold">Organization</h1>
      </div>

      <div className="card p-6">
        <div className="flex items-center gap-4">
          <div className="relative w-fit">
            <Avatar name={org?.name ?? "?"} src={org?.logo_url} size="lg" className="!rounded-2xl" />
            {isAdmin && (
              <>
                <button
                  onClick={() => logoInput.current?.click()}
                  disabled={logoMut.isPending}
                  title="Upload a logo"
                  className="absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-ink text-white shadow ring-2 ring-white transition hover:bg-primary disabled:opacity-60"
                >
                  {logoMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Camera className="h-3.5 w-3.5" />}
                </button>
                <input ref={logoInput} type="file" accept="image/*" className="hidden" onChange={onPickLogo} />
              </>
            )}
          </div>
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

      <PlanUsageCard />

      <OrgReviewQueueCard />

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
