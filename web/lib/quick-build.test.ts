import test from "node:test";
import assert from "node:assert/strict";

import {
  emptyQuickBuildInput,
  planRequestToQuickBuildInput,
  quickBuildToPlanRequest,
  sanitizeQuickBuildFocusByDaysOut,
  validateQuickBuildInput,
} from "@/lib/quick-build";
import { buildDaysOutContext, getPerformanceFocusOptionAvailability } from "@/lib/days-out-policy";
import { emptyPlanRequest } from "@/lib/onboarding";

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

function formatDateOffsetFrom(baseIsoDate: string, offsetDays: number): string {
  const base = new Date(`${baseIsoDate}T00:00:00Z`);
  base.setUTCDate(base.getUTCDate() + offsetDays);
  return base.toISOString().slice(0, 10);
}

test("validateQuickBuildInput rejects multiple technical styles", () => {
  const input = buildValidInput();
  input.technical_style = ["boxing", "muay_thai"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.technical_style, "Pick only one combat sport.");
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
  input.hard_sparring_days = ["Wednesday", "Saturday"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.hard_sparring_days, "Hard sparring days must be inside your training days.");
});

test("validateQuickBuildInput rejects more than four hard sparring days", () => {
  const input = buildValidInput();
  input.training_availability = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
  input.hard_sparring_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
  const errors = validateQuickBuildInput(input);
  assert.equal(errors.hard_sparring_days, "Pick at most 4 hard sparring days.");
});

// Reconciled: quickBuildToPlanRequest filters hard sparring days against
// training_availability using the CANONICAL (capitalised) option values, so the
// fixture must supply capitalised availability — the earlier lowercase fixture
// mismatched the days and dropped them, which is a test-data bug, not a
// regression.
test("quickBuildToPlanRequest forwards hard sparring days to the plan request", () => {
  const input = buildValidInput();
  input.training_availability = ["Monday", "Wednesday", "Friday"];
  input.hard_sparring_days = ["Monday", "Wednesday"];
  const plan = quickBuildToPlanRequest(input);
  assert.deepEqual(plan.hard_sparring_days, ["Monday", "Wednesday"]);
});

test("quickBuildToPlanRequest drops hard sparring days that are not training days", () => {
  const input = buildValidInput();
  input.training_availability = ["Monday", "Wednesday", "Friday"];
  input.hard_sparring_days = ["Monday", "Saturday"];
  const plan = quickBuildToPlanRequest(input);
  assert.deepEqual(plan.hard_sparring_days, ["Monday"]);
});

test("quickBuildToPlanRequest promotes first quick build focus values to primary", () => {
  const input = buildValidInput();
  input.key_goals = ["power", "conditioning"];
  input.weak_areas = ["mobility", "coordination"];

  const plan = quickBuildToPlanRequest(input);

  assert.deepEqual(plan.key_goals, ["power", "conditioning"]);
  assert.equal(plan.primary_goal, "power");
  assert.deepEqual(plan.weak_areas, ["mobility", "coordination"]);
  assert.equal(plan.primary_weak_area, "mobility");
});

test("planRequestToQuickBuildInput pulls advanced onboarding fields", () => {
  const plan = emptyPlanRequest("Athlete");
  plan.athlete.technical_style = ["boxing"];
  plan.athlete.tactical_style = ["pressure_fighter"];
  plan.fight_date = "2026-12-01";
  plan.no_scheduled_fight = false;
  plan.rounds_format = "5 x 3";
  plan.weekly_training_frequency = 5;
  plan.training_availability = ["Monday", "Tuesday", "Thursday", "Friday", "Saturday"];
  plan.hard_sparring_days = ["Tuesday", "Friday"];
  plan.equipment_access = ["barbell", "dumbbells"];
  plan.key_goals = ["conditioning"];
  plan.weak_areas = ["gas_tank"];
  plan.injuries = "Left knee tightness.";

  const input = planRequestToQuickBuildInput(plan);
  assert.equal(input.full_name, "Athlete");
  assert.deepEqual(input.technical_style, ["boxing"]);
  assert.deepEqual(input.tactical_style, ["pressure_fighter"]);
  assert.equal(input.fight_date, "2026-12-01");
  assert.equal(input.no_scheduled_fight, false);
  assert.equal(input.rounds_format, "5 x 3");
  assert.equal(input.weekly_training_frequency, 5);
  assert.deepEqual(input.training_availability, [
    "Monday",
    "Tuesday",
    "Thursday",
    "Friday",
    "Saturday",
  ]);
  assert.deepEqual(input.hard_sparring_days, ["Tuesday", "Friday"]);
  assert.deepEqual(input.equipment_access, ["barbell", "dumbbells"]);
  assert.deepEqual(input.key_goals, ["conditioning"]);
  assert.deepEqual(input.weak_areas, ["gas_tank"]);
  assert.equal(input.injuries, "Left knee tightness.");
});

test("planRequestToQuickBuildInput drops hard sparring days outside availability", () => {
  const plan = emptyPlanRequest("Athlete");
  plan.training_availability = ["Monday", "Tuesday"];
  plan.hard_sparring_days = ["Monday", "Saturday"];
  const input = planRequestToQuickBuildInput(plan);
  assert.deepEqual(input.hard_sparring_days, ["Monday"]);
});

test("planRequestToQuickBuildInput shows the athlete's own words, not the structured comprehension", () => {
  const plan = emptyPlanRequest("Athlete");
  // plan.injuries holds the planner's derived comprehension after advanced intake.
  plan.injuries =
    "Left shoulder is bruised (low, stable). Type: surface_injury. Surface: bruise. Impact related: yes";
  plan.guided_injuries = [
    {
      area: "Left shoulder is bruised",
      severity: "low",
      trend: "stable",
      injury_type: "surface_injury",
      surface_type: "bruise",
      impact_related: "yes",
      notes: "knocked it sparring [chest_symptoms:none]",
    },
  ];

  const input = planRequestToQuickBuildInput(plan);
  // The athlete sees what they typed (area + free-text note), with the derived
  // fields and internal [tag:...] flags stripped — not the comprehension blob.
  assert.equal(input.injuries, "Left shoulder is bruised. knocked it sparring");
});

test("planRequestToQuickBuildInput keeps free-text injuries when there are no guided injuries", () => {
  const plan = emptyPlanRequest("Athlete");
  plan.injuries = "Left knee tightness.";
  plan.guided_injuries = [];
  const input = planRequestToQuickBuildInput(plan);
  assert.equal(input.injuries, "Left knee tightness.");
});

test("planRequestToQuickBuildInput clears fight_date when no_scheduled_fight is true", () => {
  const plan = emptyPlanRequest("Athlete");
  plan.fight_date = "2026-12-01";
  plan.no_scheduled_fight = true;
  const input = planRequestToQuickBuildInput(plan);
  assert.equal(input.no_scheduled_fight, true);
  assert.equal(input.fight_date, "");
});

test("sanitizeQuickBuildFocusByDaysOut prunes conditioning and power when fight date moves close", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = formatDateOffsetFrom(new Date().toISOString().slice(0, 10), 3);
  input.key_goals = ["conditioning", "power", "mobility"];
  input.weak_areas = ["power", "gas_tank", "mobility"];

  const sanitized = sanitizeQuickBuildFocusByDaysOut(input);
  assert.deepEqual(sanitized.key_goals, ["mobility"]);
  assert.deepEqual(sanitized.weak_areas, ["mobility"]);
});

test("validateQuickBuildInput rejects unavailable days-out focus values", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = "2026-05-27";
  input.key_goals = ["conditioning"];
  input.weak_areas = ["gas_tank"];
  const errors = validateQuickBuildInput(input, { now: new Date("2026-05-24T00:00:00Z") });
  assert.equal(errors.key_goals, "One or more goals are not available for this fight window.");
  assert.equal(errors.weak_areas, "One or more weak areas are not available for this fight window.");
});

test("validateQuickBuildInput allows open camp focus values", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = true;
  input.fight_date = "";
  input.key_goals = ["conditioning", "power"];
  input.weak_areas = ["gas_tank", "power"];
  const errors = validateQuickBuildInput(input, { now: new Date("2026-05-24T00:00:00Z") });
  assert.equal(errors.key_goals, undefined);
  assert.equal(errors.weak_areas, undefined);
});

// D-27 is the "Short camp" band, capped at 4 shared focus picks. 3 goals + 1
// weak area sits exactly on that cap, so the shared cap stays quiet here while
// the days-out filtering still applies.
test("validateQuickBuildInput keeps shared focus cap active with days-out filtering", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = "2026-06-20";
  input.key_goals = ["conditioning", "power", "mobility"];
  input.weak_areas = ["gas_tank"];
  const errors = validateQuickBuildInput(input, { now: new Date("2026-05-24T00:00:00Z") });
  assert.equal(errors.focus_cap, undefined);
  assert.equal(errors.key_goals, undefined);
  assert.equal(errors.weak_areas, undefined);
});

test("D-1 blocks gas_tank and conditioning availability", () => {
  const ctx = buildDaysOutContext(1);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "weak_areas", "gas_tank").available, false);
  assert.equal(getPerformanceFocusOptionAvailability(ctx, "key_goals", "conditioning").available, false);
});

test("sanitizeQuickBuildFocusByDaysOut removes gas_tank when fight date changes from D-30 to D-1", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.key_goals = ["mobility"];
  input.weak_areas = ["gas_tank", "mobility"];

  input.fight_date = "2026-06-23";
  const stillFar = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));
  assert.deepEqual(stillFar.weak_areas, ["gas_tank", "mobility"]);

  input.fight_date = "2026-05-25";
  const d1 = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));
  assert.deepEqual(d1.weak_areas, ["mobility"]);
});

test("sanitizeQuickBuildFocusByDaysOut removes strength when hard sparring is added at D-20", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = "2026-06-13";
  input.hard_sparring_days = ["Monday"];
  input.key_goals = ["strength", "mobility"];
  input.weak_areas = ["strength", "mobility"];

  const sanitized = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));

  assert.deepEqual(sanitized.key_goals, ["mobility"]);
  assert.deepEqual(sanitized.weak_areas, ["mobility"]);
});

test("sanitizeQuickBuildFocusByDaysOut keeps strength key goals for no scheduled fight with hard sparring", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = true;
  input.fight_date = "";
  input.hard_sparring_days = ["Monday"];
  input.key_goals = ["strength", "mobility"];
  input.weak_areas = ["mobility"];

  const sanitized = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));

  assert.deepEqual(sanitized.key_goals, ["strength", "mobility"]);
});

test("sanitizeQuickBuildFocusByDaysOut keeps strength weak areas for no scheduled fight with hard sparring", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = true;
  input.fight_date = "";
  input.hard_sparring_days = ["Monday"];
  input.key_goals = ["mobility"];
  input.weak_areas = ["strength", "mobility"];

  const sanitized = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));

  assert.deepEqual(sanitized.weak_areas, ["strength", "mobility"]);
});

test("sanitizeQuickBuildFocusByDaysOut does not auto-readd strength when hard sparring is removed", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = "2026-06-13";
  input.hard_sparring_days = [];
  input.key_goals = ["mobility"];
  input.weak_areas = ["mobility"];

  const sanitized = sanitizeQuickBuildFocusByDaysOut(input, new Date("2026-05-24T00:00:00Z"));

  assert.deepEqual(sanitized.key_goals, ["mobility"]);
  assert.deepEqual(sanitized.weak_areas, ["mobility"]);
});

// One pick past the D-27 short-camp cap of 4.
test("validateQuickBuildInput blocks generation when focus cap is exceeded", () => {
  const input = buildValidInput();
  input.no_scheduled_fight = false;
  input.fight_date = "2026-06-20";
  input.key_goals = ["conditioning", "power", "mobility"];
  input.weak_areas = ["gas_tank", "mobility"];
  const errors = validateQuickBuildInput(input, { now: new Date("2026-05-24T00:00:00Z") });
  assert.equal(
    errors.focus_cap,
    "This camp allows 4 total focus picks. Remove 1 goal or weak-area selection before generating.",
  );
});
