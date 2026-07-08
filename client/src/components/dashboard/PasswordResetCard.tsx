"use client";

/**
 * In-dashboard password reset via email OTP (for the signed-in user).
 *
 * Distinct from the /login change-password: here a code is emailed to the user's
 * own inbox and, once verified, they set a new password WITHOUT knowing the
 * current one — for when they've forgotten it but are still signed in. Two steps:
 * request the code, then verify it with the new password.
 */

import { useState } from "react";
import { KeyRound, Loader2, MailCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api/http";
import type { SignupPending } from "@/lib/types";
import { useToast } from "@/components/Toast";

export function PasswordResetCard({ email }: { email: string }) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<SignupPending | null>(null);
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");

  const reset = () => {
    setOpen(false);
    setSent(null);
    setCode("");
    setNewPassword("");
    setError("");
    setBusy(false);
  };

  const start = async () => {
    setOpen(true);
    setBusy(true);
    setError("");
    try {
      setSent(await api.startPasswordReset());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setError("");
    try {
      await api.verifyPasswordReset({ code: code.trim(), new_password: newPassword });
      toast("Password updated");
      reset();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card mt-5 p-4">
        <p className="flex items-center gap-1.5 text-sm font-bold text-ink">
          <KeyRound className="h-3.5 w-3.5 text-primary" /> Password
        </p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Reset your password with a code emailed to <span className="font-semibold text-ink">{email}</span> — no need
          to remember the old one.
        </p>
        <button onClick={start} className="btn btn-secondary btn-sm mt-3 w-full">
          Reset password via email
        </button>
      </div>

      {open && (
        <div
          className="overlay-fade fixed inset-0 z-[90] flex items-center justify-center bg-navy/35 p-4 backdrop-blur-[2px]"
          onClick={reset}
          role="dialog"
          aria-modal
        >
          <div className="card relative w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={reset}
              className="absolute right-4 top-4 rounded-full p-1.5 text-muted transition hover:bg-surface hover:text-ink"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-50 text-primary">
                <MailCheck className="h-5 w-5" />
              </span>
              <div>
                <h2 className="font-display text-lg font-semibold">Reset your password</h2>
                <p className="text-xs text-muted">We sent a code to {email}</p>
              </div>
            </div>

            {sent?.dev_otp && (
              <p className="mt-4 rounded-lg bg-amber-50 px-3 py-1.5 text-xs text-amber-700">
                Email delivery is off — your code is <span className="code font-bold">{sent.dev_otp}</span>
              </p>
            )}

            <div className="mt-4 space-y-3">
              <div>
                <label className="field-label" htmlFor="pr-code">Verification code</label>
                <input
                  id="pr-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\s/g, ""))}
                  className="field code tracking-[0.3em]"
                  placeholder="••••••"
                />
              </div>
              <div>
                <label className="field-label" htmlFor="pr-new">New password</label>
                <input
                  id="pr-new"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="field"
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                />
              </div>
            </div>

            {error && <p className="field-error mt-3">{error}</p>}

            <div className="mt-5 flex items-center justify-between">
              <button onClick={start} disabled={busy} className="text-sm font-semibold text-primary hover:underline">
                Resend code
              </button>
              <button
                onClick={verify}
                disabled={busy || code.length < 4 || newPassword.length < 8}
                className="btn btn-primary btn-sm"
              >
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Update password
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
