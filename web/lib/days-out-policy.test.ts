import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDaysOutContext,
  filterAvailablePerformanceFocusValues,
  getPerformanceFocusOptionAvailability,
} from "./days-out-policy.ts";

const KEY_GOALS = ["power", "strength", "conditioning", "speed", "skill_refinement", "mobility", "recovery", "weight_cut"];
const WEAK_AREAS = ["gas_tank", "strength", "power", "speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"];

test("blocks unavailable key goals at six days out before selection", () => {
  const ctx = buildDaysOutContext(6);

  assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "key_goals", KEY_GOALS), [
    "speed",
    "skill_refinement",
    "mobility",
    "recovery",
    "weight_cut",
  ]);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "conditioning").reason, "Too late to build conditioning.");
});

test("blocks unavailable weak areas at six days out before selection", () => {
  const ctx = buildDaysOutContext(6);

  assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "weak_areas", WEAK_AREAS), [
    "speed",
    "footwork",
    "balance",
    "mobility",
    "coordination",
    "trunk_strength",
  ]);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "gas_tank").reason, "Too late to build gas tank.");
});

test("keeps only freshness-safe performance focus values at one day out", () => {
  const ctx = buildDaysOutContext(1);

  assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "key_goals", KEY_GOALS), [
    "mobility",
    "recovery",
    "weight_cut",
  ]);
  assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "weak_areas", WEAK_AREAS), [
    "balance",
    "mobility",
    "coordination",
  ]);
});
