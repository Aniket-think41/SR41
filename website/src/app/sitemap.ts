import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";
import { getResources, getPublishers, getOrgs } from "@/lib/data";
import { allPosts } from "@/lib/blog";

// Auto-generated sitemap for all public routes (spec §6).
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = SITE.url;
  const now = new Date();
  const [resources, publishers, posts, orgs] = await Promise.all([
    getResources(),
    getPublishers(),
    allPosts(),
    getOrgs(),
  ]);

  const staticRoutes: MetadataRoute.Sitemap = [
    // The marketplace is now the homepage; /marketplace 301-redirects here.
    { url: `${base}/`, lastModified: now, changeFrequency: "daily", priority: 1 },
    { url: `${base}/home`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/how-it-works`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/pricing`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/orgs`, lastModified: now, changeFrequency: "weekly", priority: 0.6 },
    { url: `${base}/feedback`, lastModified: now, changeFrequency: "weekly", priority: 0.5 },
    { url: `${base}/blog`, lastModified: now, changeFrequency: "weekly", priority: 0.6 },
    { url: `${base}/privacy`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${base}/terms`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
  ];

  const blogRoutes: MetadataRoute.Sitemap = posts.map((p) => ({
    url: `${base}/blog/${p.slug}`,
    lastModified: new Date(p.date),
    changeFrequency: "monthly",
    priority: 0.5,
  }));

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

  const orgRoutes: MetadataRoute.Sitemap = orgs.map((o) => ({
    url: `${base}/orgs/${o.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  return [...staticRoutes, ...blogRoutes, ...resourceRoutes, ...publisherRoutes, ...orgRoutes];
}
