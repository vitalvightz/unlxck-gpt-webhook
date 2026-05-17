import test from "node:test";
import assert from "node:assert/strict";

import { emptyQuickBuildInput, quickBuildToPlanRequest, validateQuickBuildInput } from "@/lib/quick-build";

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

test("validateQuickBuildInput accepts an empty hard_sparring_days list", () => {
  const input = buildValidInput();
  input.hard_sparring_days = [];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.hard_sparring_days, undefined);
});

test("validateQuickBuildInput rejects hard sparring days outside training availability", () => {
  const input = buildValidInput();
  input.hard_sparring_days = ["wednesday", "saturday"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.hard_sparring_days, "Hard sparring days must be inside your training days.");
});

test("validateQuickBuildInput rejects more than four hard sparring days", () => {
  const input = buildValidInput();
  input.training_availability = ["monday", "tuesday", "wednesday", "thursday", "friday"];
  input.hard_sparring_days = ["monday", "tuesday", "wednesday", "thursday", "friday"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.hard_sparring_days, "Pick at most 4 hard sparring days.");
});

test("quickBuildToPlanRequest forwards hard sparring days to the plan request", () => {
  const input = buildValidInput();
  input.hard_sparring_days = ["monday", "wednesday"];
  const plan = quickBuildToPlanRequest(input);
  assert.deepEqual(plan.hard_sparring_days, ["monday", "wednesday"]);
});

test("quickBuildToPlanRequest drops hard sparring days that are not training days", () => {
  const input = buildValidInput();
  input.hard_sparring_days = ["monday", "saturday"];
  const plan = quickBuildToPlanRequest(input);
  assert.deepEqual(plan.hard_sparring_days, ["monday"]);
});
