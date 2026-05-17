import test from "node:test";
import assert from "node:assert/strict";

import {
  EQUIPMENT_ACCESS_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
} from "@/lib/intake-options";
import {
  EQUIPMENT_PRESETS,
  TRAINING_PRESETS,
  deriveSetupSource,
  matchesEquipmentPreset,
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
