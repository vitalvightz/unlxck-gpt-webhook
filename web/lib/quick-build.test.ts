import test from "node:test";
import assert from "node:assert/strict";

import { emptyQuickBuildInput, validateQuickBuildInput } from "@/lib/quick-build";

function buildValidInput() {
  return {
    ...emptyQuickBuildInput("Athlete"),
    technical_style: ["boxing"],
    tactical_style: ["pressure_fighter"],
    no_scheduled_fight: true,
    rounds_format: "3 x 3",
    weekly_training_frequency: 3,
    training_availability: ["monday", "wednesday", "friday"],
    equipment_access: ["barbell", "dumbbells"],
    key_goals: ["conditioning", "power"],
    weak_areas: ["gas_tank"],
  };
}

test("validateQuickBuildInput rejects multiple technical styles", () => {
  const input = buildValidInput();
  input.technical_style = ["boxing", "muay_thai"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.technical_style, "Pick only one technical style.");
});

test("validateQuickBuildInput rejects multiple tactical styles", () => {
  const input = buildValidInput();
  input.tactical_style = ["pressure_fighter", "counter_fighter"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.tactical_style, "Pick only one tactical style.");
});
