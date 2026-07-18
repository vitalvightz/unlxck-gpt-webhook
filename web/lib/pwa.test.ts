import assert from "node:assert/strict";
import test from "node:test";

import {
  createPwaWorkerUrl,
  isIosDevice,
  isPwaCriticalWorkflow,
  isStandaloneDisplay,
  PWA_INSTALL_GUIDE_DISMISSED_KEY,
  rememberInstallGuideDismissal,
  resolvePwaInstallAvailability,
  shouldReloadForPwaControllerChange,
  shouldRegisterServiceWorker,
} from "./pwa";

test("service-worker URL changes with the production deployment fingerprint", () => {
  const first = createPwaWorkerUrl("commit-a1");
  const sameBuild = createPwaWorkerUrl("commit-a1");
  const nextBuild = createPwaWorkerUrl("commit-b2");

  assert.match(first, /^\/sw\.js\?build=[a-z0-9]+$/);
  assert.equal(first, sameBuild);
  assert.notEqual(first, nextBuild);
});

test("standalone detection supports display-mode and iOS navigator.standalone", () => {
  assert.equal(isStandaloneDisplay(true, false), true);
  assert.equal(isStandaloneDisplay(false, true), true);
  assert.equal(isStandaloneDisplay(false, false), false);
  assert.equal(isStandaloneDisplay(false, undefined), false);
});

test("iOS detection covers iPhone, iPad, and touch-enabled iPadOS desktop user agents", () => {
  assert.equal(isIosDevice("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"), true);
  assert.equal(isIosDevice("Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)"), true);
  assert.equal(isIosDevice("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)", 5), true);
  assert.equal(isIosDevice("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15)", 0), false);
  assert.equal(isIosDevice("Mozilla/5.0 (Linux; Android 15)"), false);
});

test("install availability stays hidden until detection and only exposes real install routes", () => {
  assert.equal(
    resolvePwaInstallAvailability({ hasNativePrompt: false, installed: null, ios: false }),
    "checking",
  );
  assert.equal(
    resolvePwaInstallAvailability({ hasNativePrompt: true, installed: true, ios: false }),
    "installed",
  );
  assert.equal(
    resolvePwaInstallAvailability({ hasNativePrompt: true, installed: false, ios: false }),
    "native",
  );
  assert.equal(
    resolvePwaInstallAvailability({ hasNativePrompt: false, installed: false, ios: true }),
    "ios-manual",
  );
  assert.equal(
    resolvePwaInstallAvailability({ hasNativePrompt: false, installed: false, ios: false }),
    "unsupported",
  );
});

test("critical PWA workflows cover generation, intake, triage, and admin review", () => {
  for (const path of [
    "/admin",
    "/admin/review/123",
    "/generate",
    "/intake",
    "/new-plan",
    "/onboarding/profile",
    "/quick-build",
  ]) {
    assert.equal(isPwaCriticalWorkflow(path), true, path);
  }
  assert.equal(isPwaCriticalWorkflow("/plans/123", "?review_required=1"), true);
  assert.equal(isPwaCriticalWorkflow("/plans/123", "?protected_triage=1"), true);
  assert.equal(isPwaCriticalWorkflow("/plans/123"), false);
  assert.equal(isPwaCriticalWorkflow("/dashboard"), false);
});

test("service-worker controller changes reload only after one explicit refresh request", () => {
  assert.equal(shouldReloadForPwaControllerChange(false, false), false);
  assert.equal(shouldReloadForPwaControllerChange(false, true), false);
  assert.equal(shouldReloadForPwaControllerChange(true, false), true);
  assert.equal(shouldReloadForPwaControllerChange(true, true), false);
});

test("service-worker registration is production-only and capability-gated", () => {
  assert.equal(shouldRegisterServiceWorker("production", true), true);
  assert.equal(shouldRegisterServiceWorker("development", true), false);
  assert.equal(shouldRegisterServiceWorker("test", true), false);
  assert.equal(shouldRegisterServiceWorker("production", false), false);
});

test("install-guide dismissal is stored without making storage mandatory", () => {
  const writes = new Map<string, string>();
  rememberInstallGuideDismissal({ setItem: (key, value) => writes.set(key, value) }, 1234);
  assert.equal(writes.get(PWA_INSTALL_GUIDE_DISMISSED_KEY), "1234");

  assert.doesNotThrow(() =>
    rememberInstallGuideDismissal({
      setItem: () => {
        throw new Error("storage blocked");
      },
    }),
  );
});
