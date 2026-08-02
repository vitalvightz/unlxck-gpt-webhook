import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import manifest from "../app/manifest";

const WEB_ROOT = process.cwd();

function readPublic(relativePath: string): Buffer {
  return readFileSync(path.join(WEB_ROOT, "public", relativePath));
}

function pngDimensions(buffer: Buffer): { width: number; height: number } {
  const signature = buffer.subarray(0, 8).toString("hex");
  assert.equal(signature, "89504e470d0a1a0a", "asset must be a real PNG");
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

test("manifest exposes the production install contract and shortcuts", () => {
  const value = manifest();
  assert.equal(value.id, "/");
  assert.equal(value.name, "UNLXCK");
  assert.equal(value.short_name, "UNLXCK");
  assert.equal(value.start_url, "/dashboard?source=pwa");
  assert.equal(value.scope, "/");
  assert.equal(value.display, "standalone");
  assert.equal(value.background_color, "#0a0a0b");
  assert.equal(value.theme_color, "#0a0a0b");
  assert.deepEqual(value.categories, ["fitness", "health", "sports"]);
  assert.deepEqual(
    value.icons,
    [
      {
        src: "/brand/unlxck-one-angle-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/brand/unlxck-one-angle-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
    ],
  );
  assert.deepEqual(
    value.shortcuts?.map((shortcut) => shortcut.name),
    ["Dashboard", "Today", "Plans"],
  );
  assert.ok(
    value.shortcuts?.every(
      (shortcut) => shortcut.icons?.[0]?.src === "/brand/unlxck-one-angle-192.png",
    ),
  );
});

test("all referenced one-angle icons exist with exact dimensions", () => {
  const expected = new Map([
    ["brand/unlxck-one-angle-512.png", 512],
    ["brand/unlxck-one-angle-192.png", 192],
    ["brand/unlxck-one-angle-180.png", 180],
    ["brand/unlxck-one-angle-48.png", 48],
    ["brand/unlxck-one-angle-32.png", 32],
  ]);

  expected.forEach((size, relativePath) => {
    assert.deepEqual(pngDimensions(readPublic(relativePath)), { width: size, height: size }, relativePath);
  });
  assert.ok(readPublic("favicon.ico").length > 0, "favicon.ico must exist");
});

test("offline fallback is branded, connection-honest, and retryable", () => {
  const html = readPublic("offline.html").toString("utf8");
  assert.match(html, /UNLXCK can’t connect right now\./);
  assert.match(html, /account data and fight-camp plans require a connection/i);
  assert.match(html, /Retry connection/);
  assert.doesNotMatch(html, /localStorage|sessionStorage|access_token|service_role/i);
});

test("service worker only runtime-caches safe static assets", () => {
  const source = readPublic("sw.js").toString("utf8");
  assert.match(source, /request\.method !== "GET"/);
  assert.match(source, /url\.origin !== self\.location\.origin/);
  assert.match(source, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.match(source, /request\.mode === "navigate"/);
  assert.match(source, /caches\.match\(OFFLINE_URL\)/);
  assert.match(source, /url\.pathname\.startsWith\("\/_next\/static\/"\)/);
  assert.match(source, /isVersionedNextAsset \|\| SAFE_STATIC_PATHS\.has\(url\.pathname\)/);
  assert.match(source, /event\.data\?\.type === "SKIP_WAITING"/);
  assert.match(source, /const APP_ICON_192 = "\/brand\/unlxck-one-angle-192\.png"/);
  assert.match(source, /icon: APP_ICON_192/);
  assert.match(source, /badge: APP_ICON_192/);
  assert.doesNotMatch(source, /\/icons\//);
  const navigationHandler = source.match(
    /async function networkFirstNavigation\(request\) \{[\s\S]*?\n\}/,
  )?.[0];
  assert.ok(navigationHandler);
  assert.doesNotMatch(navigationHandler, /cache\.put/);
  assert.doesNotMatch(source, /self\.skipWaiting\(\)[\s\S]*install/);

  for (const forbiddenPath of [
    "/plans",
    "/profiles",
    "/generation_jobs",
    "/check-ins",
    "/nutrition",
    "/admin",
  ]) {
    assert.doesNotMatch(
      source,
      new RegExp(`SAFE_STATIC_PATHS[^;]*${forbiddenPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
      forbiddenPath,
    );
  }
});
