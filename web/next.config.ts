import type { NextConfig } from "next";

const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";

function resolveBackendUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV !== "production") {
    return LOCAL_API_BASE_URL;
  }

  throw new Error("NEXT_PUBLIC_API_BASE_URL must be set in production for /api rewrites.");
}

const nextConfig: NextConfig = {
  async rewrites() {
    const backendUrl = resolveBackendUrl();
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
