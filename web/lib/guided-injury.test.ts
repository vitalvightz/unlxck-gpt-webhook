import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAthleteInjuryText,
  buildAthleteInjuryTexts,
  buildGuidedInjuryFields,
  buildGuidedInjurySummaries,
  coerceGuidedInjuryEditState,
  EMPTY_GUIDED_INJURY,
  getInjuryMismatchContextKey,
  hasGuidedInjuryReviewRisk,
  hasMeaningfulInjuryMismatch,
  hydrateGuidedInjuryStates,
  normalizeGuidedInjuryState,
  parseGuidedInjuryState,
} from "./guided-injury.ts";

test("buildAthleteInjuryText returns only the athlete-typed area and free-text note", () => {
  const text = buildAthleteInjuryText({
    area: "Left shoulder is bruised",
    severity: "low",
    trend: "stable",
    injury_type: "surface_injury",
    surface_type: "bruise",
    impact_related: "yes",
    notes: "knocked it sparring [chest_symptoms:none]",
  });
  assert.equal(text, "Left shoulder is bruised. knocked it sparring");
});

test("buildAthleteInjuryTexts joins athlete words across injuries and skips empties", () => {
  const text = buildAthleteInjuryTexts([
    { area: "Left shoulder is bruised", severity: "low" },
    null,
    { area: "Right knee ache", notes: "[red_flags:none]" },
  ]);
  assert.equal(text, "Left shoulder is bruised. Right knee ache");
});

test("hasGuidedInjuryReviewRisk flags serious types and surface medical-safety signals", () => {
  assert.equal(hasGuidedInjuryReviewRisk({ area: "knee", injury_type: "fracture" }), true);
  assert.equal(hasGuidedInjuryReviewRisk({ area: "head", injury_type: "head_impact" }), true);
  assert.equal(
    hasGuidedInjuryReviewRisk({ injury_type: "surface_injury", surface_type: "cut", bleeding_status: "wont_stop" }),
    true,
  );
  assert.equal(
    hasGuidedInjuryReviewRisk({ injury_type: "surface_injury", surface_type: "cut", sensitive_area: "eye" }),
    true,
  );
  assert.equal(
    hasGuidedInjuryReviewRisk({ injury_type: "surface_injury", surface_type: "bruise", infection_signs: ["pus"] }),
    true,
  );
  // Routine injuries and benign surface answers should not trip the banner.
  assert.equal(hasGuidedInjuryReviewRisk({ area: "calf", injury_type: "tightness", severity: "low" }), false);
  assert.equal(
    hasGuidedInjuryReviewRisk({ injury_type: "surface_injury", surface_type: "bruise", impact_related: "yes", infection_signs: ["none"] }),
    false,
  );
});

test("guided injury state carries the body-map zone key through coerce, normalize, and hydrate", () => {
  assert.equal(coerceGuidedInjuryEditState({ zone: "l_shoulder" }).zone, "l_shoulder");
  assert.equal(normalizeGuidedInjuryState({ area: " left delt ", zone: " l_shoulder " }).zone, "l_shoulder");

  const hydrated = hydrateGuidedInjuryStates({
    guided_injuries: [{ area: "left delt, sharp when pressing", zone: "l_shoulder" }],
  });
  assert.equal(hydrated[0]?.zone, "l_shoulder");
  // The zone is internal metadata, so it must not leak into the planner-facing
  // summary or the athlete's own-words reconstruction.
  assert.ok(!buildGuidedInjurySummaries(hydrated).includes("l_shoulder"));
  assert.ok(!buildAthleteInjuryTexts(hydrated).includes("l_shoulder"));
});

// These reconcile against the current GuidedInjuryState shape: coerce / normalize
// / parse / hydrate / build all return the COMPLETE state (structured fields
// added since these tests were written), so the expected objects spread
// EMPTY_GUIDED_INJURY and override only the fields under test. The behaviour they
// assert (space handling, trimming, parsing, hydration precedence) is unchanged.
test("coerceGuidedInjuryEditState preserves spaces while typing free-text fields", () => {
  assert.deepStrictEqual(
    coerceGuidedInjuryEditState({
      area: "hip flexor ",
      severity: "moderate",
      avoid: "deep knee drive ",
      notes: "monitor after pads ",
    }),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "hip flexor ",
      severity: "moderate",
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
      ...EMPTY_GUIDED_INJURY,
      area: "hip flexor",
      severity: "moderate",
      avoid: "deep knee drive",
      notes: "monitor after pads",
    },
  );
});

test("preserves note sentences that contain periods", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Right shoulder. Notes: Range of motion limited. Follow PT exercises daily."),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "Right shoulder",
      notes: "Range of motion limited. Follow PT exercises daily",
    },
  );
});

test("merges multiple avoid phrases into the avoid field", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Left knee. Avoid: deep squats. Movements to avoid: sprinting."),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "Left knee",
      avoid: "deep squats. sprinting",
    },
  );
});

test("keeps dashed anatomical names while still parsing descriptors", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Hip flexor-iliopsoas – high, worsening. Notes: Monitor soreness."),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "Hip flexor-iliopsoas",
      severity: "high",
      trend: "worsening",
      notes: "Monitor soreness",
    },
  );
});

test("captures notes-only text that begins with Notes and includes later sentences", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Notes: Chronic inflammation. Monitor swelling after sessions."),
    {
      ...EMPTY_GUIDED_INJURY,
      notes: "Chronic inflammation. Monitor swelling after sessions",
    },
  );
});

test("normalizes mild severity alias to low", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Right knee (mild, stable)"),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "Right knee",
      severity: "low",
      trend: "stable",
    },
  );
});

test("normalizes severe severity alias to high", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Left shoulder (severe, worsening)"),
    {
      ...EMPTY_GUIDED_INJURY,
      area: "Left shoulder",
      severity: "high",
      trend: "worsening",
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
        ...EMPTY_GUIDED_INJURY,
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
      },
      {
        ...EMPTY_GUIDED_INJURY,
        area: "Right heel",
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
        ...EMPTY_GUIDED_INJURY,
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
        ...EMPTY_GUIDED_INJURY,
        area: "Left shoulder",
        severity: "moderate",
        trend: "improving",
        avoid: "heavy overhead pressing",
      },
      guided_injuries: [
        {
          ...EMPTY_GUIDED_INJURY,
          area: "Left shoulder",
          severity: "moderate",
          trend: "improving",
          avoid: "heavy overhead pressing",
        },
        {
          ...EMPTY_GUIDED_INJURY,
          area: "Right heel",
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

test("normalizeGuidedInjuryState keeps legacy fields unchanged", () => {
  const normalized = normalizeGuidedInjuryState({
    area: "Left shoulder ",
    severity: "moderate",
    trend: "improving",
    avoid: "heavy pressing ",
    notes: "monitor soreness ",
  });

  assert.equal(normalized.area, "Left shoulder");
  assert.equal(normalized.severity, "moderate");
  assert.equal(normalized.trend, "improving");
  assert.equal(normalized.avoid, "heavy pressing");
  assert.equal(normalized.notes, "monitor soreness");
});

test("hydrate/normalize preserves structured guided injury fields", () => {
  const hydrated = hydrateGuidedInjuryStates({
    guided_injuries: [
      {
        area: "Right shin",
        injury_type: "fracture",
        surface_type: "cut",
        timeframe: "last_month",
        cleared: "no",
        open_wound: "yes",
        bleeding_status: "wont_stop",
        infection_signs: ["pus", " fever "],
        impact_related: "yes",
        sensitive_area: "eye",
      },
    ],
  });

  assert.equal(hydrated[0]?.injury_type, "fracture");
  assert.equal(hydrated[0]?.surface_type, "cut");
  assert.equal(hydrated[0]?.timeframe, "last_month");
  assert.equal(hydrated[0]?.cleared, "no");
  assert.deepStrictEqual(hydrated[0]?.infection_signs, ["pus", "fever"]);
  assert.equal(hydrated[0]?.sensitive_area, "eye");
});

test("infection_signs defaults to empty array", () => {
  const normalized = normalizeGuidedInjuryState({ area: "Left knee" });
  assert.deepStrictEqual(normalized.infection_signs, []);
});

test("buildGuidedInjuryFields includes structured fields in guided payloads", () => {
  const result = buildGuidedInjuryFields([
    {
      area: "Right shin",
      injury_type: "fracture",
      bleeding_status: "wont_stop",
      infection_signs: ["pus", "fever"],
    },
  ]);

  assert.equal(result.guided_injury?.injury_type, "fracture");
  assert.equal(result.guided_injuries[0]?.bleeding_status, "wont_stop");
  assert.deepStrictEqual(result.guided_injuries[0]?.infection_signs, ["pus", "fever"]);
});

test("buildGuidedInjurySummary keeps legacy output and appends structured values", () => {
  const summary = buildGuidedInjurySummaries([
    {
      area: "Left shoulder",
      severity: "moderate",
      trend: "improving",
      injury_type: "fracture",
      surface_type: "cut",
      timeframe: "last_month",
      cleared: "no",
      bleeding_status: "wont_stop",
      infection_signs: ["pus", "fever"],
      sensitive_area: "eye",
    },
  ]);

  assert.equal(
    summary,
    "Left shoulder (moderate, improving). Type: fracture. Surface: cut. Timeframe: last_month. Cleared: no. Bleeding: wont_stop. Infection: pus, fever. Sensitive area: eye",
  );
});

test("normalize/build/hydrate retain injury_type sprain", () => {
  const normalized = normalizeGuidedInjuryState({ injury_type: "sprain" });
  assert.equal(normalized.injury_type, "sprain");
  assert.deepStrictEqual(normalized.injury_subtypes, ["sprain"]);

  const built = buildGuidedInjuryFields([{ area: "ankle", injury_type: "sprain" }]);
  assert.equal(built.guided_injury?.injury_type, "sprain");
  assert.equal(built.guided_injuries[0]?.injury_type, "sprain");

  const hydrated = hydrateGuidedInjuryStates({
    guided_injuries: [{ area: "ankle", injury_type: "sprain" }],
  });
  assert.equal(hydrated[0]?.injury_type, "sprain");
  assert.deepStrictEqual(hydrated[0]?.injury_subtypes, ["sprain"]);
});

test("normalizeGuidedInjuryState infers surface primary subtype key when subtype list is empty", () => {
  const normalized = normalizeGuidedInjuryState({
    injury_type: "surface_injury",
    surface_type: "blister",
    injury_subtypes: [],
  });
  assert.deepStrictEqual(normalized.injury_subtypes, ["surface_injury:blister"]);
});

test("normalizeGuidedInjuryState promotes a single selected subtype to primary type", () => {
  const normalized = normalizeGuidedInjuryState({
    injury_type: "pain",
    injury_subtypes: ["sprain"],
  });
  assert.equal(normalized.injury_type, "sprain");
  assert.deepStrictEqual(normalized.injury_subtypes, ["sprain"]);
});

test("normalizeGuidedInjuryState promotes a single selected surface subtype", () => {
  const normalized = normalizeGuidedInjuryState({
    injury_type: "pain",
    surface_type: "cut",
    injury_subtypes: ["surface_injury:blister"],
  });
  assert.equal(normalized.injury_type, "surface_injury");
  assert.equal(normalized.surface_type, "blister");
});

test("normalizeGuidedInjuryState keeps explicit primary type when multiple subtypes are selected", () => {
  const normalized = normalizeGuidedInjuryState({
    injury_type: "pain",
    injury_subtypes: ["pain", "instability", "tightness"],
  });
  assert.equal(normalized.injury_type, "pain");
  assert.deepStrictEqual(normalized.injury_subtypes, ["pain", "instability", "tightness"]);
});

test("normalizeGuidedInjuryState keeps skin_irritation subtype key for backend mapping", () => {
  const normalized = normalizeGuidedInjuryState({
    injury_type: "surface_injury",
    surface_type: "skin_irritation",
    injury_subtypes: ["surface_injury:skin_irritation"],
  });
  assert.equal(normalized.injury_type, "surface_injury");
  assert.equal(normalized.surface_type, "skin_irritation");
});
