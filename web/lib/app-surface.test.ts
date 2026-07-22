import test from "node:test";
import assert from "node:assert/strict";

import {
  getServerShellSurface,
  getShellSurface,
  isAuthSurfaceRoute,
} from "./app-surface";

const AUTH_ROUTES = ["/login", "/signup", "/forgot-password", "/reset-password"];

test("auth routes are identified as auth-surface routes", () => {
  for (const route of AUTH_ROUTES) {
    assert.equal(isAuthSurfaceRoute(route), true, `${route} should be an auth route`);
  }
});

test("the homepage and workspace routes are not auth-surface routes", () => {
  assert.equal(isAuthSurfaceRoute("/"), false);
  assert.equal(isAuthSurfaceRoute("/plans"), false);
  assert.equal(isAuthSurfaceRoute("/today"), false);
  assert.equal(isAuthSurfaceRoute("/admin"), false);
});

test("auth routes always resolve to the brand surface, logged in or out", () => {
  for (const route of AUTH_ROUTES) {
    assert.equal(getShellSurface(route, false), "brand", `${route} logged out`);
    // Signed-in visitors are redirected off auth pages, so we never want the
    // workspace chrome to flash in behind the form.
    assert.equal(getShellSurface(route, true), "brand", `${route} logged in`);
  }
});

test("the homepage is brand when logged out and workspace when signed in", () => {
  assert.equal(getShellSurface("/", false), "brand");
  assert.equal(getShellSurface("/", true), "workspace");
});

test("workspace routes resolve to the workspace surface", () => {
  assert.equal(getShellSurface("/plans", true), "workspace");
  assert.equal(getShellSurface("/plans", false), "workspace");
  assert.equal(getShellSurface("/today", true), "workspace");
});

test("the server commits the brand surface only for auth routes", () => {
  for (const route of AUTH_ROUTES) {
    assert.equal(getServerShellSurface(route), "brand", `${route} should be SSR brand`);
  }
});

test("the server defers non-auth routes to the client (returns null)", () => {
  // The homepage and workspace routes depend on the client session, which the
  // server cannot know, so it must not commit a surface for them.
  assert.equal(getServerShellSurface("/"), null);
  assert.equal(getServerShellSurface("/plans"), null);
  assert.equal(getServerShellSurface(null), null);
  assert.equal(getServerShellSurface(undefined), null);
});
