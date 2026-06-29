import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDaysOutContext,
  filterAvailablePerformanceFocusValues,
  getPerformanceFocusOptionAvailability,
  HARD_SPARRING_STRENGTH_BLOCK_REASON,
} from "./days-out-policy.ts";

const KEY_GOALS = ["power", "strength", "conditioning", "speed", "skill_refinement", "mobility", "recovery", "weight_cut"] as const;
const WEAK_AREAS = ["gas_tank", "strength", "power", "speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"] as const;

const KEY_GOAL_EXPECTATIONS: Array<{ daysOut: number; available: string[] }> = [
  { daysOut: 14, available: [...KEY_GOALS] },
  { daysOut: 13, available: ["power", "speed", "skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 8, available: ["power", "speed", "skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 7, available: ["speed", "skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 5, available: ["speed", "skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 4, available: ["skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 2, available: ["skill_refinement", "mobility", "recovery", "weight_cut"] },
  { daysOut: 1, available: ["mobility", "recovery", "weight_cut"] },
  { daysOut: 0, available: ["mobility", "recovery", "weight_cut"] },
];

const WEAK_AREA_EXPECTATIONS: Array<{ daysOut: number; available: string[] }> = [
  { daysOut: 14, available: [...WEAK_AREAS] },
  { daysOut: 13, available: ["power", "speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"] },
  { daysOut: 8, available: ["power", "speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"] },
  { daysOut: 7, available: ["speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"] },
  { daysOut: 5, available: ["speed", "footwork", "balance", "mobility", "coordination", "trunk_strength"] },
  { daysOut: 4, available: ["footwork", "balance", "mobility", "coordination"] },
  { daysOut: 2, available: ["footwork", "balance", "mobility", "coordination"] },
  { daysOut: 1, available: ["balance", "mobility", "coordination"] },
  { daysOut: 0, available: ["balance", "mobility", "coordination"] },
];

test("applies key goal availability at each fight-date boundary", () => {
  for (const { daysOut, available } of KEY_GOAL_EXPECTATIONS) {
    const ctx = buildDaysOutContext(daysOut);

    assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "key_goals", [...KEY_GOALS]), available, `D-${daysOut}`);
  }
});

test("applies weak area availability at each fight-date boundary", () => {
  for (const { daysOut, available } of WEAK_AREA_EXPECTATIONS) {
    const ctx = buildDaysOutContext(daysOut);

    assert.deepStrictEqual(filterAvailablePerformanceFocusValues(ctx, "weak_areas", [...WEAK_AREAS]), available, `D-${daysOut}`);
  }
});

test("uses specific days-out disabled reasons before focus-cap reasons", () => {
  const ctx = buildDaysOutContext(6);

  assert.equal(
    getPerformanceFocusOptionAvailability(ctx, "key_goals", "conditioning").reason,
    "Too late to build conditioning safely.",
  );
  assert.equal(
    getPerformanceFocusOptionAvailability(ctx, "weak_areas", "gas_tank").reason,
    "Too late to build gas tank safely.",
  );
});

test("keeps strength available at D-14 without hard sparring", () => {
  const ctx = buildDaysOutContext(14, { hasHardSparring: false });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength").available, true);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength").available, true);
});

test("blocks strength at D-13 without hard sparring", () => {
  const ctx = buildDaysOutContext(13, { hasHardSparring: false });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength").available, false);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength").available, false);
});

test("keeps strength available at D-21 with hard sparring", () => {
  const ctx = buildDaysOutContext(21, { hasHardSparring: true });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength").available, true);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength").available, true);
});

test("keeps strength available without a fight date when hard sparring is selected", () => {
  const ctx = buildDaysOutContext(null, { hasHardSparring: true });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength").available, true);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength").available, true);
});

test("blocks strength at D-20 with hard sparring and uses the hard-sparring reason", () => {
  const ctx = buildDaysOutContext(20, { hasHardSparring: true });

  assert.deepEqual(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength"), {
    available: false,
    reason: HARD_SPARRING_STRENGTH_BLOCK_REASON,
  });
  assert.deepEqual(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength"), {
    available: false,
    reason: HARD_SPARRING_STRENGTH_BLOCK_REASON,
  });
});

test("blocks strength at D-18 with hard sparring", () => {
  const ctx = buildDaysOutContext(18, { hasHardSparring: true });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "strength").available, false);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "strength").available, false);
});

test("adding hard sparring at D-20 removes existing strength selections", () => {
  const ctx = buildDaysOutContext(20, { hasHardSparring: true });

  assert.deepEqual(
    filterAvailablePerformanceFocusValues(ctx, "key_goals", ["strength", "mobility"]),
    ["mobility"],
  );
  assert.deepEqual(
    filterAvailablePerformanceFocusValues(ctx, "weak_areas", ["strength", "mobility"]),
    ["mobility"],
  );
});

test("removing hard sparring does not auto-readd strength", () => {
  const ctx = buildDaysOutContext(20, { hasHardSparring: false });

  assert.deepEqual(filterAvailablePerformanceFocusValues(ctx, "key_goals", ["mobility"]), ["mobility"]);
  assert.deepEqual(filterAvailablePerformanceFocusValues(ctx, "weak_areas", ["mobility"]), ["mobility"]);
});

test("hard sparring strength rule does not change existing non-strength days-out rules", () => {
  const ctx = buildDaysOutContext(20, { hasHardSparring: true });

  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "conditioning").available, true);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "gas_tank").available, true);
});
