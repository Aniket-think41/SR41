import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LegalPage } from "@/components/LegalPage";
import { getPage } from "@/lib/content";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How SkillShare by Think41 collects, uses, and protects your data — including the secret-redaction guarantees for the CLI and MCP.",
  alternates: { canonical: "/privacy" },
};

export const revalidate = 60;

export default async function Privacy() {
  const page = await getPage("privacy");
  if (!page) notFound();
  return (
    <LegalPage
      kicker={page.kicker}
      title={page.title}
      intro={page.intro}
      updated={page.updated}
      sections={page.sections}
    />
  );
}
