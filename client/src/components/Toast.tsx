"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";

interface ToastItem {
  id: number;
  kind: "success" | "error";
  message: string;
}

const ToastCtx = createContext<{
  toast: (message: string, kind?: ToastItem["kind"]) => void;
}>({ toast: () => {} });

export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const toast = useCallback((message: string, kind: ToastItem["kind"] = "success") => {
    const id = ++seq.current;
    setItems((xs) => [...xs, { id, kind, message }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4200);
  }, []);

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-6 right-6 z-[100] flex w-80 flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className="pop pointer-events-auto flex items-start gap-3 rounded-2xl border border-line bg-white p-4 shadow-[0_18px_40px_-16px_rgba(20,20,19,0.3)]"
            role="status"
          >
            {t.kind === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-success)]" />
            ) : (
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-danger)]" />
            )}
            <p className="flex-1 text-sm font-medium text-ink">{t.message}</p>
            <button
              onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}
              className="text-muted hover:text-ink"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
