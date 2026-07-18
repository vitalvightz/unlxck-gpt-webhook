import type { MetadataRoute } from "next";

const APP_DESCRIPTION =
  "Athlete-first fight camp planning, daily training intelligence, and coach review.";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "UNLXCK",
    short_name: "UNLXCK",
    description: APP_DESCRIPTION,
    start_url: "/dashboard?source=pwa",
    scope: "/",
    display: "standalone",
    background_color: "#0a0a0b",
    theme_color: "#0a0a0b",
    categories: ["fitness", "health", "sports"],
    icons: [
      {
        src: "/icons/icon-192x192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-maskable-512x512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      {
        name: "Dashboard",
        short_name: "Dashboard",
        description: "Open your athlete dashboard.",
        url: "/dashboard?source=pwa-shortcut",
        icons: [{ src: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" }],
      },
      {
        name: "Today",
        short_name: "Today",
        description: "Open today’s readiness and training command centre.",
        url: "/today?source=pwa-shortcut",
        icons: [{ src: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" }],
      },
      {
        name: "Plans",
        short_name: "Plans",
        description: "Open your active and saved fight camps.",
        url: "/plans?source=pwa-shortcut",
        icons: [{ src: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" }],
      },
    ],
  };
}
