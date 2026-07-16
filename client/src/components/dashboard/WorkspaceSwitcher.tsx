"use client";

/**
 * Workspace switch — flips the dashboard between the Org space (projects, pods,
 * members, RBAC) and the Publisher space (marketplace + your own resources).
 *
 * The Org tab is gated on whether the user actually has somewhere to go (spec §2):
 *   1. No org + FREE plan  → the tab is LOCKED (🔒); clicking routes to upgrade.
 *   2. No org + paid plan  → clicking opens a "create your organization" popup;
 *                            creating it unlocks the tab and switches in.
 *   3. Already in an org    → toggles freely.
 * Selecting "Publisher" the first time registers the user as a publisher.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Loader2, Lock, Rocket, X } from "lucide-react";
import { api } from "@/lib/api";
import { isApiError } from "@/lib/api/http";
import { qk, useCanCreateOrg, useCurrentOrg, useSession } from "@/lib/hooks";
import { useUi, type Workspace } from "@/lib/store";
import { useToast } from "../Toast";

export function WorkspaceSwitcher({ collapsed }: { collapsed?: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { data: user } = useSession();
  const { workspace, setWorkspace } = useUi();
  const { orgs, setOrgSlug } = useCurrentOrg();
  const { canCreate, reason } = useCanCreateOrg();

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");

  const hasOrg = (orgs?.length ?? 0) > 0;
  // Definitively blocked from having an org (FREE / at cap) — show the lock.
  const orgLocked = !hasOrg && !canCreate && !!reason;

  // A publisher with no orgs belongs in the publisher space (org space is empty).
  useEffect(() => {
    if (orgs && orgs.length === 0 && user?.is_publisher && workspace !== "publisher") {
      setWorkspace("publisher");
      router.replace("/dashboard/publisher");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgs, user?.is_publisher]);

  const becomePublisher = useMutation({
    mutationFn: () => api.updateMe({ is_publisher: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.me }),
  });

  const goUpgrade = () => {
    setCreateOpen(false);
    setWorkspace("publisher");
    router.push("/dashboard/billing");
  };

  const createOrg = useMutation({
    mutationFn: () => api.createOrg({ name: name.trim() }),
    onSuccess: async (created) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: qk.orgs }),
        qc.invalidateQueries({ queryKey: qk.myEntitlements }),
      ]);
      setOrgSlug(created.slug);
      setCreateOpen(false);
      setName("");
      setWorkspace("org");
      router.replace("/dashboard");
      toast(`Organization "${created.name}" created`);
    },
    onError: (e) => {
      // Backend is the source of truth on plan limits — a FREE user who slipped
      // past the client gate gets routed to upgrade rather than dead-ending.
      if (isApiError(e) && e.error.code === "PAYMENT_REQUIRED") {
        toast(e.error.message, "error");
        goUpgrade();
        return;
      }
      toast(isApiError(e) ? e.error.message : "Could not create org", "error");
    },
  });

  const go = async (next: Workspace) => {
    if (next === workspace && next !== "org") return;
    if (next === "org") {
      if (hasOrg) {
        setWorkspace("org");
        router.replace("/dashboard");
        return;
      }
      // No org yet: FREE → upgrade, paid → create popup.
      if (orgLocked) {
        goUpgrade();
        return;
      }
      setCreateOpen(true);
      return;
    }
    // Publisher space (registers publisher on first switch).
    if (next === workspace) return;
    if (!user?.is_publisher) await becomePublisher.mutateAsync();
    setWorkspace("publisher");
    router.replace("/dashboard/publisher");
  };

  const orgIcon = orgLocked ? Lock : Building2;

  return (
    <>
      {collapsed ? (
        (() => {
          const other: Workspace = workspace === "org" ? "publisher" : "org";
          const Icon = workspace === "org" ? Rocket : orgIcon;
          return (
            <button
              onClick={() => go(other)}
              className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl border border-line bg-surface text-primary transition hover:bg-card"
              title={
                other === "org"
                  ? orgLocked
                    ? "Upgrade to create an organization"
                    : hasOrg ? "Switch to Org space" : "Create an organization"
                  : "Switch to Publisher space"
              }
              aria-label={`Switch to ${other} space`}
            >
              <Icon className="h-4 w-4" />
            </button>
          );
        })()
      ) : (
        <div className="flex rounded-xl border border-line bg-surface p-1" role="tablist" aria-label="Workspace">
          <button
            role="tab"
            aria-selected={workspace === "org"}
            onClick={() => go("org")}
            disabled={becomePublisher.isPending}
            title={orgLocked ? reason ?? "Upgrade to create an organization" : undefined}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold transition ${
              workspace === "org" ? "bg-card text-primary shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            {orgLocked ? <Lock className="h-3.5 w-3.5" /> : <Building2 className="h-3.5 w-3.5" />}
            Org
          </button>
          <button
            role="tab"
            aria-selected={workspace === "publisher"}
            onClick={() => go("publisher")}
            disabled={becomePublisher.isPending}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold transition ${
              workspace === "publisher" ? "bg-card text-primary shadow-sm" : "text-muted hover:text-ink"
            }`}
          >
            <Rocket className="h-3.5 w-3.5" />
            Publisher
          </button>
        </div>
      )}

      {/* Create-organization popup (paid users with no org yet) */}
      {createOpen && (
        <div
          className="overlay-fade fixed inset-0 z-[95] flex items-center justify-center bg-navy/35 p-4 backdrop-blur-[2px]"
          onClick={() => !createOrg.isPending && setCreateOpen(false)}
          role="dialog"
          aria-modal
        >
          <div className="card relative w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setCreateOpen(false)}
              className="absolute right-4 top-4 rounded-full p-1.5 text-muted transition hover:bg-surface hover:text-ink"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-50 text-primary">
                <Building2 className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-display text-lg font-semibold">Create your organization</h2>
                <p className="text-xs text-muted">Projects, pods, members &amp; shared resources live here.</p>
              </div>
            </div>
            <div className="mt-4">
              <label className="field-label" htmlFor="ws-org-name">Organization name</label>
              <input
                id="ws-org-name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && name.trim() && createOrg.mutate()}
                placeholder="Acme Inc."
                className="field"
              />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setCreateOpen(false)} className="btn btn-secondary btn-sm" disabled={createOrg.isPending}>
                Cancel
              </button>
              <button onClick={() => createOrg.mutate()} className="btn btn-primary btn-sm" disabled={createOrg.isPending || !name.trim()}>
                {createOrg.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Create &amp; switch
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
