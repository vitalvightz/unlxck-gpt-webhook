import assert from "node:assert/strict";
import test from "node:test";

import { applyNoScheduledFightSnapshot } from "./plan-intake-form.tsx";
import { emptyPlanRequest } from "../lib/onboarding.ts";

test("noScheduledFight snapshot forces empty fight_date", () => {
  const form = {
    ...emptyPlanRequest("Test"),
    fight_date: "2030-01-01",
    no_scheduled_fight: false,
  };

  const result = applyNoScheduledFightSnapshot(form, true);

  assert.equal(result.fight_date, "");
  assert.equal(result.no_scheduled_fight, true);
});
