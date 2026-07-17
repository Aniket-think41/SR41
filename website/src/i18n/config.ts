/** Locales the marketing site ships. Add a code + messages/<code>.json and it
 *  appears in the language switcher automatically.
 *
 *  The switcher itself is gated by a marketplace-level feature flag
 *  (NEXT_PUBLIC_I18N_ENABLED === "true"); see i18nEnabled(). */
export const LOCALES = ["en", "hi"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "NEXT_LOCALE";

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  hi: "हिन्दी",
};

/** Marketplace-wide feature flag for internationalization. Off → the language
 *  switcher is hidden and the site renders in the default locale. */
export function i18nEnabled(): boolean {
  return process.env.NEXT_PUBLIC_I18N_ENABLED === "true";
}
