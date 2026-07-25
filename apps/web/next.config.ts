import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    const origin = process.env.REVIEW_HUB_API_ORIGIN;
    if (!origin) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${origin}/api/:path*`,
      },
      {
        source: "/healthz",
        destination: `${origin}/healthz`,
      },
      {
        source: "/readyz",
        destination: `${origin}/readyz`,
      },
    ];
  },
};

export default nextConfig;
