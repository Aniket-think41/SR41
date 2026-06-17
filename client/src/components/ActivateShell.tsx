"use client";

/**
 * Device-login approval page (/activate). The CLI / MCP server sends the user
 * here with ?code=XXXX-XXXX. We confirm who's signing in, show which client is
 * asking, and let the user approve or reject it. Approving flips the device
 * session to "approved" so the waiting terminal receives its tokens.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, MonitorSmartphone, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { useSession } from "@/lib/hooks";
import { Logo } from "./Logo";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-white px-4 py-12">
      <div className="blob -left-32 top-0 h-[28rem] w-[28rem]" style={{ background: "var(--color-primary-50)" }} />
      <div className="blob -right-20 bottom-0 h-[24rem] w-[24rem]" style={{ background: "rgba(209,255,0,0.25)" }} />
      <div className="relative w-full max-w-md">
        <Link href="/dashboard" className="mb-8 flex items-center justify-center gap-2.5">
          <Logo className="h-9 w-9" />
          <span className="font-display text-2xl font-semibold tracking-tight">
            Skill<span className="text-primary">Share</span>
          </span>
        </Link>
        <div className="card p-8">{children}</div>
      </div>
    </main>
  );
}

function ActivateInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { data: user, isLoading: sessionLoading } = useSession();
  const codeParam = (search.get("code") ?? "").toUpperCase();
  const [code, setCode] = useState(codeParam);
  const [done, setDone] = useState<"approved" | "denied" | null>(null);

  // Not signed in → send to login and come back here with the code.
  useEffect(() => {
    if (!sessionLoading && user === null) {
      const back = `/activate${codeParam ? `?code=${codeParam}` : ""}`;
      router.replace(`/login?redirect=${encodeURIComponent(back)}`);
    }
  }, [sessionLoading, user, codeParam, router]);

  const info = useQuery({
    queryKey: ["device", codeParam],
    queryFn: () => api.deviceInfo(codeParam),
    enabled: !!user && !!codeParam,
    retry: false,
  });

  const approve = useMutation({
    mutationFn: () => api.deviceApprove(codeParam),
    onSuccess: () => setDone("approved"),
  });
  const deny = useMutation({
    mutationFn: () => api.deviceDeny(codeParam),
    onSuccess: () => setDone("denied"),
  });

  if (sessionLoading || !user) {
    return (
      <Shell>
        <div className="flex items-center justify-center gap-2 py-6 text-muted">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading…
        </div>
      </Shell>
    );
  }

  // No code yet → let the user type the one shown in their terminal.
  if (!codeParam) {
    return (
      <Shell>
        <h1 className="font-display text-2xl font-semibold">Connect a device</h1>
        <p className="mt-1.5 text-sm text-body">Enter the code shown in your terminal.</p>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="WXYZ-1A2B"
          className="field code mt-5 text-center text-lg tracking-widest"
        />
        <button
          className="btn btn-primary mt-4 w-full"
          disabled={code.length < 4}
          onClick={() => router.replace(`/activate?code=${encodeURIComponent(code.trim())}`)}
        >
          Continue
        </button>
      </Shell>
    );
  }

  if (done === "approved") {
    return (
      <Shell>
        <div className="text-center">
          <CheckCircle2 className="mx-auto h-12 w-12 text-primary" />
          <h1 className="font-display mt-3 text-2xl font-semibold">You&apos;re connected.</h1>
          <p className="mt-1.5 text-sm text-body">
            Return to your terminal — it&apos;s signed in as <span className="font-semibold">@{user.username}</span> now.
          </p>
          <Link href="/dashboard/marketplace" className="btn btn-primary mt-6 w-full">
            Explore the marketplace
          </Link>
          <Link href="/dashboard" className="btn btn-secondary mt-2 w-full">
            Go to dashboard
          </Link>
        </div>
      </Shell>
    );
  }

  if (done === "denied") {
    return (
      <Shell>
        <div className="text-center">
          <XCircle className="mx-auto h-12 w-12 text-note" />
          <h1 className="font-display mt-3 text-2xl font-semibold">Request rejected.</h1>
          <p className="mt-1.5 text-sm text-body">The device was not connected. You can close this page.</p>
        </div>
      </Shell>
    );
  }

  if (info.isLoading) {
    return (
      <Shell>
        <div className="flex items-center justify-center gap-2 py-6 text-muted">
          <Loader2 className="h-5 w-5 animate-spin" /> Checking the request…
        </div>
      </Shell>
    );
  }

  if (info.isError || !info.data) {
    return (
      <Shell>
        <div className="text-center">
          <XCircle className="mx-auto h-12 w-12 text-note" />
          <h1 className="font-display mt-3 text-2xl font-semibold">Code not found.</h1>
          <p className="mt-1.5 text-sm text-body">
            This code is invalid or has expired. Start a new login from your terminal.
          </p>
        </div>
      </Shell>
    );
  }

  const status = info.data.status;
  if (status === "expired" || status === "denied") {
    return (
      <Shell>
        <div className="text-center">
          <XCircle className="mx-auto h-12 w-12 text-note" />
          <h1 className="font-display mt-3 text-2xl font-semibold">
            {status === "expired" ? "This code expired." : "Already rejected."}
          </h1>
          <p className="mt-1.5 text-sm text-body">Start a new login from your terminal.</p>
        </div>
      </Shell>
    );
  }
  if (status === "approved") {
    return (
      <Shell>
        <div className="text-center">
          <CheckCircle2 className="mx-auto h-12 w-12 text-primary" />
          <h1 className="font-display mt-3 text-2xl font-semibold">Already connected.</h1>
          <p className="mt-1.5 text-sm text-body">This device has been approved. Return to your terminal.</p>
          <Link href="/dashboard/marketplace" className="btn btn-primary mt-6 w-full">Explore the marketplace</Link>
        </div>
      </Shell>
    );
  }

  // pending → ask for approval
  const busy = approve.isPending || deny.isPending;
  return (
    <Shell>
      <div className="mb-5 flex justify-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-50 text-primary">
          <MonitorSmartphone className="h-7 w-7" />
        </span>
      </div>
      <h1 className="font-display text-center text-2xl font-semibold">Authorize this device?</h1>
      <p className="mt-1.5 text-center text-sm text-body">
        <span className="font-semibold">{info.data.client_name}</span> wants to sign in as{" "}
        <span className="font-semibold">@{user.username}</span>.
      </p>
      <p className="mt-3 text-center font-mono text-lg tracking-widest text-ink">{codeParam}</p>

      {(approve.isError || deny.isError) && (
        <p className="field-error mt-3 text-center">{errorMessage(approve.error ?? deny.error)}</p>
      )}

      <button className="btn btn-primary mt-6 w-full" disabled={busy} onClick={() => approve.mutate()}>
        {approve.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
        Approve &amp; connect
      </button>
      <button className="btn btn-secondary mt-2 w-full" disabled={busy} onClick={() => deny.mutate()}>
        Reject
      </button>
      <p className="mt-4 text-center text-xs text-muted">
        Only approve if you just started a login from a terminal you trust.
      </p>
    </Shell>
  );
}

export function ActivateShell() {
  return (
    <Suspense>
      <ActivateInner />
    </Suspense>
  );
}
