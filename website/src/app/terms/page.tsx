import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { LegalPage } from "@/components/LegalPage";
import { getPage } from "@/lib/content";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "The terms for using SkillShare by Think41 — the skill and MCP registry. Free in v1, with rules for publishing and acceptable use.",
  alternates: { canonical: "/terms" },
};

export const revalidate = 60;

export default async function Terms() {
  const page = await getPage("terms");
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
