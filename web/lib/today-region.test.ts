import test from "node:test";
import assert from "node:assert/strict";

import { getSafeSessionView } from "./today.ts";
import type { InjuryFlagRecord } from "./types.ts";

function injury(overrides: Partial<InjuryFlagRecord>): InjuryFlagRecord {
  return {
    id: "inj-1",
    athlete_id: "ath-1",
    source: "checkin",
    body_area: "",
    description: "",
    severity: "moderate",
    status: "open",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

test("safe session consumes backend regions for existing deep synonyms", () => {
  for (const [canonical_location, label, region_group] of [
    ["calf", "Soleus tear", "lower_leg_foot"],
    ["foot", "Metatarsal fracture", "lower_leg_foot"],
    ["groin", "Adductors tear", "hip_groin"],
  ] as const) {
    const view = getSafeSessionView("Technical sparring", [
      injury({
        label,
        canonical_location,
        region_group,
        body_region: "lower_limb",
        consequence: "structural",
      }),
    ]);
    assert.equal(view.allowed.includes("Light bike or walk"), false, label);
    assert.equal(
      view.allowed.includes("Seated upper-body cardio — only if pain-free and available"),
      true,
      label,
    );
  }
});

test("structured lower- and upper-limb injuries remove every cardio option", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "lower_limb", consequence: "structural", label: "Ankle fracture" }),
    injury({ id: "inj-2", body_region: "upper_limb", consequence: "structural", label: "Humerus fracture" }),
  ]);
  assert.equal(view.allowed.some((item) => item.toLowerCase().includes("cardio")), false);
});

test("trunk and neuro postures use clinician-owned rehab copy", () => {
  const trunk = getSafeSessionView("Technical sparring", [
    injury({ body_region: "trunk_spine", consequence: "structural", label: "Spinal fracture" }),
  ]);
  assert.deepEqual(trunk.allowed, ["Breathing reset", "Clinician-approved rehab"]);
  assert.equal(trunk.title, "Rest and recover");

  const neuro = getSafeSessionView("Technical sparring", [
    injury({ body_region: "head_neck", consequence: "neuro", label: "Concussion" }),
  ]);
  assert.deepEqual(neuro.allowed, [
    "Easy mobility",
    "Breathing reset",
    "Clinician-approved rehab",
  ]);
});

test("an unclassified structural injury fails closed", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "unknown", consequence: "structural", label: "Structural injury" }),
  ]);
  assert.deepEqual(view.allowed, ["Breathing reset", "Clinician-approved rehab"]);
  assert.equal(view.blocked.includes("Loaded movement"), true);
});

test("a mild load-sensitive lower-limb injury keeps light conditioning", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({
      body_region: "lower_limb",
      consequence: "load_sensitive",
      severity: "mild",
      label: "Patellar tendinopathy",
    }),
  ]);
  assert.equal(view.allowed.includes("Light bike or walk"), true);
});
