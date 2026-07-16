"use client";

/**
 * Org settings → Features: per-org feature toggles. Premium flags show a
 * lime "Premium" badge and stay locked until a license is activated.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, KeyRound, Loader2, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk, useCurrentOrg, useFeatures } from "@/lib/hooks";
import { useToast } from "../Toast";

function Toggle({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${
        checked ? "bg-primary" : "bg-line"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-card shadow transition-[left] ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

export function FeaturesCard() {
  const { org } = useCurrentOrg();
  const { data: features } = useFeatures();
  const qc = useQueryClient();
  const { toast } = useToast();
  const [licenseKey, setLicenseKey] = useState("");

  const isAdmin = org?.my_role === "ADMIN";
  // Any paid tier (PRO / ENTERPRISE / legacy PREMIUM) unlocks premium features.
  const premiumOrg = !!org && org.plan !== "FREE";

  const invalidate = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: qk.features(org!.slug) }),
      qc.invalidateQueries({ queryKey: ["orgs"] }),
    ]);

  const toggleMut = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      api.setFeature(org!.slug, key, enabled),
    onSuccess: async (f) => {
      await invalidate();
      toast(`"${f.name}" ${f.enabled ? "enabled" : "disabled"} for ${org?.name}`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const licenseMut = useMutation({
    mutationFn: () => api.activateLicense(org!.slug, licenseKey),
    onSuccess: async () => {
      await invalidate();
      setLicenseKey("");
      toast(`Premium license activated for ${org?.name} 🎉`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold">Features</h2>
        <span
          className={`tag ${premiumOrg ? "!bg-lime !text-ink" : ""}`}
          title={premiumOrg ? "Premium features unlocked" : "Free plan"}
        >
          {premiumOrg ? <BadgeCheck className="h-3 w-3" /> : null}
          {org?.plan ?? "FREE"} plan
        </span>
      </div>
      <p className="mt-1 text-sm text-body">
        Turn features on or off for everyone in {org?.name}. Premium features need a license.
      </p>

      <ul className="mt-5 divide-y divide-line">
        {(features ?? []).map((f) => (
          <li key={f.key} className="flex items-start gap-4 py-4">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 text-sm font-bold text-ink">
                {f.name}
                {f.premium && (
                  <span className="tag !bg-lime !text-ink" title="Requires a premium license">
                    Premium
                  </span>
                )}
                {f.premium && !f.licensed && <Lock className="h-3.5 w-3.5 text-muted" />}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">{f.description}</p>
            </div>
            <Toggle
              checked={f.enabled}
              disabled={!isAdmin || (f.premium && !f.licensed) || toggleMut.isPending}
              onChange={(v) => toggleMut.mutate({ key: f.key, enabled: v })}
            />
          </li>
        ))}
      </ul>

      {!premiumOrg && (
        <div className="mt-2 rounded-2xl border border-dashed border-line bg-surface p-4">
          <p className="flex items-center gap-1.5 text-sm font-bold text-ink">
            <KeyRound className="h-3.5 w-3.5 text-primary" /> Activate a premium license
          </p>
          <p className="mt-1 text-xs text-muted">
            Unlocks the locked features above. Demo key format: <code className="code">T41-PREM-XXXX</code>
          </p>
          {isAdmin && (
            <div className="mt-3 flex gap-2">
              <input
                value={licenseKey}
                onChange={(e) => setLicenseKey(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && licenseKey.trim() && licenseMut.mutate()}
                placeholder="T41-PREM-…"
                className="field code flex-1 !py-2 text-sm uppercase"
              />
              <button
                onClick={() => licenseMut.mutate()}
                disabled={!licenseKey.trim() || licenseMut.isPending}
                className="btn btn-lime btn-sm"
              >
                {licenseMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Activate
              </button>
            </div>
          )}
        </div>
      )}

      {!isAdmin && <p className="mt-3 text-xs text-muted">Only org admins can change features.</p>}
    </div>
  );
}
