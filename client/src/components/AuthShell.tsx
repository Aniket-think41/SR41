"use client";

/**
 * Shared layout + form logic for /login and /signup.
 * The form posts to POST /api/auth/login|signup. Without NEXT_PUBLIC_API_URL
 * the transport seam uses the in-browser mock (any password); with it set,
 * this is the real JWT flow. The demo button logs in as the seeded demo user
 * and works against both.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage, setToken } from "@/lib/api/http";
import { Logo } from "./Logo";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

type GoogleId = {
  accounts: {
    id: {
      initialize: (cfg: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
      prompt: () => void;
    };
  };
};
const googleApi = (): GoogleId | undefined => (window as unknown as { google?: GoogleId }).google;

// Lazily load Google Identity Services once; resolves when window.google is ready.
let gisPromise: Promise<void> | null = null;
function loadGoogleScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if ((window as unknown as { google?: unknown }).google) return Promise.resolve();
  if (gisPromise) return gisPromise;
  gisPromise = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Google sign-in"));
    document.head.appendChild(s);
  });
  return gisPromise;
}

const loginSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
  display_name: z.string().optional(),
});

const signupSchema = loginSchema.extend({
  password: z.string().min(8, "At least 8 characters"),
  display_name: z.string().min(1, "Your name is required"),
});

type FormValues = z.infer<typeof loginSchema>;

function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const search = useSearchParams();
  const qc = useQueryClient();
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(mode === "login" ? loginSchema : signupSchema),
  });

  // Store the access token returned by the backend (the mock returns
  // "mock-access-token"; the real API returns a JWT) and enter the dashboard.
  const finish = (session: { access_token: string }) => {
    setToken(session.access_token);
    qc.clear();
    router.replace(search.get("redirect") ?? "/dashboard");
  };

  const submit = handleSubmit(async (values) => {
    setBusy(true);
    setServerError("");
    try {
      const session =
        mode === "login"
          ? await api.login({ email: values.email, password: values.password })
          : await api.signup({
              email: values.email,
              password: values.password,
              display_name: values.display_name ?? "",
            });
      finish(session);
    } catch (e) {
      setServerError(errorMessage(e));
      setBusy(false);
    }
  });

  // Initialize Google Identity Services when a client id is configured. The
  // callback hands the id_token to the backend (POST /api/auth/google).
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    loadGoogleScript()
      .then(() => {
        googleApi()?.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (resp: { credential: string }) => {
            setBusy(true);
            setServerError("");
            try {
              finish(await api.google(resp.credential));
            } catch (e) {
              setServerError(errorMessage(e));
              setBusy(false);
            }
          },
        });
      })
      .catch((e) => setServerError(errorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const googleSignIn = () => {
    if (!GOOGLE_CLIENT_ID) {
      setServerError("Google sign-in isn't configured — set NEXT_PUBLIC_GOOGLE_CLIENT_ID. Use email for now.");
      return;
    }
    googleApi()?.accounts.id.prompt();
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      {mode === "signup" && (
        <div>
          <label className="field-label" htmlFor="auth-name">Name</label>
          <input id="auth-name" {...register("display_name")} className="field" placeholder="Ada Rao" />
          {errors.display_name && <p className="field-error">{errors.display_name.message}</p>}
        </div>
      )}

      <div>
        <label className="field-label" htmlFor="auth-email">Work email</label>
        <input id="auth-email" {...register("email")} className="field" placeholder="you@company.com" autoComplete="email" />
        {errors.email && <p className="field-error">{errors.email.message}</p>}
      </div>

      <div>
        <label className="field-label" htmlFor="auth-password">Password</label>
        <input
          id="auth-password"
          type="password"
          {...register("password")}
          className="field"
          placeholder="••••••••"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
        />
        {errors.password && <p className="field-error">{errors.password.message}</p>}
      </div>

      {serverError && <p className="field-error">{serverError}</p>}

      <button type="submit" className="btn btn-primary w-full" disabled={busy}>
        {busy && <Loader2 className="h-4 w-4 animate-spin" />}
        {mode === "login" ? "Sign in" : "Create account"}
      </button>

      <button
        type="button"
        className="btn btn-secondary w-full"
        disabled={busy}
        onClick={googleSignIn}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
          <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.43.34-2.1V7.06H2.18A11 11 0 0 0 1 12c0 1.77.43 3.45 1.18 4.94l3.66-2.84z" />
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.16-3.16A11 11 0 0 0 12 1 11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z" />
        </svg>
        Continue with Google
      </button>

    </form>
  );
}

export function AuthShell({ mode }: { mode: "login" | "signup" }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-white px-4 py-12">
      <div className="blob -left-32 top-0 h-[28rem] w-[28rem]" style={{ background: "var(--color-primary-50)" }} />
      <div className="blob -right-20 bottom-0 h-[24rem] w-[24rem]" style={{ background: "rgba(209,255,0,0.25)" }} />

      <div className="relative w-full max-w-md">
        <Link href="https://skillshare.think41.com" className="mb-8 flex items-center justify-center gap-2.5">
          <Logo className="h-9 w-9" />
          <span className="font-display text-2xl font-semibold tracking-tight">
            Skill<span className="text-primary">Share</span>
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">by Think41</span>
        </Link>

        <div className="card p-8">
          <h1 className="font-display text-2xl font-semibold">
            {mode === "login" ? "Welcome back." : "Create your account."}
          </h1>
          <p className="mt-1.5 text-sm text-body">
            {mode === "login"
              ? "Sign in to your org's skill registry."
              : "Free tier — no card required."}
          </p>

          <div className="mt-6">
            <Suspense>
              <AuthForm mode={mode} />
            </Suspense>
          </div>
        </div>

        <p className="mt-5 text-center text-sm text-body">
          {mode === "login" ? (
            <>New to SkillShare? <Link href="/signup" className="font-bold text-primary hover:underline">Create an account</Link></>
          ) : (
            <>Already have an account? <Link href="/login" className="font-bold text-primary hover:underline">Sign in</Link></>
          )}
        </p>
      </div>
    </main>
  );
}
