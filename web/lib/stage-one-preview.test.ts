import test from "node:test";
import assert from "node:assert/strict";

import { buildStageOnePreview, selectCampBrief, selectTriage } from "@/lib/stage-one-preview";
import type { PlanRequest, ProgressMilestone } from "@/lib/types";

function makeIntake(overrides: Partial<PlanRequest> = {}): PlanRequest {
  return {
    athlete: {
      full_name: "Test Fighter",
      technical_style: ["boxing"],
      tactical_style: ["pressure"],
    },
    fight_date: "2026-08-15",
    no_scheduled_fight: false,
    equipment_access: ["barbell", "kettlebell"],
    training_availability: ["Mon", "Tue", "Wed", "Thu", "Fri"],
    hard_sparring_days: ["Tue"],
    support_work_days: ["Thu"],
    weekly_training_frequency: 5,
    rounds_format: "3 x 3",
    key_goals: ["conditioning", "power"],
    primary_goal: "conditioning",
    weak_areas: ["repeat-effort gas"],
    primary_weak_area: "repeat-effort gas",
    injuries: "left shoulder twinge",
    ...overrides,
  };
}

function milestone(code: string, meta: Record<string, unknown> = {}): ProgressMilestone {
  return {
    code,
    label: code,
    detail: "",
    at: "2026-05-17T12:00:00Z",
    meta,
  };
}

test("buildStageOnePreview returns null when milestones are empty", () => {
  assert.equal(buildStageOnePreview(makeIntake(), []), null);
});

test("buildStageOnePreview returns null before camp_brief_built arrives", () => {
  const milestones = [
    milestone("intake_received"),
    milestone("intake_parsed", { weeks_out: 12 }),
  ];
  assert.equal(buildStageOnePreview(makeIntake(), milestones), null);
});

test("buildStageOnePreview returns null when intake is missing", () => {
  const milestones = [milestone("camp_brief_built", { camp_len: 10, phase_weeks: { GPP: 4, SPP: 4, TAPER: 2 } })];
  assert.equal(buildStageOnePreview(null, milestones), null);
});

test("buildStageOnePreview populates camp + phase split from camp_brief_built meta", () => {
  const milestones = [
    milestone("camp_brief_built", { camp_len: 10, phase_weeks: { GPP: 4, SPP: 4, TAPER: 2 } }),
  ];
  const preview = buildStageOnePreview(makeIntake(), milestones);
  assert.ok(preview);
  assert.equal(preview.camp.campWeeks, 10);
  assert.deepEqual(preview.camp.phaseWeeks, { GPP: 4, SPP: 4, TAPER: 2 });
  assert.equal(preview.camp.isOpenCamp, false);
  assert.equal(preview.camp.fightDate, "2026-08-15");
});

test("buildStageOnePreview marks open camp when no_scheduled_fight is true", () => {
  const milestones = [
    milestone("camp_brief_built", { camp_len: 8, phase_weeks: { GPP: 4, SPP: 3, TAPER: 1 } }),
  ];
  const preview = buildStageOnePreview(
    makeIntake({ no_scheduled_fight: true, fight_date: "" }),
    milestones,
  );
  assert.ok(preview);
  assert.equal(preview.camp.isOpenCamp, true);
  assert.equal(preview.camp.fightDate, "");
});

test("buildStageOnePreview never throws on malformed meta", () => {
  const milestones: ProgressMilestone[] = [
    milestone("camp_brief_built", {
      camp_len: "twelve" as unknown as number,
      phase_weeks: "bad" as unknown as Record<string, unknown>,
    }),
  ];
  assert.doesNotThrow(() => buildStageOnePreview(makeIntake(), milestones));
  assert.equal(buildStageOnePreview(makeIntake(), milestones), null);
});

test("buildStageOnePreview surfaces a triage advisory when triage_mode is not full_plan", () => {
  const milestones = [
    milestone("injury_triage_done", { triage_mode: "needs_review", parsed_injury_count: 1 }),
    milestone("camp_brief_built", { camp_len: 9, phase_weeks: { GPP: 4, SPP: 4, TAPER: 1 } }),
  ];
  const preview = buildStageOnePreview(makeIntake(), milestones);
  assert.ok(preview);
  assert.equal(preview.safetyNotes.length, 1);
  assert.equal(preview.safetyNotes[0].triageMode, "needs_review");
  assert.match(preview.safetyNotes[0].message, /coach review/i);
});

test("buildStageOnePreview hides safety notes for full_plan triage", () => {
  const milestones = [
    milestone("injury_triage_done", { triage_mode: "full_plan", parsed_injury_count: 0 }),
    milestone("camp_brief_built", { camp_len: 12, phase_weeks: { GPP: 5, SPP: 5, TAPER: 2 } }),
  ];
  const preview = buildStageOnePreview(makeIntake(), milestones);
  assert.ok(preview);
  assert.deepEqual(preview.safetyNotes, []);
});

test("buildStageOnePreview reflects intake equipment, injuries, frequency, focus", () => {
  const milestones = [
    milestone("camp_brief_built", { camp_len: 10, phase_weeks: { GPP: 4, SPP: 4, TAPER: 2 } }),
  ];
  const preview = buildStageOnePreview(makeIntake(), milestones);
  assert.ok(preview);
  assert.deepEqual(preview.restrictions.equipmentAccess, ["barbell", "kettlebell"]);
  assert.equal(preview.restrictions.injuriesText, "left shoulder twinge");
  assert.equal(preview.schedule.weeklyTrainingFrequency, 5);
  assert.equal(preview.schedule.availableDays, 5);
  assert.equal(preview.schedule.roundsFormat, "3 x 3");
  assert.equal(preview.focus.primaryGoal, "conditioning");
  assert.deepEqual(preview.focus.keyGoals, ["conditioning", "power"]);
  assert.equal(preview.focus.primaryWeakArea, "repeat-effort gas");
});

test("selectCampBrief returns null on missing milestone", () => {
  assert.equal(selectCampBrief([]), null);
  assert.equal(selectCampBrief(undefined), null);
});

test("selectCampBrief returns null when both camp_len and phase_weeks are zero", () => {
  const milestones = [milestone("camp_brief_built", { camp_len: 0, phase_weeks: { GPP: 0, SPP: 0, TAPER: 0 } })];
  assert.equal(selectCampBrief(milestones), null);
});

test("selectCampBrief uses the latest camp_brief_built entry", () => {
  const milestones = [
    milestone("camp_brief_built", { camp_len: 8, phase_weeks: { GPP: 3, SPP: 4, TAPER: 1 } }),
    milestone("camp_brief_built", { camp_len: 10, phase_weeks: { GPP: 4, SPP: 4, TAPER: 2 } }),
  ];
  const camp = selectCampBrief(milestones);
  assert.ok(camp);
  assert.equal(camp.campWeeks, 10);
});

test("selectTriage returns null with no meta", () => {
  const milestones = [milestone("injury_triage_done", {})];
  assert.equal(selectTriage(milestones), null);
});

test("selectTriage normalizes empty triage_mode to full_plan when injuries parsed", () => {
  const milestones = [milestone("injury_triage_done", { triage_mode: "", parsed_injury_count: 2 })];
  const triage = selectTriage(milestones);
  assert.ok(triage);
  assert.equal(triage.mode, "full_plan");
  assert.equal(triage.parsedInjuryCount, 2);
});
