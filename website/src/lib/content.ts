/**
 * Legal / static pages (privacy, terms) for the marketing site.
 *
 * Source of truth is the backend (`/api/public/pages/{key}`), where the content
 * is managed by a platform admin. When `API_URL` is unset, the seed below is
 * used — it mirrors the backend content seed (backend/scripts/seed.py).
 */

import { publicGet } from "./api";
import type { LegalSection } from "@/components/LegalPage";

export interface ContentPage {
  key: string;
  kicker: string;
  title: string;
  intro: string;
  /** Display string, e.g. "June 15, 2026". */
  updated: string;
  sections: LegalSection[];
}

const SEED: Record<string, ContentPage> = {
  privacy: {
    key: "privacy",
    kicker: "Legal",
    title: "Privacy Policy",
    intro:
      "Plain-language summary of what we collect and how we protect it. SkillShare is v1 — this policy will grow with the product.",
    updated: "June 15, 2026",
    sections: [
      {
        heading: "Who we are",
        paragraphs: [
          "SkillShare is a skill and MCP registry operated by Think41. This policy explains what data we collect when you use the dashboard, CLI, MCP server, and public marketplace, and what we do with it.",
        ],
      },
      {
        heading: "What we collect",
        bullets: [
          "Account data — your name, email, and the organizations, projects, and pods you belong to.",
          "Content you publish — skills, MCP server configurations, notes, and their metadata.",
          "Usage data — installs, stars, and activity needed to power notifications and discovery.",
          "Authentication — Personal Access Tokens you mint for the CLI and MCP, stored hashed.",
        ],
      },
      {
        heading: "Secrets are redacted before they leave your machine",
        paragraphs: [
          "When you contribute a local skill, MCP server, or note through the CLI or MCP, we detect and redact secrets — API keys, tokens, and credentials — before anything is uploaded. You always see a redacted preview, and nothing is pushed without your explicit approval.",
          "Redaction is enforced again server-side, so a credential that slips past the client is never stored.",
        ],
      },
      {
        heading: "How we use your data",
        bullets: [
          "To operate the registry and resolve what you can see based on your membership.",
          "To notify you when resources are added or published in scopes you belong to.",
          "To show installs, stars, and verified-publisher status on the public marketplace.",
          "To keep the service secure and debug problems.",
        ],
      },
      {
        heading: "What we don't do",
        paragraphs: [
          "We don't sell your data. We don't use the private contents of your org's resources to train models. Public marketplace listings are, by design, public.",
        ],
      },
      {
        heading: "Your choices",
        bullets: [
          "Revoke a Personal Access Token at any time from the dashboard or with `skillshare logout`.",
          "Dismiss contribution recommendations — your choice is remembered and synced to your account.",
          "Request export or deletion of your account data by contacting us.",
        ],
      },
      {
        heading: "Changes",
        paragraphs: [
          "We may update this policy as the product evolves. Material changes will be noted on this page, and the “last updated” date above will change.",
        ],
      },
    ],
  },
  terms: {
    key: "terms",
    kicker: "Legal",
    title: "Terms of Service",
    intro:
      "The ground rules for using SkillShare. Free in v1, with sensible limits on publishing and acceptable use.",
    updated: "June 15, 2026",
    sections: [
      {
        heading: "Acceptance",
        paragraphs: [
          "By creating an account or using SkillShare — the dashboard, CLI, MCP server, or public marketplace — you agree to these terms. If you're using SkillShare for an organization, you agree on its behalf.",
        ],
      },
      {
        heading: "The service",
        paragraphs: [
          "SkillShare is a registry for AI skills, MCP servers, and team knowledge, operated by Think41. It is free in v1. Paid Team and Enterprise plans are planned for future versions; pricing and terms for those will be published before they launch.",
        ],
      },
      {
        heading: "Your content",
        bullets: [
          "You keep ownership of the skills, MCP configs, and notes you publish.",
          "By publishing to the public marketplace, you grant others the right to view, install, and import that resource.",
          "You're responsible for having the rights to publish what you upload, and for not including secrets or third-party confidential data.",
        ],
      },
      {
        heading: "Acceptable use",
        bullets: [
          "Don't upload malware, or skills/MCP servers designed to exfiltrate data or cause harm.",
          "Don't violate others' intellectual property or privacy.",
          "Don't abuse the API, attempt to bypass permission scopes, or disrupt the service.",
          "Don't misrepresent authorship or impersonate a verified publisher.",
        ],
      },
      {
        heading: "Verified publishers",
        paragraphs: [
          "Think41-verified status is granted at our discretion and may be revoked if these terms are violated. Verification signals identity, not an endorsement of every resource a publisher ships.",
        ],
      },
      {
        heading: "Disclaimer & liability",
        paragraphs: [
          "SkillShare is provided “as is,” without warranties of any kind. Resources on the marketplace are published by their authors — review them before installing. To the extent permitted by law, Think41 is not liable for indirect or consequential damages arising from use of the service.",
        ],
      },
      {
        heading: "Termination",
        paragraphs: [
          "You can stop using SkillShare at any time and delete your account. We may suspend or terminate access for violations of these terms.",
        ],
      },
      {
        heading: "Changes",
        paragraphs: [
          "We may update these terms as the product evolves. Material changes will be posted here, and continued use after a change means you accept the updated terms.",
        ],
      },
    ],
  },
};

export async function getPage(key: string): Promise<ContentPage | undefined> {
  const live = await publicGet<ContentPage>(`/pages/${key}`);
  if (live) return live;
  return SEED[key];
}
