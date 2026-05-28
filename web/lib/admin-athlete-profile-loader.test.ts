import assert from "node:assert/strict";
import test from "node:test";

import { loadAdminAthleteProfileData } from "./admin-athlete-profile-loader.ts";

test("athlete profile loads when nutrition endpoint fails", async () => {
  const profile = await loadAdminAthleteProfileData({
    getAdminAthlete: async () => ({ athlete_id: "athlete-1" } as never),
    getAdminAthleteNutritionCurrent: async () => {
      throw new Error("nutrition down");
    },
    getAdminAthleteGenerationJobs: async () => [{ job_id: "job-1" } as never],
  });

  assert.equal(profile.athlete.athlete_id, "athlete-1");
  assert.equal(profile.nutrition, null);
  assert.equal(profile.nutritionWarning, "Nutrition workspace could not be loaded.");
  assert.equal(profile.jobs.length, 1);
  assert.equal(profile.plans.length, 0);
});

test("athlete profile loads when generation jobs endpoint fails", async () => {
  const profile = await loadAdminAthleteProfileData({
    getAdminAthlete: async () => ({ athlete_id: "athlete-1" } as never),
    getAdminAthleteNutritionCurrent: async () => ({ source: "intake" } as never),
    getAdminAthleteGenerationJobs: async () => {
      throw new Error("jobs down");
    },
  });

  assert.equal(profile.athlete.athlete_id, "athlete-1");
  assert.equal(profile.jobs.length, 0);
  assert.equal(profile.jobsWarning, "Generation diagnostics could not be loaded.");
  assert.equal(profile.nutritionWarning, null);
  assert.equal(profile.plansWarning, null);
});

test("full-page error path only triggers when core athlete load fails", async () => {
  await assert.rejects(
    loadAdminAthleteProfileData({
      getAdminAthlete: async () => {
        throw new Error("core failed");
      },
      getAdminAthleteNutritionCurrent: async () => ({ source: "intake" } as never),
      getAdminAthleteGenerationJobs: async () => [],
    }),
    /core failed/,
  );
});

test("athlete profile filters admin plan history to the selected athlete", async () => {
  const profile = await loadAdminAthleteProfileData({
    getAdminAthlete: async () => ({ athlete_id: "athlete-1" } as never),
    getAdminAthleteNutritionCurrent: async () => ({ source: "intake" } as never),
    getAdminAthleteGenerationJobs: async () => [],
    listAdminPlans: async () => [
      { plan_id: "plan-1", athlete_id: "athlete-1" },
      { plan_id: "plan-2", athlete_id: "athlete-2" },
    ] as never,
  });

  assert.deepEqual(
    profile.plans.map((plan) => plan.plan_id),
    ["plan-1"],
  );
});

test("athlete profile still loads when plan history fails", async () => {
  const profile = await loadAdminAthleteProfileData({
    getAdminAthlete: async () => ({ athlete_id: "athlete-1" } as never),
    getAdminAthleteNutritionCurrent: async () => ({ source: "intake" } as never),
    getAdminAthleteGenerationJobs: async () => [],
    listAdminPlans: async () => {
      throw new Error("plans down");
    },
  });

  assert.equal(profile.plans.length, 0);
  assert.equal(profile.plansWarning, "Plan history could not be loaded.");
});
