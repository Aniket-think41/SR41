"use client";

/**
 * Mandatory first-entry password screen (frontend spec — §auth).
 * Rendered by the dashboard layout instead of the app whenever the signed-in
 * user still has must_change_password set: brand-new signups, Google accounts
 * (who never chose a password), and invited users on a temp password. The
 * backend skips current-password verification while the flag is set, so we only
 * collect a new password + confirmation. Cleared by POST /api/auth/change-password.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import { qk } from "@/lib/hooks";
import type { User } from "@/lib/types";
import { Logo } from "@/components/Logo";

export function ChangePasswordGate({ user }: { user: User }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");

  const mut = useMutation({
    mutationFn: () => api.changePassword({ new_password: password }),
    onSuccess: async () => {
      // Refresh the session so must_change_password flips false and the app shows.
      await qc.invalidateQueries({ queryKey: qk.me });
    },
    onError: (e) => setError(errorMessage(e)),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) return setError("Use at least 8 characters.");
    if (password !== confirm) return setError("Passwords don't match.");
    mut.mutate();
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-card px-4 py-12">
      <div className="blob -left-32 top-0 h-[28rem] w-[28rem]" style={{ background: "var(--color-primary-50)" }} />
      <div className="blob -right-20 bottom-0 h-[24rem] w-[24rem]" style={{ background: "rgba(209,255,0,0.25)" }} />

      <div className="relative w-full max-w-md">
        <div className="mb-8 flex items-center justify-center gap-2.5">
          <Logo className="h-9 w-9" />
          <span className="font-display text-2xl font-semibold tracking-tight">
            Skill<span className="text-primary">Share</span>
          </span>
        </div>

        <div className="card p-8">
          <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--color-primary-50)] text-primary">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <h1 className="font-display mt-4 text-2xl font-semibold">Set your password</h1>
          <p className="mt-1.5 text-sm text-body">
            Welcome, {user.display_name}. Before you continue, choose a password for your
            account — you&apos;ll use it to sign in with your email.
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="field-label" htmlFor="cpg-pw">New password</label>
              <input
                id="cpg-pw"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="field"
                placeholder="••••••••"
                autoComplete="new-password"
                autoFocus
              />
            </div>
            <div>
              <label className="field-label" htmlFor="cpg-confirm">Confirm password</label>
              <input
                id="cpg-confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="field"
                placeholder="••••••••"
                autoComplete="new-password"
              />
            </div>

            {error && <p className="field-error">{error}</p>}

            <button type="submit" className="btn btn-primary w-full" disabled={mut.isPending}>
              {mut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Set password &amp; continue
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
