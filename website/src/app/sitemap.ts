import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";
import { getResources, getPublishers } from "@/lib/data";

// Auto-generated sitemap for all public routes (spec §6).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = SITE.url;
  const now = new Date();
  const [resources, publishers] = await Promise.all([getResources(), getPublishers()]);

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${base}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/how-it-works`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/marketplace`, lastModified: now, changeFrequency: "daily", priority: 0.9 },
    { url: `${base}/pricing`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/blog`, lastModified: now, changeFrequency: "weekly", priority: 0.6 },
  ];

  const resourceRoutes: MetadataRoute.Sitemap = resources.map((r) => ({
    url: `${base}/marketplace/${r.id}`,
    lastModified: new Date(r.updated_at),
    changeFrequency: "weekly",
    priority: 0.7,
  }));

  const publisherRoutes: MetadataRoute.Sitemap = publishers.map((p) => ({
    url: `${base}/publishers/${p.username}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  return [...staticRoutes, ...resourceRoutes, ...publisherRoutes];
}
