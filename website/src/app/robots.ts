import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";

// Allow full indexing of public routes; disallow dashboard surfaces (spec §6).
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/login", "/signup"],
    },
    sitemap: `${SITE.url}/sitemap.xml`,
    host: SITE.url,
  };
}
