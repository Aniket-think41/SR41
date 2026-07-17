import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // The marketplace is now the homepage (/). Keep the old URL working —
      // resource detail pages (/marketplace/:id) are unaffected (exact match).
      { source: "/marketplace", destination: "/", permanent: true },
    ];
  },
};

// Cookie-based i18n (no URL routing) — reads src/i18n/request.ts.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
