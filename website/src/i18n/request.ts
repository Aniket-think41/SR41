import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, LOCALES, i18nEnabled, type Locale } from "./config";

/** next-intl request config — cookie-based locale, no URL routing. When the
 *  marketplace i18n flag is off, always serves the default locale regardless of
 *  any stale cookie. */
export default getRequestConfig(async () => {
  const store = await cookies();
  const raw = store.get(LOCALE_COOKIE)?.value;
  const locale: Locale =
    i18nEnabled() && (LOCALES as readonly string[]).includes(raw ?? "")
      ? (raw as Locale)
      : DEFAULT_LOCALE;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
