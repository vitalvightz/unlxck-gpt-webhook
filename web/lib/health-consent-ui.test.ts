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

test("withdrawal omits every generation health field from Intake state without mutation", () => {
  const input = emptyPlanRequest("Athlete");
  input.athlete.weight_kg = 72;
  input.athlete.target_weight_kg = 68;
  input.fatigue_level = "high";
  input.injuries = "Sore knee";
  input.guided_injury = { area: "Knee", notes: "Sore" };
  input.guided_injuries = [{ area: "Knee", notes: "Sore" }];

  const safe = withoutIntakeHealthData(input);
  assert.equal("weight_kg" in safe.athlete, false);
  assert.equal("target_weight_kg" in safe.athlete, false);
  assert.equal("fatigue_level" in safe, false);
  assert.equal("injuries" in safe, false);
  assert.equal("guided_injury" in safe, false);
  assert.equal("guided_injuries" in safe, false);
  assert.equal(safe.athlete.full_name, "Athlete", "non-health Intake remains usable");
  assert.notEqual(safe, input, "historical source data is not mutated");
  assert.notEqual(safe.athlete, input.athlete, "nested athlete data is not mutated");
  assert.equal(input.fatigue_level, "high");
  assert.equal(input.athlete.weight_kg, 72);
  assert.deepEqual(input.guided_injuries, [{ area: "Knee", notes: "Sore" }]);
});

test("withdrawal removes Quick Build restrictions but keeps non-health setup", () => {
  const input = { ...emptyQuickBuildInput("Athlete"), injuries: "Shoulder pain", equipment_access: ["gym"] };
  const safe = withoutQuickBuildHealthData(input);
  assert.equal(safe.injuries, "");
  assert.equal(safe.full_name, "Athlete");
  assert.deepEqual(safe.equipment_access, ["gym"]);
  assert.equal(input.injuries, "Shoulder pain", "historical source data is not mutated");
});

test("Quick Build does not invent a fatigue value", async () => {
  const { quickBuildToPlanRequest } = await import("./quick-build");
  const request = quickBuildToPlanRequest(emptyQuickBuildInput("Athlete"));

  assert.equal(request.fatigue_level, undefined);
  assert.equal("fatigue_level" in JSON.parse(JSON.stringify(request)), false);
});
