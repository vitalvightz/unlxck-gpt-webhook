/* global self, caches, fetch, URL, Response */

const CACHE_PREFIX = "unlxck-pwa-";
const BUILD_VERSION = (new URL(self.location.href).searchParams.get("build") || "shell")
  .replace(/[^a-z0-9_-]/gi, "")
  .slice(0, 32);
const PRECACHE_NAME = `${CACHE_PREFIX}precache-${BUILD_VERSION}`;
const STATIC_CACHE_NAME = `${CACHE_PREFIX}static-${BUILD_VERSION}`;
const OFFLINE_URL = "/offline.html";
const PRECACHE_URLS = [
  OFFLINE_URL,
  "/icons/icon-192x192.png",
  "/icons/icon-512x512.png",
  "/icons/icon-maskable-512x512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32x32.png",
  "/icons/favicon-16x16.png",
];
const SAFE_STATIC_PATHS = new Set(PRECACHE_URLS.slice(1));

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(PRECACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith(CACHE_PREFIX) &&
                key !== PRECACHE_NAME &&
                key !== STATIC_CACHE_NAME,
            )
            .map((key) => caches.delete(key)),
        ),
      ),
      self.clients.claim(),
    ]),
  );
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

async function networkFirstNavigation(request) {
  try {
    return await fetch(request);
  } catch {
    return (await caches.match(OFFLINE_URL)) ?? Response.error();
  }
}

async function staleWhileRevalidate(request, event) {
  const cache = await caches.open(STATIC_CACHE_NAME);
  const cached = await cache.match(request);
  const networkRequest = fetch(request)
    .then((response) => {
      if (response.ok && response.type === "basic") {
        return cache.put(request, response.clone()).then(() => response);
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    event.waitUntil(networkRequest);
    return cached;
  }

  return (await networkRequest) ?? Response.error();
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  const isVersionedNextAsset = url.pathname.startsWith("/_next/static/");
  if (isVersionedNextAsset || SAFE_STATIC_PATHS.has(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request, event));
  }
});
