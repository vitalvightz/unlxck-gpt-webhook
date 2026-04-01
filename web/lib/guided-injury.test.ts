import assert from "node:assert/strict";
import test from "node:test";

import { hasMeaningfulInjuryMismatch, parseGuidedInjuryState } from "./guided-injury.ts";

test("preserves note sentences that contain periods", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Right shoulder. Notes: Range of motion limited. Follow PT exercises daily."),
    {
      area: "Right shoulder",
      severity: "",
      trend: "",
      avoid: "",
      notes: "Range of motion limited. Follow PT exercises daily",
    },
  );
});

test("merges multiple avoid phrases into the avoid field", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Left knee. Avoid: deep squats. Movements to avoid: sprinting."),
    {
      area: "Left knee",
      severity: "",
      trend: "",
      avoid: "deep squats. sprinting",
      notes: "",
    },
  );
});

test("keeps dashed anatomical names while still parsing descriptors", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Hip flexor-iliopsoas – high, worsening. Notes: Monitor soreness."),
    {
      area: "Hip flexor-iliopsoas",
      severity: "high",
      trend: "worsening",
      avoid: "",
      notes: "Monitor soreness",
    },
  );
});

test("captures notes-only text that begins with Notes and includes later sentences", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Notes: Chronic inflammation. Monitor swelling after sessions."),
    {
      area: "",
      severity: "",
      trend: "",
      avoid: "",
      notes: "Chronic inflammation. Monitor swelling after sessions",
    },
  );
});

test("normalizes mild severity alias to low", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Right knee (mild, stable)"),
    {
      area: "Right knee",
      severity: "low",
      trend: "stable",
      avoid: "",
      notes: "",
    },
  );
});

test("normalizes severe severity alias to high", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Left shoulder (severe, worsening)"),
    {
      area: "Left shoulder",
      severity: "high",
      trend: "worsening",
      avoid: "",
      notes: "",
    },
  );
});

// ─── hasMeaningfulInjuryMismatch ─────────────────────────────────────────────

test("hasMeaningfulInjuryMismatch: identical strings do not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("Right shoulder. Avoid: deep squats.", "Right shoulder. Avoid: deep squats."), false);
});

test("hasMeaningfulInjuryMismatch: capitalisation-only change does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("Shoulder Injury", "shoulder injury"), false);
});

test("hasMeaningfulInjuryMismatch: punctuation-only change does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("shoulder injury.", "shoulder injury"), false);
});

test("hasMeaningfulInjuryMismatch: Avoid label formatting does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("avoid deep squats", "Avoid: deep squats"), false);
});

test("hasMeaningfulInjuryMismatch: Notes label formatting does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("monitor swelling", "Notes: monitor swelling"), false);
});

test("hasMeaningfulInjuryMismatch: parenthetical descriptor formatting does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("right shoulder, low, stable", "right shoulder (low, stable)"), false);
});

test("hasMeaningfulInjuryMismatch: empty original does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("", "Right shoulder. Avoid: deep squats."), false);
});

test("hasMeaningfulInjuryMismatch: empty generated does not mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("Right shoulder.", ""), false);
});

test("hasMeaningfulInjuryMismatch: dropped surgery history triggers mismatch", () => {
  assert.equal(
    hasMeaningfulInjuryMismatch(
      "Right shoulder surgery history. Avoid: deep squats.",
      "Right shoulder. Avoid: deep squats.",
    ),
    true,
  );
});

test("hasMeaningfulInjuryMismatch: dropped trigger context triggers mismatch", () => {
  assert.equal(
    hasMeaningfulInjuryMismatch(
      "Right shoulder. Avoid: training after sparring.",
      "Right shoulder. Avoid: training.",
    ),
    true,
  );
});

test("hasMeaningfulInjuryMismatch: dropped after-sparring qualifier triggers mismatch", () => {
  assert.equal(hasMeaningfulInjuryMismatch("avoid training after sparring", "Avoid: training"), true);
});

test("hasMeaningfulInjuryMismatch: dropped monitor-swelling note triggers mismatch", () => {
  assert.equal(
    hasMeaningfulInjuryMismatch(
      "Right shoulder. Notes: Monitor swelling.",
      "Right shoulder.",
    ),
    true,
  );
});
