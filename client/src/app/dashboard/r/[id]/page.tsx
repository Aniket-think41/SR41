"use client";

/**
 * Dashboard side of the canonical share link (/dashboard/r/{id}).
 *
 * Reached when someone opens a shared link to a resource that isn't publicly
 * visible (the website bounced them here). This route sits under the auth-gated
 * dashboard layout, so an unauthenticated visitor is sent to /login?redirect=…
 * first. Once authenticated we fetch the resource with the access-checked
 * endpoint and: open it if allowed, or show "no access" / "not found".
 * Access is NOT granted by holding the link — you must already be a member with
 * the right visibility.
 */

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Lock, Loader2, SearchX } from "lucide-react";
import { api } from "@/lib/api";
import { isApiError } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import { useUi } from "@/lib/store";

export default function SharedResourceResolver() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { openDetail } = useUi();

  const { data, error, isLoading } = useQuery({
    queryKey: qk.resource(id),
    queryFn: () => api.resource(id),
    retry: false,
    enabled: !!id,
  });

  useEffect(() => {
    if (!data) return;
    if (data.is_public) {
      // Public/approved → the dedicated in-app marketplace view.
      router.replace(`/dashboard/marketplace/${id}`);
    } else {
      // Private but permitted → open the detail drawer over the workspace.
      openDetail(data);
      router.replace("/dashboard");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const code = isApiError(error) ? error.error.code : null;

  if (code === "FORBIDDEN") {
    return (
      <Message
        icon={<Lock className="h-6 w-6" />}
        title="You don't have access to this resource"
        body="It's private to an organization, project, or pod you're not a member of. Ask an owner or admin to add you, then open the link again."
      />
    );
  }
  if (code === "NOT_FOUND") {
    return (
      <Message
        icon={<SearchX className="h-6 w-6" />}
        title="Resource not found"
        body="This resource doesn't exist or has been deleted."
      />
    );
  }
  if (error) {
    return (
      <Message
        icon={<SearchX className="h-6 w-6" />}
        title="Couldn't open this resource"
        body={isApiError(error) ? error.error.message : "Something went wrong. Try again."}
      />
    );
  }

  // Loading, or briefly before the redirect fires.
  void isLoading;
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-muted">
      <Loader2 className="h-6 w-6 animate-spin" />
      <p className="text-sm font-semibold">Opening resource…</p>
    </div>
  );
}

function Message({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  const router = useRouter();
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-surface text-muted">{icon}</span>
      <div>
        <h1 className="font-display text-xl font-semibold text-ink">{title}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-body">{body}</p>
      </div>
      <button onClick={() => router.replace("/dashboard")} className="btn btn-secondary btn-sm">
        Back to dashboard
      </button>
    </div>
  );
}
