import test from "node:test";
import assert from "node:assert/strict";

import { applyNoScheduledFightSnapshot, emptyPlanRequest, hydratePlanRequest } from "@/lib/onboarding";

test("hydratePlanRequest clears fight_date when partial draft marks open camp", () => {
  const latest = {
    ...emptyPlanRequest("Athlete"),
    fight_date: "2026-09-20",
    no_scheduled_fight: false,
  };

  const me = {
    profile: {
      full_name: "Athlete",
      technical_style: [],
      tactical_style: [],
      stance: "",
      professional_status: "",
      record: "",
      athlete_timezone: "UTC",
      nutrition_profile: null,
      onboarding_draft: {
        no_scheduled_fight: true,
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.equal(hydrated.no_scheduled_fight, true);
  assert.equal(hydrated.fight_date, "");
});

test("applyNoScheduledFightSnapshot(true) clears fight_date and sets open camp", () => {
  const form = {
    ...emptyPlanRequest("Athlete"),
    fight_date: "2026-10-10",
    no_scheduled_fight: false,
  };

  const next = applyNoScheduledFightSnapshot(form, true);
  assert.equal(next.no_scheduled_fight, true);
  assert.equal(next.fight_date, "");
});

test("applyNoScheduledFightSnapshot(false) preserves fight_date and clears open camp", () => {
  const form = {
    ...emptyPlanRequest("Athlete"),
    fight_date: "2026-10-10",
    no_scheduled_fight: true,
  };

  const next = applyNoScheduledFightSnapshot(form, false);
  assert.equal(next.no_scheduled_fight, false);
  assert.equal(next.fight_date, "2026-10-10");
});
