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
    value.shortcuts?.map((shortcut) => shortcut.name),
    ["Dashboard", "Today", "Plans"],
  );
  assert.ok(value.icons?.some((icon) => icon.sizes === "512x512" && icon.purpose === "maskable"));
});

test("all referenced app icons exist with exact dimensions", () => {
  const expected = new Map([
    ["icons/icon-192x192.png", 192],
    ["icons/icon-512x512.png", 512],
    ["icons/icon-maskable-512x512.png", 512],
    ["icons/apple-touch-icon.png", 180],
    ["icons/favicon-32x32.png", 32],
    ["icons/favicon-16x16.png", 16],
  ]);

  expected.forEach((size, relativePath) => {
    assert.deepEqual(pngDimensions(readPublic(relativePath)), { width: size, height: size }, relativePath);
  });
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
  assert.match(source, /event\.data\?\.type === "SKIP_WAITING"/);
  assert.doesNotMatch(source, /self\.skipWaiting\(\)[\s\S]*install/);
});
