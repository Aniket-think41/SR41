"use client";

/**
 * Full-page gate for org-disabled features. Renders children when the flag
 * is on; otherwise a friendly "disabled for this org" notice.
 */

import Link from "next/link";
import { Lock } from "lucide-react";
import { useCurrentOrg, useFeature, useFeatures } from "@/lib/hooks";

export function FeatureGate({
  feature,
  title,
  children,
}: {
  feature: string;
  title: string;
  children: React.ReactNode;
}) {
  const { org } = useCurrentOrg();
  const { isLoading } = useFeatures();
  const { enabled } = useFeature(feature);

  if (isLoading) return null;
  if (enabled) return <>{children}</>;

  return (
    <div className="mx-auto max-w-md py-20 text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2 text-primary">
        <Lock className="h-6 w-6" />
      </span>
      <h1 className="font-display mt-5 text-2xl font-semibold">{title} is turned off.</h1>
      <p className="mt-2 text-sm leading-relaxed text-body">
        An admin disabled this feature for <span className="font-bold text-ink">{org?.name}</span>.
        It can be re-enabled anytime from organization settings.
      </p>
      <div className="mt-6 flex justify-center gap-2">
        <Link href="/dashboard" className="btn btn-secondary btn-sm">Back to dashboard</Link>
        {org?.my_role === "ADMIN" && (
          <Link href="/dashboard/org/settings" className="btn btn-primary btn-sm">Open settings</Link>
        )}
      </div>
    </div>
  );
}
