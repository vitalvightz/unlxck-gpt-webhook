import assert from "node:assert/strict";
import test from "node:test";

import { emptyPlanRequest } from "./onboarding";
import { emptyQuickBuildInput } from "./quick-build";
import {
  HEALTH_CONSENT_BLOCKED_MESSAGE,
  withoutIntakeHealthData,
  withoutQuickBuildHealthData,
} from "./health-consent-ui";

test("health consent UI uses the compliance message", () => {
  assert.equal(HEALTH_CONSENT_BLOCKED_MESSAGE, "Health data consent required. Manage it in Settings → Privacy.");
});

test("withdrawal removes current weight, target weight, fatigue, and restrictions from Intake state", () => {
  const input = emptyPlanRequest("Athlete");
  input.athlete.weight_kg = 72;
  input.athlete.target_weight_kg = 68;
  input.fatigue_level = "high";
  input.injuries = "Sore knee";
  input.guided_injury = { area: "Knee", notes: "Sore" };
  input.guided_injuries = [{ area: "Knee", notes: "Sore" }];

  const safe = withoutIntakeHealthData(input);
  assert.equal(safe.athlete.weight_kg, null);
  assert.equal(safe.athlete.target_weight_kg, null);
  assert.equal(safe.fatigue_level, "low");
  assert.equal(safe.injuries, "");
  assert.equal(safe.guided_injury, null);
  assert.deepEqual(safe.guided_injuries, []);
  assert.equal(safe.athlete.full_name, "Athlete", "non-health Intake remains usable");
  assert.notEqual(safe, input, "historical source data is not mutated");
});

test("withdrawal removes Quick Build restrictions but keeps non-health setup", () => {
  const input = { ...emptyQuickBuildInput("Athlete"), injuries: "Shoulder pain", equipment_access: ["gym"] };
  const safe = withoutQuickBuildHealthData(input);
  assert.equal(safe.injuries, "");
  assert.equal(safe.full_name, "Athlete");
  assert.deepEqual(safe.equipment_access, ["gym"]);
  assert.equal(input.injuries, "Shoulder pain", "historical source data is not mutated");
});
