import test from "node:test";
import assert from "node:assert/strict";

import { getSafeSessionView } from "./today.ts";
import type { InjuryFlagRecord } from "./types.ts";

// These fixtures intentionally provide backend-classified anatomy. Today must
// consume these fields directly rather than rebuilding the injury synonym map.
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

test("safe session trusts the backend-supplied lower-limb region", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({
      label: "Soleus tear",
      canonical_location: "calf",
      region_group: "lower_leg_foot",
      body_region: "lower_limb",
      consequence: "structural",
    }),
  ]);
  assert.equal(view.allowed.includes("Light bike or walk"), false);
  assert.equal(
    view.allowed.includes("Seated upper-body cardio — only if pain-free and available"),
    true,
  );
});

test("structured lower- and upper-limb injuries remove every cardio option", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "lower_limb", consequence: "structural", label: "Ankle fracture" }),
    injury({ id: "inj-2", body_region: "upper_limb", consequence: "structural", label: "Humerus fracture" }),
  ]);
  assert.equal(view.allowed.some((item) => item.toLowerCase().includes("cardio")), false);
});

test("an upper-limb structural injury keeps leg-safe conditioning", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "upper_limb", consequence: "structural", label: "Humerus fracture" }),
  ]);
  assert.equal(view.allowed.includes("Light bike or walk"), true);
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

test("an active injury with missing classification fails closed", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "unknown", consequence: null, label: "Unclassified injury" }),
  ]);
  assert.deepEqual(view.allowed, ["Breathing reset", "Clinician-approved rehab"]);
});

test("a severe lower-limb injury blocks gait without a structural consequence", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "lower_limb", consequence: "load_sensitive", severity: "severe" }),
  ]);
  assert.equal(view.allowed.includes("Light bike or walk"), false);
});

test("an upper-limb nerve injury does not trigger head-injury downregulation", () => {
  const view = getSafeSessionView("Technical sparring", [
    injury({ body_region: "upper_limb", consequence: "neuro", label: "Arm nerve injury" }),
  ]);
  assert.equal(view.allowed.includes("Light bike or walk"), true);
  assert.equal(view.allowed.includes("Gentle activation"), true);
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
