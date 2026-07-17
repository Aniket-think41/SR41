"use client";

/**
 * Marketplace language switcher — sets the NEXT_LOCALE cookie and refreshes so
 * the server re-renders in the chosen locale (next-intl, cookie-based, no URL
 * change). Rendered only when the marketplace i18n flag is on (see i18nEnabled).
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { LOCALES, LOCALE_LABELS, LOCALE_COOKIE, i18nEnabled, type Locale } from "@/i18n/config";

export function LanguageSwitcher() {
  const active = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [, startTransition] = useTransition();

  if (!i18nEnabled()) return null;

  function choose(locale: Locale) {
    document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
    setOpen(false);
    startTransition(() => router.refresh());
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Change language"
        title="Language"
        className="flex h-11 w-11 items-center justify-center rounded-full border border-line text-ink transition hover:border-primary hover:text-primary"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-xl border border-line bg-card py-1 shadow-lg">
            {LOCALES.map((loc) => (
              <button
                key={loc}
                onClick={() => choose(loc)}
                className={`flex w-full items-center justify-between px-3 py-2 text-sm transition hover:bg-surface ${
                  loc === active ? "font-semibold text-primary" : "text-body hover:text-ink"
                }`}
              >
                {LOCALE_LABELS[loc]}
                {loc === active && <span aria-hidden>✓</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
