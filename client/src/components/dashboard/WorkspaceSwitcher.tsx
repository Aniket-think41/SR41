"use client";

/**
 * Workspace switch — flips the dashboard between the Org space (projects, pods,
 * members, RBAC) and the Publisher space (marketplace + your own resources, no
 * org/RBAC surfaces). Selecting "Publisher" for the first time registers the
 * user as a publisher (POST /api/auth/me { is_publisher: true }) — that's the
 * "register as a publisher" step. Once switched, we route to the right home.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Rocket } from "lucide-react";
import { api } from "@/lib/api";
import { qk, useSession } from "@/lib/hooks";
import { useUi, type Workspace } from "@/lib/store";

export function WorkspaceSwitcher({ collapsed }: { collapsed?: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: user } = useSession();
  const { workspace, setWorkspace } = useUi();

  // How many orgs the user belongs to — a publisher with no orgs should land in
  // the publisher space automatically (the org space would be empty for them).
  const { data: orgs } = useQuery({ queryKey: qk.orgs, queryFn: api.myOrgs });

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

  const go = async (next: Workspace) => {
    if (next === workspace) return;
    if (next === "publisher" && !user?.is_publisher) {
      await becomePublisher.mutateAsync();
    }
    setWorkspace(next);
    router.replace(next === "publisher" ? "/dashboard/publisher" : "/dashboard");
  };

  const tabs: { key: Workspace; label: string; icon: typeof Building2 }[] = [
    { key: "org", label: "Org", icon: Building2 },
    { key: "publisher", label: "Publisher", icon: Rocket },
  ];

  if (collapsed) {
    // Compact: a single icon that toggles to the other space.
    const other: Workspace = workspace === "org" ? "publisher" : "org";
    const Icon = workspace === "org" ? Building2 : Rocket;
    return (
      <button
        onClick={() => go(other)}
        className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl border border-line bg-surface text-primary transition hover:bg-white"
        title={`Switch to ${other === "org" ? "Org" : "Publisher"} space`}
        aria-label={`Switch to ${other} space`}
      >
        <Icon className="h-4 w-4" />
      </button>
    );
  }

  return (
    <div className="flex rounded-xl border border-line bg-surface p-1" role="tablist" aria-label="Workspace">
      {tabs.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          role="tab"
          aria-selected={workspace === key}
          onClick={() => go(key)}
          disabled={becomePublisher.isPending}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-bold transition ${
            workspace === key ? "bg-white text-primary shadow-sm" : "text-muted hover:text-ink"
          }`}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
