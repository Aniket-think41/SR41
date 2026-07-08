"use client";

/**
 * Promise-based destructive-confirm modal. A call to `confirm({...})` opens a
 * dialog and resolves true/false when the user acts. For deletes it requires the
 * user to type an exact phrase (default "/delete") before the button unlocks —
 * a deliberate speed-bump for irreversible actions. Mirrors the Toast provider.
 *
 *   const confirm = useConfirm();
 *   if (await confirm({ title: `Delete "${name}"?`, message: "…" })) mut.mutate();
 */

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmOptions {
  title: string;
  message?: string;
  /** Phrase the user must type to unlock the confirm button. Default "/delete".
   *  Pass null to skip the type-to-confirm gate (a plain confirm). */
  requireType?: string | null;
  confirmLabel?: string;
}

const ConfirmCtx = createContext<{ confirm: (opts: ConfirmOptions) => Promise<boolean> }>({
  confirm: async () => false,
});

export const useConfirm = () => useContext(ConfirmCtx).confirm;

interface Pending extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [typed, setTyped] = useState("");
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const confirm = useCallback((opts: ConfirmOptions) => {
    setTyped("");
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
      setPending({ ...opts, resolve });
    });
  }, []);

  const close = (ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setPending(null);
    setTyped("");
  };

  // "/delete" by default; null disables the gate.
  const phrase = pending ? (pending.requireType === undefined ? "/delete" : pending.requireType) : null;
  const gated = !!phrase;
  const unlocked = !gated || typed.trim() === phrase;

  return (
    <ConfirmCtx.Provider value={{ confirm }}>
      {children}
      {pending && (
        <div
          className="overlay-fade fixed inset-0 z-[110] flex items-center justify-center bg-navy/40 p-4 backdrop-blur-[2px]"
          onClick={() => close(false)}
          role="dialog"
          aria-modal
        >
          <div className="card relative w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => close(false)}
              className="absolute right-4 top-4 rounded-full p-1.5 text-muted transition hover:bg-surface hover:text-ink"
              aria-label="Cancel"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-[var(--color-danger)]">
                <AlertTriangle className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <h2 className="font-display text-lg font-semibold text-ink">{pending.title}</h2>
                {pending.message && <p className="mt-1 text-sm leading-relaxed text-body">{pending.message}</p>}
              </div>
            </div>

            {gated && (
              <div className="mt-4">
                <label className="field-label" htmlFor="confirm-type">
                  Type <span className="code font-bold text-[var(--color-danger)]">{phrase}</span> to confirm
                </label>
                <input
                  id="confirm-type"
                  autoFocus
                  autoComplete="off"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && unlocked && close(true)}
                  placeholder={phrase}
                  className="field code"
                />
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => close(false)} className="btn btn-secondary btn-sm">
                Cancel
              </button>
              <button
                onClick={() => close(true)}
                disabled={!unlocked}
                className="btn btn-danger btn-sm"
              >
                {pending.confirmLabel ?? "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmCtx.Provider>
  );
}
