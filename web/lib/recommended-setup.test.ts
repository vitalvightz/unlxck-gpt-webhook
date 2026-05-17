import test from "node:test";
import assert from "node:assert/strict";

import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
} from "@/lib/intake-options";
import {
  EQUIPMENT_PRESETS,
  FOCUS_PRESETS,
  TRAINING_PRESETS,
  deriveSetupSource,
  getAvailableFocusPresets,
  matchesEquipmentPreset,
  matchesFocusPreset,
  matchesTrainingPreset,
} from "@/lib/recommended-setup";

test("every equipment preset value exists in EQUIPMENT_ACCESS_OPTIONS", () => {
  const known = new Set(EQUIPMENT_ACCESS_OPTIONS.map((option) => option.value));
  for (const preset of EQUIPMENT_PRESETS) {
    for (const value of preset.equipment_access) {
      assert.ok(known.has(value), `${preset.key} -> "${value}" missing from EQUIPMENT_ACCESS_OPTIONS`);
    }
  }
});

test("every training preset day exists in TRAINING_AVAILABILITY_OPTIONS", () => {
  const known = new Set(TRAINING_AVAILABILITY_OPTIONS.map((option) => option.value));
  for (const preset of TRAINING_PRESETS) {
    for (const value of preset.training_availability) {
      assert.ok(known.has(value), `${preset.key} -> "${value}" missing from TRAINING_AVAILABILITY_OPTIONS`);
    }
  }
});

test("training preset frequency matches its training-day count", () => {
  for (const preset of TRAINING_PRESETS) {
    assert.equal(
      preset.weekly_training_frequency,
      preset.training_availability.length,
      `${preset.key} frequency must equal day count`,
    );
  }
});

test("equipment presets round-trip through matchesEquipmentPreset", () => {
  for (const preset of EQUIPMENT_PRESETS) {
    assert.equal(matchesEquipmentPreset(preset.equipment_access), preset.key);
    // Order-insensitive: shuffled copy should still match.
    const shuffled = [...preset.equipment_access].reverse();
    assert.equal(matchesEquipmentPreset(shuffled), preset.key);
  }
});

test("training presets round-trip through matchesTrainingPreset", () => {
  for (const preset of TRAINING_PRESETS) {
    assert.equal(
      matchesTrainingPreset(preset.training_availability, preset.weekly_training_frequency),
      preset.key,
    );
  }
});

test("matchesEquipmentPreset returns null for non-preset selections", () => {
  assert.equal(matchesEquipmentPreset([]), null);
  assert.equal(matchesEquipmentPreset(["dumbbells"]), null);
});

test("matchesTrainingPreset returns null when frequency differs from preset", () => {
  const threeDay = TRAINING_PRESETS.find((preset) => preset.key === "three_days")!;
  assert.equal(matchesTrainingPreset(threeDay.training_availability, 2), null);
});

test("deriveSetupSource maps preset hits to source label", () => {
  assert.equal(deriveSetupSource(["home", "three_days"]), "preset");
  assert.equal(deriveSetupSource(["home", null]), "mixed");
  assert.equal(deriveSetupSource([null, null]), "manual");
  assert.equal(deriveSetupSource([]), "manual");
});

test("every focus preset key_goal exists in KEY_GOAL_OPTIONS", () => {
  const known = new Set(KEY_GOAL_OPTIONS.map((option) => option.value));
  for (const preset of FOCUS_PRESETS) {
    for (const value of preset.key_goals) {
      assert.ok(known.has(value), `${preset.key} -> "${value}" missing from KEY_GOAL_OPTIONS`);
    }
  }
});

test("every focus preset weak_area exists in WEAK_AREA_OPTIONS", () => {
  const known = new Set(WEAK_AREA_OPTIONS.map((option) => option.value));
  for (const preset of FOCUS_PRESETS) {
    for (const value of preset.weak_areas) {
      assert.ok(known.has(value), `${preset.key} -> "${value}" missing from WEAK_AREA_OPTIONS`);
    }
  }
});

test("every focus preset stays at or below the fight-week cap of 2 selections", () => {
  // Minimum performance-focus cap is 2 (fight week). Presets above this would be
  // hidden in fight week — keep them ≤ 2 so they survive every camp window.
  for (const preset of FOCUS_PRESETS) {
    const total = preset.key_goals.length + preset.weak_areas.length;
    assert.ok(total <= 2, `${preset.key} has ${total} selections, exceeds fight-week cap`);
  }
});

test("focus presets round-trip through matchesFocusPreset", () => {
  for (const preset of FOCUS_PRESETS) {
    assert.equal(matchesFocusPreset(preset.key_goals, preset.weak_areas), preset.key);
  }
});

test("matchesFocusPreset is order-insensitive", () => {
  const mobilityRecovery = FOCUS_PRESETS.find((preset) => preset.key === "mobility_recovery")!;
  const reversed = [...mobilityRecovery.key_goals].reverse();
  assert.equal(matchesFocusPreset(reversed, mobilityRecovery.weak_areas), "mobility_recovery");
});

test("matchesFocusPreset returns null for non-preset selections", () => {
  assert.equal(matchesFocusPreset([], []), null);
  assert.equal(matchesFocusPreset(["weight_cut"], []), null);
  assert.equal(matchesFocusPreset(["power"], ["gas_tank"]), null);
});

test("Mobility & recovery uses recovery + mobility, no weak areas", () => {
  const preset = FOCUS_PRESETS.find((entry) => entry.key === "mobility_recovery")!;
  assert.deepEqual([...preset.key_goals].sort(), ["mobility", "recovery"]);
  assert.deepEqual(preset.weak_areas, []);
});

test("getAvailableFocusPresets in open camp hides fight_sharpness", () => {
  const available = getAvailableFocusPresets({ fightDate: "", noScheduledFight: true });
  const keys = available.map((entry) => entry.preset.key);
  assert.ok(keys.includes("strength_base"));
  assert.ok(keys.includes("explosive_power"));
  assert.ok(keys.includes("gas_tank"));
  assert.ok(keys.includes("mobility_recovery"));
  assert.ok(!keys.includes("fight_sharpness"));
});

function fightDateInDays(days: number, now: Date): string {
  const target = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  target.setUTCDate(target.getUTCDate() + days);
  const y = target.getUTCFullYear();
  const m = String(target.getUTCMonth() + 1).padStart(2, "0");
  const d = String(target.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

test("getAvailableFocusPresets at fight week shows only Fight Sharpness and Mobility & Recovery", () => {
  const now = new Date(Date.UTC(2026, 4, 17));
  for (const days of [0, 3, 7]) {
    const available = getAvailableFocusPresets({
      fightDate: fightDateInDays(days, now),
      noScheduledFight: false,
      now,
      timeZone: "UTC",
    });
    const keys = available.map((entry) => entry.preset.key);
    assert.deepEqual([...keys].sort(), ["fight_sharpness", "mobility_recovery"], `days=${days}`);
  }
});

test("getAvailableFocusPresets at 14 days still hides Strength Base and Explosive Power", () => {
  const now = new Date(Date.UTC(2026, 4, 17));
  const available = getAvailableFocusPresets({
    fightDate: fightDateInDays(14, now),
    noScheduledFight: false,
    now,
    timeZone: "UTC",
  });
  const keys = available.map((entry) => entry.preset.key);
  assert.ok(!keys.includes("strength_base"));
  assert.ok(!keys.includes("explosive_power"));
  assert.ok(keys.includes("fight_sharpness"));
  assert.ok(keys.includes("mobility_recovery"));
});

test("getAvailableFocusPresets at 21 days shows mid-camp set", () => {
  const now = new Date(Date.UTC(2026, 4, 17));
  const available = getAvailableFocusPresets({
    fightDate: fightDateInDays(21, now),
    noScheduledFight: false,
    now,
    timeZone: "UTC",
  });
  const keys = available.map((entry) => entry.preset.key);
  assert.deepEqual([...keys].sort(), [
    "explosive_power",
    "fight_sharpness",
    "gas_tank",
    "mobility_recovery",
  ]);
});

test("getAvailableFocusPresets at 43 days drops Fight Sharpness and adds Strength Base", () => {
  const now = new Date(Date.UTC(2026, 4, 17));
  const available = getAvailableFocusPresets({
    fightDate: fightDateInDays(43, now),
    noScheduledFight: false,
    now,
    timeZone: "UTC",
  });
  const keys = available.map((entry) => entry.preset.key);
  assert.deepEqual([...keys].sort(), [
    "explosive_power",
    "gas_tank",
    "mobility_recovery",
    "strength_base",
  ]);
});

test("getAvailableFocusPresets never disables a preset under current caps", () => {
  // Every shipping preset has ≤ 2 selections and minimum cap is 2, so disabledReason
  // should always be null. If this breaks, either the preset shape or the cap rules
  // changed and the defensive branch becomes meaningful.
  const now = new Date(Date.UTC(2026, 4, 17));
  for (const days of [0, 7, 14, 21, 42, 56, 90]) {
    const available = getAvailableFocusPresets({
      fightDate: fightDateInDays(days, now),
      noScheduledFight: false,
      now,
      timeZone: "UTC",
    });
    for (const entry of available) {
      assert.equal(entry.disabledReason, null, `days=${days} key=${entry.preset.key}`);
    }
  }
});

test("deriveSetupSource handles three-way match with focus presets", () => {
  assert.equal(deriveSetupSource(["home", "three_days", "gas_tank"]), "preset");
  assert.equal(deriveSetupSource(["home", null, "gas_tank"]), "mixed");
  assert.equal(deriveSetupSource([null, null, null]), "manual");
});
