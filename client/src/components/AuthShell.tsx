"use client";

/**
 * Shared layout + form logic for /login and /signup.
 *
 * Signup is a two-step, email-verified flow: submit email/password → we email a
 * one-time code → enter the code → account is created and you're signed in.
 * Login stays single-step email/password. Google and Microsoft OAuth are offered
 * when their client ids are configured; otherwise the buttons explain they're off.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, MailCheck } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage, setToken } from "@/lib/api/http";
import type { AuthSession, SignupPending } from "@/lib/types";
import { Logo } from "./Logo";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const MS_CLIENT_ID = process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID ?? "";
const MS_TENANT = process.env.NEXT_PUBLIC_MICROSOFT_TENANT ?? "common";

type GoogleId = {
  accounts: {
    id: {
      initialize: (cfg: { client_id: string; callback: (resp: { credential: string }) => void }) => void;
      prompt: (listener?: (n: PromptMoment) => void) => void;
    };
  };
};
type PromptMoment = {
  isNotDisplayed?: () => boolean;
  isSkippedMoment?: () => boolean;
  isDismissedMoment?: () => boolean;
};
const googleApi = (): GoogleId | undefined => (window as unknown as { google?: GoogleId }).google;

// Minimal shape of the MSAL browser SDK we load from CDN (mirrors Google's GIS).
type MsalResult = { idToken?: string };
type MsalApp = { loginPopup: (req: { scopes: string[] }) => Promise<MsalResult> };
type MsalNS = { PublicClientApplication: new (cfg: unknown) => MsalApp };
const msalApi = (): MsalNS | undefined => (window as unknown as { msal?: MsalNS }).msal;

// Lazily load a third-party auth script once; resolves when the global is ready.
function loadScript(src: string, ready: () => boolean): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (ready()) return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load the sign-in script"));
    document.head.appendChild(s);
  });
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
  // When set, signup moved to the "enter the code we emailed you" step.
  const [pending, setPending] = useState<SignupPending | null>(null);
  const [code, setCode] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(mode === "login" ? loginSchema : signupSchema),
  });

  const finish = (session: AuthSession) => {
    setToken(session.access_token);
    qc.clear();
    router.replace(search.get("redirect") ?? "/dashboard");
  };

  const submit = handleSubmit(async (values) => {
    setBusy(true);
    setServerError("");
    try {
      if (mode === "login") {
        finish(await api.login({ email: values.email, password: values.password }));
      } else {
        // Step 1: email a code. The account isn't created until it's verified.
        const p = await api.signup({
          email: values.email,
          password: values.password,
          display_name: values.display_name ?? "",
        });
        setPending(p);
        setBusy(false);
      }
    } catch (e) {
      setServerError(errorMessage(e));
      setBusy(false);
    }
  });

  const verify = async () => {
    if (!pending) return;
    setBusy(true);
    setServerError("");
    try {
      finish(await api.verifyEmail({ email: pending.email, code: code.trim() }));
    } catch (e) {
      setServerError(errorMessage(e));
      setBusy(false);
    }
  };

  const resend = async () => {
    if (!pending) return;
    setServerError("");
    try {
      setPending(await api.resendSignupOtp(pending.email));
    } catch (e) {
      setServerError(errorMessage(e));
    }
  };

  // Google Identity Services — initialize when a client id is configured.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    loadScript("https://accounts.google.com/gsi/client", () => !!googleApi())
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
    // Show feedback immediately so the button doesn't feel dead while Google loads.
    setBusy(true);
    setServerError("");
    googleApi()?.accounts.id.prompt((n: PromptMoment) => {
      // If the prompt never showed or was dismissed without a credential, release
      // the spinner (the credential callback handles the success path).
      if (n.isNotDisplayed?.() || n.isSkippedMoment?.() || n.isDismissedMoment?.()) setBusy(false);
    });
  };

  const microsoftSignIn = async () => {
    if (!MS_CLIENT_ID) {
      setServerError("Microsoft sign-in isn't configured — set NEXT_PUBLIC_MICROSOFT_CLIENT_ID. Use email for now.");
      return;
    }
    setBusy(true);
    setServerError("");
    try {
      await loadScript("https://alcdn.msauth.net/browser/2.38.2/js/msal-browser.min.js", () => !!msalApi());
      const msal = msalApi();
      if (!msal) throw new Error("Microsoft sign-in failed to load");
      const pca = new msal.PublicClientApplication({
        auth: { clientId: MS_CLIENT_ID, authority: `https://login.microsoftonline.com/${MS_TENANT}` },
        cache: { cacheLocation: "sessionStorage" },
      });
      const res = await pca.loginPopup({ scopes: ["openid", "email", "profile"] });
      if (!res?.idToken) throw new Error("No Microsoft token returned");
      finish(await api.microsoft(res.idToken));
    } catch (e) {
      setServerError(errorMessage(e));
      setBusy(false);
    }
  };

  // ---- OTP verification step (signup only) ----
  if (pending) {
    return (
      <div className="relative space-y-4">
        {busy && <BusyOverlay label="Verifying…" />}
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary-50 text-primary">
            <MailCheck className="h-5 w-5" />
          </span>
          <p className="text-sm text-body">
            {pending.email_sent ? (
              <>We emailed a 6-digit code to <span className="font-semibold text-ink">{pending.email}</span>. Enter it to finish.</>
            ) : (
              <>Enter the 6-digit code to finish creating your account.</>
            )}
          </p>
          {/* Dev fallback: when email delivery isn't configured the code is returned
              directly so the flow still works. */}
          {pending.dev_otp && (
            <p className="rounded-lg bg-amber-50 px-3 py-1.5 text-xs text-amber-700">
              Email delivery is off — your code is <span className="code font-bold">{pending.dev_otp}</span>
            </p>
          )}
        </div>

        <div>
          <label className="field-label" htmlFor="auth-otp">Verification code</label>
          <input
            id="auth-otp"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\s/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && verify()}
            className="field code tracking-[0.4em]"
            placeholder="••••••"
            autoFocus
          />
        </div>

        {serverError && <p className="field-error">{serverError}</p>}

        <button type="button" onClick={verify} className="btn btn-primary w-full" disabled={busy || code.length < 4}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}
          Verify & create account
        </button>

        <div className="flex items-center justify-between text-sm">
          <button type="button" onClick={() => { setPending(null); setCode(""); setServerError(""); }} className="flex items-center gap-1 font-semibold text-muted hover:text-ink">
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
          <button type="button" onClick={resend} className="font-semibold text-primary hover:underline" disabled={busy}>
            Resend code
          </button>
        </div>
      </div>
    );
  }

  // ---- Email/password + OAuth ----
  return (
    <div className="relative">
      {busy && <BusyOverlay label="Signing you in…" />}
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
          {mode === "login" ? "Sign in" : "Continue"}
        </button>

        <div className="flex items-center gap-3 py-0.5">
          <span className="h-px flex-1 bg-line" />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">or</span>
          <span className="h-px flex-1 bg-line" />
        </div>

        <button type="button" className="btn btn-secondary w-full" disabled={busy} onClick={googleSignIn}>
          <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.43.34-2.1V7.06H2.18A11 11 0 0 0 1 12c0 1.77.43 3.45 1.18 4.94l3.66-2.84z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.16-3.16A11 11 0 0 0 12 1 11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z" />
          </svg>
          Continue with Google
        </button>

        <button type="button" className="btn btn-secondary w-full" disabled={busy} onClick={microsoftSignIn}>
          <svg viewBox="0 0 23 23" className="h-4 w-4" aria-hidden>
            <path fill="#F25022" d="M1 1h10v10H1z" />
            <path fill="#7FBA00" d="M12 1h10v10H12z" />
            <path fill="#00A4EF" d="M1 12h10v10H1z" />
            <path fill="#FFB900" d="M12 12h10v10H12z" />
          </svg>
          Continue with Microsoft
        </button>
      </form>
    </div>
  );
}

function BusyOverlay({ label }: { label: string }) {
  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-2xl bg-card/85 backdrop-blur-sm">
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
      <p className="text-sm font-semibold text-muted">{label}</p>
    </div>
  );
}

export function AuthShell({ mode }: { mode: "login" | "signup" }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-card px-4 py-12">
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
              : "Free tier — no card required. We'll email you a code to confirm."}
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
