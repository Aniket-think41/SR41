import type { Metadata } from "next";
import { Schibsted_Grotesk, Manrope, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";
import { SITE } from "@/lib/site";

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
  metadataBase: new URL(SITE.url),
  title: {
    default: "SkillShare by Think41 — The skill & MCP registry your AI team needs",
    template: "%s · SkillShare by Think41",
  },
  description:
    "SkillShare by Think41 is a structured marketplace for AI skills, MCP servers, and team knowledge — scoped to your org, your project, or the world.",
  keywords: ["AI skills", "MCP servers", "skill registry", "Think41", "SkillShare", "MCP marketplace"],
  openGraph: {
    type: "website",
    siteName: "SkillShare by Think41",
    url: SITE.url,
    title: "SkillShare by Think41 — The skill & MCP registry your AI team needs",
    description:
      "A structured marketplace for AI skills, MCP servers, and team knowledge — scoped to your org, your project, or the world.",
  },
  twitter: {
    card: "summary_large_image",
    title: "SkillShare by Think41",
    description: "The skill and MCP registry your AI team actually needs.",
  },
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
      <body className="min-h-full flex flex-col">
        {/* Set the theme class before paint to avoid a flash of the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <NextIntlClientProvider>
          <Nav />
          <main className="flex-1">{children}</main>
          <Footer />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
