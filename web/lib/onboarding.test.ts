import assert from "node:assert/strict";
import test from "node:test";

import { hydratePlanRequest } from "./onboarding.ts";
import type { MeResponse, PlanRequest } from "./types";

function makePlan(overrides: Partial<PlanRequest>): PlanRequest {
  return {
    athlete: {
      full_name: "Test",
      sex: null,
      age: null,
      weight_kg: null,
      target_weight_kg: null,
      height_cm: null,
      technical_style: ["boxer"],
      tactical_style: [],
      stance: "orthodox",
      professional_status: "amateur",
      record: "",
      athlete_timezone: "UTC",
      athlete_locale: "",
    },
    fight_date: "",
    no_scheduled_fight: false,
    rounds_format: "3 x 3",
    weekly_training_frequency: 4,
    fatigue_level: "moderate",
    equipment_access: [],
    training_availability: [],
    hard_sparring_days: [],
    support_work_days: [],
    injuries: "",
    guided_injury: null,
    guided_injuries: [],
    key_goals: [],
    primary_goal: "",
    weak_areas: [],
    primary_weak_area: "",
    goal_weakness_collision_detail: "",
    goal_weakness_collision_tags: [],
    goal_weakness_collision_details: [],
    training_preference: "",
    mindset_challenges: "",
    notes: "",
    ...overrides,
  };
}

function makeMe(latest: PlanRequest, draft: PlanRequest): MeResponse {
  return {
    profile: {
      athlete_id: "a1",
      email: "a@a.com",
      full_name: "Test",
      role: "athlete",
      technical_style: [],
      tactical_style: [],
      stance: "",
      professional_status: "",
      record: "",
      onboarding_draft: draft,
      nutrition_profile: null,
      athlete_timezone: "UTC",
      appearance_mode: "dark",
    },
    latest_intake: latest,
    latest_plan: null,
  } as MeResponse;
}

test("hydratePlanRequest clears fight_date for open camp drafts", () => {
  const latest = makePlan({ fight_date: "2030-01-01", no_scheduled_fight: false });
  const draft = makePlan({ fight_date: "", no_scheduled_fight: true });

  const result = hydratePlanRequest(makeMe(latest, draft));

  assert.equal(result.fight_date, "");
  assert.equal(result.no_scheduled_fight, true);
});

test("hydratePlanRequest preserves scheduled fight date", () => {
  const latest = makePlan({ fight_date: "2030-01-01", no_scheduled_fight: false });
  const draft = makePlan({ fight_date: "2031-02-02", no_scheduled_fight: false });

  const result = hydratePlanRequest(makeMe(latest, draft));

  assert.equal(result.fight_date, "2031-02-02");
  assert.equal(result.no_scheduled_fight, false);
});
