import type { NextConfig } from "next";

const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";
const MISSING_PRODUCTION_REWRITE_WARNING =
  "NEXT_PUBLIC_API_BASE_URL is not set; skipping /api rewrites for this production build.";

function resolveBackendUrl(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV !== "production") {
    return LOCAL_API_BASE_URL;
  }

  return null;
}

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl = resolveBackendUrl();
    if (!backendUrl) {
      console.warn(MISSING_PRODUCTION_REWRITE_WARNING);
      return [];
    }

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
