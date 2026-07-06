"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronsUpDown, Plus, Check, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { isApiError } from "@/lib/api/http";
import { useCanCreateOrg, useCurrentOrg } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { useToast } from "../Toast";
import { Avatar } from "../Avatar";

export function OrgSwitcher({ collapsed }: { collapsed: boolean }) {
  const { org, orgs, setOrgSlug } = useCurrentOrg();
  const { canCreate, reason } = useCanCreateOrg();
  const { setWorkspace } = useUi();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const { toast } = useToast();

  // Route to the publisher space + upgrade page instead of dead-ending (spec §2).
  const goUpgrade = () => {
    setOpen(false);
    setCreating(false);
    setWorkspace("publisher");
    router.push("/dashboard/billing");
  };

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const create = async () => {
    if (!name.trim()) return;
    try {
      const created = await api.createOrg({ name: name.trim() });
      await qc.invalidateQueries({ queryKey: ["orgs"] });
      await qc.invalidateQueries({ queryKey: ["me", "entitlements"] });
      setOrgSlug(created.slug);
      setCreating(false);
      setName("");
      setOpen(false);
      toast(`Organization "${created.name}" created`);
    } catch (e) {
      // FREE users can't create orgs → don't dead-end; send them to upgrade (spec §2).
      if (isApiError(e) && e.error.code === "PAYMENT_REQUIRED") {
        toast(e.error.message, "error");
        goUpgrade();
        return;
      }
      toast(isApiError(e) ? e.error.message : "Could not create org", "error");
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`flex w-full items-center gap-2.5 rounded-2xl border border-line bg-white p-2 text-left transition hover:border-primary/50 ${collapsed ? "justify-center" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Avatar name={org?.name ?? "?"} src={org?.logo_url} size="sm" className="!rounded-xl" />
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold text-ink">{org?.name ?? "…"}</span>
              <span className="block text-[0.68rem] font-semibold uppercase tracking-wider text-muted">
                {org?.my_role ?? ""}
                {org && org.plan !== "FREE" && (
                  <span className="ml-1.5 rounded-full bg-lime px-1.5 py-px text-[0.58rem] font-bold normal-case tracking-normal text-ink">
                    {org.plan === "PREMIUM" ? "Premium" : org.plan}
                  </span>
                )}
              </span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted" />
          </>
        )}
      </button>

      {open && (
        <div className="pop absolute left-0 top-full z-50 mt-2 w-64 rounded-2xl border border-line bg-white p-2 shadow-[0_24px_48px_-16px_rgba(20,20,19,0.25)]">
          <p className="px-3 pb-1 pt-2 text-[0.65rem] font-bold uppercase tracking-wider text-muted">
            Your organizations
          </p>
          {orgs.map((o) => (
            <button
              key={o.id}
              onClick={() => {
                setOrgSlug(o.slug);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left hover:bg-surface"
            >
              <Avatar name={o.name} src={o.logo_url} size="xs" className="!rounded-lg" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink">{o.name}</span>
                <span className="block text-[0.65rem] uppercase tracking-wider text-muted">{o.my_role}</span>
              </span>
              {o.slug === org?.slug && <Check className="h-4 w-4 text-primary" />}
            </button>
          ))}

          <div className="mt-1 border-t border-line pt-1">
            {!canCreate ? (
              <button
                onClick={goUpgrade}
                title={reason ?? undefined}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm font-semibold text-muted hover:bg-surface hover:text-ink"
              >
                <Lock className="h-4 w-4 shrink-0" />
                <span className="min-w-0">
                  <span className="block">Upgrade to create an organization</span>
                  {reason && <span className="block text-[0.65rem] font-normal text-muted">{reason}</span>}
                </span>
              </button>
            ) : creating ? (
              <div className="p-2">
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && create()}
                  placeholder="Organization name"
                  className="field !py-2 text-sm"
                />
                <div className="mt-2 flex gap-2">
                  <button onClick={create} className="btn btn-primary btn-sm flex-1">Create</button>
                  <button onClick={() => setCreating(false)} className="btn btn-secondary btn-sm">Cancel</button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-semibold text-primary hover:bg-primary-50"
              >
                <Plus className="h-4 w-4" /> Create Organization
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
