"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { getToken } from "@/lib/api/http";
import { Logo } from "@/components/Logo";

type Status = "checking" | "signing-in" | "accepted" | "expired" | "not-found" | "error";

export default function JoinPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;
  const token = params.token as string;
  const [status, setStatus] = useState<Status>("checking");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!slug || !token) {
      setStatus("error");
      setMessage("Invalid invitation link.");
      return;
    }

    const tokenStr = getToken();
    if (!tokenStr) {
      // Not logged in — redirect to login, come back here after auth
      router.replace(`/login?redirect=${encodeURIComponent(`/join/${slug}/${token}`)}`);
      return;
    }

    setStatus("signing-in");
    api
      .join(slug, token)
      .then(() => {
        setStatus("accepted");
        setTimeout(() => router.replace("/dashboard"), 2000);
      })
      .catch((e) => {
        const msg =
          typeof e === "object" && e !== null && "error" in e
            ? (e as { error: { message: string } }).error.message
            : "Something went wrong";
        if (msg.toLowerCase().includes("not found")) {
          setStatus("not-found");
        } else if (msg.toLowerCase().includes("expired")) {
          setStatus("expired");
        } else {
          setStatus("error");
        }
        setMessage(msg);
      });
  }, [slug, token, router]);

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-white px-4">
      <div className="w-full max-w-md text-center">
        <Logo className="mx-auto h-12 w-12" />
        <h1 className="mt-4 font-display text-2xl font-semibold">Accepting invitation</h1>

        {(status === "checking" || status === "signing-in") && (
          <div className="mt-6 flex items-center justify-center gap-2 text-sm text-body">
            <Loader2 className="h-4 w-4 animate-spin" />
            {status === "checking" ? "Checking your session…" : "Joining organization…"}
          </div>
        )}

        {status === "accepted" && (
          <div className="mt-6">
            <p className="text-sm text-green-600">You&#39;ve joined the organization!</p>
            <p className="mt-1 text-xs text-body">Redirecting to your dashboard…</p>
          </div>
        )}

        {status === "not-found" && (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-body">{message || "This invitation was not found or has already been used."}</p>
            <a href="/dashboard" className="btn btn-primary btn-sm">Go to dashboard</a>
          </div>
        )}

        {status === "expired" && (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-body">{message || "This invitation has expired. Ask your org admin to send a new one."}</p>
            <a href="/dashboard" className="btn btn-primary btn-sm">Go to dashboard</a>
          </div>
        )}

        {status === "error" && (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-red-600">{message || "Something went wrong."}</p>
            <a href="/dashboard" className="btn btn-primary btn-sm">Go to dashboard</a>
          </div>
        )}
      </div>
    </main>
  );
}
