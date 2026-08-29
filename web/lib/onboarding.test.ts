import test from "node:test";
import assert from "node:assert/strict";

import { applyNoScheduledFightSnapshot, canonicalizePerformanceFocus, emptyPlanRequest, hydratePlanRequest } from "@/lib/onboarding";

test("a fresh intake does not preselect a recovery profile", () => {
  assert.equal(emptyPlanRequest("Athlete").fatigue_level, undefined);
});

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

test("hydratePlanRequest respects a draft that clears support_work_days", () => {
  // The previous intake locked in Wednesday as a support-work day. The athlete
  // then removed it in the draft, so hydration must NOT resurrect it from
  // latest_intake — otherwise the cleared day silently comes back and the
  // backend rejects generation (support_work_days ⊄ training_availability).
  const latest = {
    ...emptyPlanRequest("Athlete"),
    training_availability: ["monday", "tuesday", "wednesday"],
    support_work_days: ["wednesday"],
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
        training_availability: ["monday", "tuesday"],
        support_work_days: [],
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.deepEqual(hydrated.training_availability, ["monday", "tuesday"]);
  assert.deepEqual(hydrated.support_work_days, []);
});

test("hydratePlanRequest prunes coupled day fields to draft availability", () => {
  // Availability shrank in the draft but the coupled day picks still reference a
  // dropped day. Hydration must prune them so the payload can never reach the
  // backend with a day outside training_availability.
  const latest = {
    ...emptyPlanRequest("Athlete"),
    training_availability: ["monday", "tuesday", "wednesday"],
    hard_sparring_days: ["wednesday"],
    support_work_days: ["tuesday"],
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
        training_availability: ["monday", "tuesday"],
        hard_sparring_days: ["wednesday"],
        support_work_days: ["tuesday"],
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.deepEqual(hydrated.training_availability, ["monday", "tuesday"]);
  assert.deepEqual(hydrated.hard_sparring_days, []);
  assert.deepEqual(hydrated.support_work_days, ["tuesday"]);
});

test("hydratePlanRequest backfills coupled day fields a partial draft never saved", () => {
  // The draft set availability but never reached the sparring step, so its
  // day fields are absent (undefined). Hydration must keep the previous
  // intake's value (pruned to the new availability), not clobber it with [].
  const latest = {
    ...emptyPlanRequest("Athlete"),
    training_availability: ["monday", "tuesday", "wednesday"],
    hard_sparring_days: ["monday"],
    support_work_days: ["wednesday"],
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
        training_availability: ["monday", "tuesday"],
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.deepEqual(hydrated.training_availability, ["monday", "tuesday"]);
  // monday is still available -> retained; wednesday dropped from availability -> pruned.
  assert.deepEqual(hydrated.hard_sparring_days, ["monday"]);
  assert.deepEqual(hydrated.support_work_days, []);
});

test("hydratePlanRequest uses quick build draft as source of truth", () => {
  const latest = {
    ...emptyPlanRequest("Athlete"),
    key_goals: ["power", "conditioning"],
    weak_areas: ["gas_tank"],
    training_availability: ["monday", "wednesday", "friday", "saturday"],
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
        ...emptyPlanRequest("Athlete"),
        plan_source: "quick_build",
        technical_style: ["boxing"],
        key_goals: ["speed"],
        weak_areas: [],
        training_availability: ["tuesday", "thursday"],
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.deepEqual(hydrated.key_goals, ["speed"]);
  assert.deepEqual(hydrated.training_availability, ["tuesday", "thursday"]);
});

test("hydratePlanRequest treats empty draft fields as intentional clears", () => {
  const latest = {
    ...emptyPlanRequest("Athlete"),
    equipment_access: ["barbell", "heavy_bag"],
    key_goals: ["conditioning", "speed"],
    weak_areas: ["gas_tank"],
    injuries: "Old shoulder issue",
    training_preference: "Old preference",
    athlete: {
      ...emptyPlanRequest("Athlete").athlete,
      tactical_style: ["pressure_fighter"],
      stance: "orthodox",
      record: "5-1",
    },
  };

  const me = {
    profile: {
      full_name: "Athlete",
      technical_style: ["boxing"],
      tactical_style: ["pressure_fighter"],
      stance: "orthodox",
      professional_status: "amateur",
      record: "5-1",
      athlete_timezone: "UTC",
      nutrition_profile: null,
      onboarding_draft: {
        ...emptyPlanRequest("Athlete"),
        equipment_access: [],
        key_goals: ["speed"],
        weak_areas: [],
        injuries: "",
        training_preference: "",
        athlete: {
          ...emptyPlanRequest("Athlete").athlete,
          full_name: "Athlete",
          technical_style: ["boxing"],
          tactical_style: [],
          stance: "",
          record: "",
          athlete_timezone: "UTC",
        },
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);

  assert.deepEqual(hydrated.equipment_access, []);
  assert.deepEqual(hydrated.key_goals, ["speed"]);
  assert.deepEqual(hydrated.weak_areas, []);
  assert.equal(hydrated.injuries, "");
  assert.equal(hydrated.training_preference, "");
  assert.deepEqual(hydrated.athlete.tactical_style, []);
  assert.equal(hydrated.athlete.stance, "");
  assert.equal(hydrated.athlete.record, "");
});

test("hydratePlanRequest lets current draft override stale latest intake focus fields", () => {
  const latest = {
    ...emptyPlanRequest("Athlete"),
    key_goals: ["speed"],
    primary_goal: "speed",
    fatigue_level: "moderate",
    weak_areas: ["conditioning"],
    primary_weak_area: "conditioning",
    athlete: {
      ...emptyPlanRequest("Athlete").athlete,
      professional_status: "professional",
    },
  };

  const me = {
    profile: {
      full_name: "Athlete",
      technical_style: [],
      tactical_style: [],
      stance: "",
      professional_status: "professional",
      record: "",
      athlete_timezone: "UTC",
      nutrition_profile: null,
      onboarding_draft: {
        key_goals: ["strength", "mobility"],
        primary_goal: "strength",
        fatigue_level: "low",
        weak_areas: ["footwork"],
        primary_weak_area: "footwork",
        athlete: {
          professional_status: "amateur",
        },
      },
    },
    latest_intake: latest,
  } as any;

  const hydrated = hydratePlanRequest(me);
  assert.deepEqual(hydrated.key_goals, ["strength", "mobility"]);
  assert.equal(hydrated.primary_goal, "strength");
  assert.equal(hydrated.fatigue_level, "low");
  assert.equal(hydrated.athlete.professional_status, "amateur");
  assert.deepEqual(hydrated.weak_areas, ["footwork"]);
  assert.equal(hydrated.primary_weak_area, "footwork");
});

test("canonicalizePerformanceFocus sets the only selected goal as primary", () => {
  const canonical = canonicalizePerformanceFocus({
    ...emptyPlanRequest("Athlete"),
    key_goals: ["strength"],
    primary_goal: "speed",
  });

  assert.equal(canonical.primary_goal, "strength");
});

test("canonicalizePerformanceFocus preserves a valid primary among multiple goals", () => {
  const canonical = canonicalizePerformanceFocus({
    ...emptyPlanRequest("Athlete"),
    key_goals: ["strength", "mobility"],
    primary_goal: "mobility",
  });

  assert.equal(canonical.primary_goal, "mobility");
});

test("canonicalizePerformanceFocus corrects invalid primary weak area", () => {
  const canonical = canonicalizePerformanceFocus({
    ...emptyPlanRequest("Athlete"),
    weak_areas: ["footwork"],
    primary_weak_area: "conditioning",
  });

  assert.equal(canonical.primary_weak_area, "footwork");
});
