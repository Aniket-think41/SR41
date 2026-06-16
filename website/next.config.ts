import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // The marketplace is now the homepage (/). Keep the old URL working —
      // resource detail pages (/marketplace/:id) are unaffected (exact match).
      { source: "/marketplace", destination: "/", permanent: true },
    ];
  },
};

export default nextConfig;
