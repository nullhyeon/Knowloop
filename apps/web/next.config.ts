import type { NextConfig } from "next";

const knowloopApiBaseUrl =
  process.env.KNOWLOOP_API_BASE_URL ?? process.env.NEXT_PUBLIC_KNOWLOOP_API_BASE_URL ?? "http://127.0.0.1:8000";

const normalizedApiBaseUrl = knowloopApiBaseUrl.replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${normalizedApiBaseUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
