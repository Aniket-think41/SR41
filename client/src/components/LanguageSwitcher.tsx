"use client";

/**
 * Language switcher — sets the NEXT_LOCALE cookie and refreshes so the server
 * re-renders with the chosen locale's messages (next-intl, cookie-based, no URL
 * change). Kept tiny so it drops into the TopBar next to the theme toggle.
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { Globe, Check } from "lucide-react";
import { LOCALES, LOCALE_LABELS, LOCALE_COOKIE, type Locale } from "@/i18n/config";

export function LanguageSwitcher() {
  const active = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [, startTransition] = useTransition();

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
        className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition hover:border-primary hover:text-primary"
      >
        <Globe className="h-4 w-4" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-40 overflow-hidden rounded-xl border border-line bg-card py-1 shadow-lg">
            {LOCALES.map((loc) => (
              <button
                key={loc}
                onClick={() => choose(loc)}
                className="flex w-full items-center justify-between px-3 py-2 text-sm text-body transition hover:bg-surface hover:text-ink"
              >
                {LOCALE_LABELS[loc]}
                {loc === active && <Check className="h-4 w-4 text-primary" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
