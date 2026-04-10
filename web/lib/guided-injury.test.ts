import assert from "node:assert/strict";
import test from "node:test";

import {
  buildGuidedInjuryFields,
  buildGuidedInjurySummaries,
  coerceGuidedInjuryEditState,
  getInjuryMismatchContextKey,
  hasMeaningfulInjuryMismatch,
  hydrateGuidedInjuryStates,
  normalizeGuidedInjuryState,
  parseGuidedInjuryState,
} from "./guided-injury.ts";

test("coerceGuidedInjuryEditState preserves spaces while typing free-text fields", () => {
  assert.deepStrictEqual(
    coerceGuidedInjuryEditState({
      area: "hip flexor ",
      severity: "moderate",
      avoid: "deep knee drive ",
      notes: "monitor after pads ",
    }),
    {
      area: "hip flexor ",
      severity: "moderate",
      trend: "",
      avoid: "deep knee drive ",
      notes: "monitor after pads ",
    },
  );
});

test("normalizeGuidedInjuryState still trims persisted free-text values", () => {
  assert.deepStrictEqual(
    normalizeGuidedInjuryState({
      area: "hip flexor ",
      severity: "moderate",
      avoid: "deep knee drive ",
      notes: "monitor after pads ",
    }),
    {
      area: "hip flexor",
      severity: "moderate",
      trend: "",
      avoid: "deep knee drive",
      notes: "monitor after pads",
    },
  );
});

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

test("buildGuidedInjurySummaries joins multiple injury cards in order", () => {
  assert.equal(
    buildGuidedInjurySummaries([
      {
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "heavy overhead pressing",
        notes: "",
      },
      {
        area: "Right heel",
        severity: "low",
        trend: "stable",
        avoid: "roadwork",
        notes: "flairs up after long runs",
      },
    ]),
    "Left shoulder (moderate, improving). Avoid: heavy overhead pressing. Right heel (low, stable). Avoid: roadwork. Notes: flairs up after long runs",
  );
});

test("hydrateGuidedInjuryStates prefers guided_injuries over legacy injury fields", () => {
  assert.deepStrictEqual(
    hydrateGuidedInjuryStates({
      injuries: "legacy shoulder note",
      guided_injury: {
        area: "Legacy shoulder",
        severity: "moderate",
      },
      guided_injuries: [
        {
          area: "Left shoulder",
          severity: "moderate",
          trend: "improving",
        },
        {
          area: "Right heel",
          notes: "tight after skipping rope",
        },
      ],
    }),
    [
      {
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "",
        notes: "",
      },
      {
        area: "Right heel",
        severity: "",
        trend: "",
        avoid: "",
        notes: "tight after skipping rope",
      },
    ],
  );
});

test("hydrateGuidedInjuryStates falls back to parsing legacy injuries text", () => {
  assert.deepStrictEqual(
    hydrateGuidedInjuryStates({
      injuries: "Left shoulder (moderate, improving). Avoid: heavy overhead pressing. Notes: surgery history.",
    }),
    [
      {
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "heavy overhead pressing",
        notes: "surgery history",
      },
    ],
  );
});

test("buildGuidedInjuryFields mirrors the first card into legacy guided_injury", () => {
  assert.deepStrictEqual(
    buildGuidedInjuryFields([
      {
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "heavy overhead pressing",
        notes: "",
      },
      {
        area: "Right heel",
        severity: "",
        trend: "",
        avoid: "",
        notes: "tight after roadwork",
      },
    ]),
    {
      injuries: "Left shoulder (moderate, improving). Avoid: heavy overhead pressing. Right heel. Notes: tight after roadwork",
      guided_injury: {
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "heavy overhead pressing",
        notes: "",
      },
      guided_injuries: [
        {
          area: "Left shoulder",
          severity: "moderate",
          trend: "improving",
          avoid: "heavy overhead pressing",
          notes: "",
        },
        {
          area: "Right heel",
          severity: "",
          trend: "",
          avoid: "",
          notes: "tight after roadwork",
        },
      ],
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

test("hasMeaningfulInjuryMismatch: empty generated mismatches when original note exists", () => {
  assert.equal(hasMeaningfulInjuryMismatch("Right shoulder.", ""), true);
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

test("getInjuryMismatchContextKey: formatting-only changes keep the same mismatch context", () => {
  assert.equal(
    getInjuryMismatchContextKey(
      "Right shoulder surgery history. avoid deep squats.",
      "Right shoulder. Avoid: deep squats.",
    ),
    getInjuryMismatchContextKey(
      "right shoulder surgery history. Avoid: deep squats",
      "Right shoulder. avoid deep squats",
    ),
  );
});

test("getInjuryMismatchContextKey: generated summary edits change the mismatch context", () => {
  assert.notEqual(
    getInjuryMismatchContextKey(
      "Right shoulder surgery history. Avoid: deep squats.",
      "Right shoulder. Avoid: deep squats.",
    ),
    getInjuryMismatchContextKey(
      "Right shoulder surgery history. Avoid: deep squats.",
      "Right shoulder. Avoid: training after sparring.",
    ),
  );
});
