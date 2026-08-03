import assert from "node:assert/strict";
import test from "node:test";

import {
  BOTTOM_NAV_ITEMS,
  isStandaloneNutritionPath,
  NUTRITION_DISABLED_REDIRECT,
  SIDE_NAV_ITEMS,
  STANDALONE_NUTRITION_ENABLED,
} from "./beta-navigation.ts";

test("bottom nav shows Overview, Today, Plan and Progress", () => {
  assert.deepEqual(
    BOTTOM_NAV_ITEMS.map((item) => item.label),
    ["Overview", "Today", "Plan", "Progress"],
  );
});

test("Progress replaces Intake only in the compact bottom nav", () => {
  assert.equal(BOTTOM_NAV_ITEMS.some((item) => item.label === "Progress"), true);
  assert.equal(BOTTOM_NAV_ITEMS.some((item) => item.label === "Intake"), false);
  assert.equal(SIDE_NAV_ITEMS.some((item) => item.label === "Intake"), true);
});

test("Progress routes to the full XP interface", () => {
  const progress = BOTTOM_NAV_ITEMS.find((item) => item.label === "Progress");
  assert.equal(progress?.href, "/progress");
});

test("bottom nav never links to the standalone Nutrition route", () => {
  assert.equal(
    BOTTOM_NAV_ITEMS.some((item) => isStandaloneNutritionPath(item.href)),
    false,
  );
});

test("side menu places Progress between Plan and History", () => {
  assert.deepEqual(
    SIDE_NAV_ITEMS.map((item) => item.label),
    ["Overview", "Today", "Plan", "Progress", "History", "Intake", "Settings"],
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
