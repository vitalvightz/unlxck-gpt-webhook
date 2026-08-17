import assert from "node:assert/strict";
import test from "node:test";

import {
  BOTTOM_NAV_ITEMS,
  isStandaloneNutritionPath,
  NUTRITION_DISABLED_REDIRECT,
  SIDE_NAV_ITEMS,
  STANDALONE_NUTRITION_ENABLED,
} from "./beta-navigation.ts";

test("bottom nav shows Overview, Today, Plan and Camp Setup", () => {
  assert.deepEqual(
    BOTTOM_NAV_ITEMS.map((item) => item.label),
    ["Overview", "Today", "Plan", "Camp Setup"],
  );
});

test("Progress is not promoted into primary navigation", () => {
  assert.equal(BOTTOM_NAV_ITEMS.some((item) => item.label === "Progress"), false);
  assert.equal(SIDE_NAV_ITEMS.some((item) => item.label === "Progress"), false);
  assert.equal(BOTTOM_NAV_ITEMS.some((item) => item.label === "Camp Setup"), true);
});

test("bottom nav never links to the standalone Nutrition route", () => {
  assert.equal(
    BOTTOM_NAV_ITEMS.some((item) => isStandaloneNutritionPath(item.href)),
    false,
  );
});

test("side menu keeps Camp Setup without exposing Progress", () => {
  assert.deepEqual(
    SIDE_NAV_ITEMS.map((item) => item.label),
    ["Overview", "Today", "Plan", "History", "Camp Setup", "Settings"],
  );
});

test("side menu explains the Plan, Camp Setup and Settings destinations", () => {
  assert.deepEqual(
    SIDE_NAV_ITEMS.filter((item) => ["Plan", "Camp Setup", "Settings"].includes(item.label)),
    [
      { href: "/plans", label: "Plan", meta: "Active and saved plans" },
      { href: "/onboarding", label: "Camp Setup", meta: "Build your camp" },
      { href: "/settings", label: "Settings", meta: "Account & preferences" },
    ],
  );
});

test("side menu no longer exposes standalone Nutrition", () => {
  assert.equal(
    SIDE_NAV_ITEMS.some(
      (item) => item.label === "Nutrition" || isStandaloneNutritionPath(item.href),
    ),
    false,
  );
});

test("standalone Nutrition is disabled for beta and redirects to Overview", () => {
  assert.equal(STANDALONE_NUTRITION_ENABLED, false);
  assert.equal(NUTRITION_DISABLED_REDIRECT, "/");
});

test("isStandaloneNutritionPath matches the workspace and its sub-pages only", () => {
  assert.equal(isStandaloneNutritionPath("/nutrition"), true);
  assert.equal(isStandaloneNutritionPath("/nutrition/bodyweight-log"), true);
  assert.equal(isStandaloneNutritionPath("/nutrition?tab=weight"), true);
  assert.equal(isStandaloneNutritionPath("/nutrition#readiness"), true);
  assert.equal(isStandaloneNutritionPath("/progress"), false);
  assert.equal(isStandaloneNutritionPath("/plans"), false);
  assert.equal(isStandaloneNutritionPath("/"), false);
  assert.equal(isStandaloneNutritionPath("/plans/abc#nutrition"), false);
});
