import type { Metadata } from "next";
import { Schibsted_Grotesk, Manrope, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Providers } from "@/components/Providers";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";

const schibsted = Schibsted_Grotesk({
  variable: "--font-schibsted",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: {
    default: "Dashboard · SkillShare by Think41",
    template: "%s · SkillShare",
  },
  description:
    "The SkillShare dashboard — manage your org's skills, MCP servers, and notes across projects and pods.",
  robots: { index: false }, // the dashboard is private; the website handles SEO
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  return (
    <html
      lang={locale}
      className={`${schibsted.variable} ${manrope.variable} ${jetbrains.variable} h-full`}
    >
      <body className="min-h-full">
        {/* Set the theme class before paint to avoid a flash of the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
