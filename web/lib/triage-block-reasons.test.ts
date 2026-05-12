import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBlockedInjuryContextSummary,
  buildCapturedInjuryDetail,
  summarizeBlockedInjuryContext,
} from "./triage-block-reasons.ts";

test("summarizeBlockedInjuryContext returns captured injury for structured injury only", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
    guidedInjuries: [{ area: "Left ankle", surface_type: "bruise", severity: "moderate", trend: "stable", impact_related: "yes" }],
  });

  assert.equal(summary, "Captured injury: Left ankle — Bruise / contusion · Moderate · Stable · Impact-related");
});

test("summarizeBlockedInjuryContext puts captured injury before triage reason", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: {
      red_flags: [],
      matched_high_risk_categories: [],
      reasons: ["Moderate stable injury did not meet the strict allowlist for automatic full planning."],
    },
    guidedInjuries: [
      { area: "Left ankle", surface_type: "bruise", severity: "moderate", trend: "stable", impact_related: "yes" },
    ],
  });

  assert.equal(
    summary,
    "Captured injury: Left ankle — Bruise / contusion · Moderate · Stable · Impact-related · Blocked trigger: Moderate stable injury did not meet the strict allowlist for automatic full planning.",
  );
});

test("summarizeBlockedInjuryContext shows captured injury before blocked trigger when safety signal exists", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: ["loss_of_consciousness"], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Head", injury_type: "concussion", severity: "high" }],
  });

  assert.equal(summary, "Captured injury: Head — Concussion · High · Blocked trigger: Loss of consciousness");
});

test("summarizeBlockedInjuryContext prioritises red flags over high-risk labels inside blocked trigger", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: {
      red_flags: ["loss_of_consciousness"],
      urgent_flags: [],
      matched_high_risk_categories: ["moderate_stable_injury", "strict_allowlist_failed"],
    },
    guidedInjuries: [{ area: "Head", injury_type: "concussion", severity: "high" }],
  });

  assert.equal(
    summary,
    "Captured injury: Head — Concussion · High · Blocked trigger: Loss of consciousness + Moderate stable injury",
  );
});

test("summarizeBlockedInjuryContext does not treat area-only guided injury as captured when notes infer a symptom", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Right shoulder", notes: "Feels unstable and keeps giving way" }],
  });

  assert.equal(summary, "Blocked trigger: Instability + Right shoulder");
});

test("summarizeBlockedInjuryContext maps skin_irritation surface type", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Head", surface_type: "skin_irritation" }],
  });

  assert.equal(summary, "Captured injury: Head — Burn / skin irritation");
});

test("summarizeBlockedInjuryContext maps skin_irritation surface type with severity and trend", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [
      { area: "Forearm", injury_type: "surface_injury", surface_type: "skin_irritation", severity: "low", trend: "stable" },
    ],
  });

  assert.equal(summary, "Captured injury: Forearm — Burn / skin irritation · Low · Stable");
});

test("summarizeBlockedInjuryContext prioritises red flags in fallback when no captured injury exists", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: {
      red_flags: ["loss_of_consciousness"],
      matched_high_risk_categories: ["moderate_stable_injury"],
    },
  });
  assert.equal(summary, "Blocked trigger: Loss of consciousness + Moderate stable injury");
});

test("summarizeBlockedInjuryContext keeps fallback when guided injury is absent", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: ["moderate_stable_injury"], reasons: ["did not meet strict allowlist"] },
    injuriesText: "left ankle rolled in sparring",
  });

  assert.equal(summary, "Blocked trigger: Moderate stable injury + did not meet strict allowlist");
});

test("buildBlockedInjuryContextSummary returns structured fields with captured injury and trigger", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: { red_flags: ["loss_of_consciousness"], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Head", injury_type: "concussion", severity: "high" }],
  });

  assert.deepEqual(summary, {
    capturedInjury: "Head — Concussion · High",
    blockedTrigger: "Loss of consciousness",
    capturedInjuries: [
      { headline: "Head — Concussion", meta: ["High severity"], flags: [] },
    ],
  });
});

test("buildBlockedInjuryContextSummary returns only blockedTrigger when guided context is absent", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: { red_flags: [], matched_high_risk_categories: ["moderate_stable_injury"] },
  });

  assert.deepEqual(summary, { blockedTrigger: "Moderate stable injury" });
});

test("buildBlockedInjuryContextSummary returns only capturedInjury when no safety signals exist", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [
      { area: "Left ankle", surface_type: "bruise", severity: "moderate", trend: "stable", impact_related: "yes" },
    ],
  });

  assert.deepEqual(summary, {
    capturedInjury: "Left ankle — Bruise / contusion · Moderate · Stable · Impact-related",
    capturedInjuries: [
      {
        headline: "Left ankle — Bruise / contusion",
        meta: ["Moderate severity", "Trend: Stable", "Impact-related"],
        flags: [],
      },
    ],
  });
});

test("buildCapturedInjuryDetail returns headline and full meta for a populated injury", () => {
  const detail = buildCapturedInjuryDetail({
    area: "Left ankle",
    surface_type: "bruise",
    severity: "moderate",
    trend: "stable",
    impact_related: "yes",
    timeframe: "within_2_weeks",
    notes: "Swells after sparring rounds.",
    avoid: "Heavy kicks and lateral cuts.",
  });

  assert.deepEqual(detail, {
    headline: "Left ankle — Bruise / contusion",
    meta: ["Moderate severity", "Trend: Stable", "Impact-related", "Onset: Within 2 weeks"],
    flags: [],
    notes: "Swells after sparring rounds.",
    avoid: "Heavy kicks and lateral cuts.",
  });
});

test("buildCapturedInjuryDetail keeps headline when only area is set", () => {
  const detail = buildCapturedInjuryDetail({ area: "Right shoulder" });
  assert.deepEqual(detail, {
    headline: "Right shoulder",
    meta: [],
    flags: [],
  });
});

test("buildCapturedInjuryDetail surfaces wound and clearance flags", () => {
  const detail = buildCapturedInjuryDetail({
    area: "Eyebrow",
    surface_type: "laceration",
    open_wound: "yes",
    bleeding_status: "active",
    infection_signs: ["redness", "warmth"],
    sensitive_area: "yes",
    cleared: "no",
  });

  assert.deepEqual(detail, {
    headline: "Eyebrow — Laceration / deep cut",
    meta: [],
    flags: [
      "Open wound",
      "Bleeding: Active",
      "Infection signs: Redness, Warmth",
      "Sensitive area",
      "Not yet medically cleared",
    ],
  });
});

test("buildCapturedInjuryDetail returns null when neither area nor type is provided", () => {
  const detail = buildCapturedInjuryDetail({});
  assert.equal(detail, null);
});

test("buildBlockedInjuryContextSummary populates capturedInjuries for every guided injury in order", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [
      { area: "Left ankle", surface_type: "bruise", severity: "moderate" },
      { area: "Right shoulder", injury_type: "strain", trend: "worsening" },
    ],
  });

  assert.deepEqual(summary.capturedInjuries, [
    {
      headline: "Left ankle — Bruise / contusion",
      meta: ["Moderate severity"],
      flags: [],
    },
    {
      headline: "Right shoulder — Strain",
      meta: ["Trend: Worsening"],
      flags: [],
    },
  ]);
});

test("buildBlockedInjuryContextSummary returns pauseReasons verbatim and deduped", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: {
      red_flags: [],
      matched_high_risk_categories: [],
      reasons: [
        "Moderate stable injury did not meet the strict allowlist for automatic full planning.",
        "  Moderate stable injury did not meet the strict allowlist for automatic full planning.  ",
        "Coach/admin review is required before normal plan generation.",
      ],
    },
  });

  assert.deepEqual(summary.pauseReasons, [
    "Moderate stable injury did not meet the strict allowlist for automatic full planning.",
    "Coach/admin review is required before normal plan generation.",
  ]);
});

test("buildBlockedInjuryContextSummary keeps capturedInjury alongside capturedInjuries so the visible line is never dropped", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: {
      red_flags: [],
      matched_high_risk_categories: ["moderate_stable_injury"],
      reasons: ["Moderate stable injury did not meet the strict allowlist for automatic full planning."],
    },
    guidedInjuries: [
      {
        area: "Left ankle",
        surface_type: "bruise",
        severity: "moderate",
        trend: "stable",
        impact_related: "yes",
        notes: "Swells after sparring",
      },
    ],
  });

  assert.equal(
    summary.capturedInjury,
    "Left ankle — Bruise / contusion · Moderate · Stable · Impact-related",
    "single-line capturedInjury must remain populated so the always-visible line renders",
  );
  assert.equal(summary.capturedInjuries?.length, 1);
  assert.equal(typeof summary.blockedTrigger, "string");
  assert.ok(
    (summary.blockedTrigger ?? "").length > 0,
    "blockedTrigger must remain populated so the always-visible line renders",
  );
  assert.deepEqual(summary.pauseReasons, [
    "Moderate stable injury did not meet the strict allowlist for automatic full planning.",
  ]);
});

test("buildBlockedInjuryContextSummary sets legacyInjuryText only when guided list is empty", () => {
  const withGuided = buildBlockedInjuryContextSummary({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
    guidedInjuries: [{ area: "Left ankle", surface_type: "bruise" }],
  });
  assert.equal(withGuided.legacyInjuryText, undefined);

  const withoutGuided = buildBlockedInjuryContextSummary({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
  });
  assert.equal(withoutGuided.legacyInjuryText, "left ankle rolled in sparring");
});

test("buildBlockedInjuryContextSummary picks guided card matching head-impact medical hold signals", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: {
      red_flags: ["vomiting_after_head_impact"],
      matched_high_risk_categories: ["concussion"],
      urgent_flags: ["vomiting_after_head_impact"],
      reasons: ["Head impact with vomiting reported"],
      routing_reasons: ["medical_hold from head impact"],
    },
    guidedInjuries: [
      { area: "Left ankle", injury_type: "sprain", severity: "mild", notes: "rolled ankle" },
      { area: "Head", injury_type: "head_impact", notes: "Vomiting after head impact", severity: "high" },
    ],
  });

  assert.equal(summary.capturedInjury, "Head — Head impact · High");
});

test("buildBlockedInjuryContextSummary picks post-surgery knee card for restricted routing", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: {
      red_flags: [],
      matched_high_risk_categories: ["post_op_reconstruction_active"],
      reasons: ["Post-surgery knee still not cleared"],
      routing_reasons: ["restricted_rehab_only"],
    },
    guidedInjuries: [
      { area: "Left wrist", injury_type: "tightness", severity: "mild", notes: "mild wrist discomfort" },
      { area: "Left knee", injury_type: "post_surgery", notes: "post-surgery rehab ongoing", severity: "moderate" },
    ],
  });

  assert.equal(summary.capturedInjury, "Left knee — Post-surgery injury · Moderate");
});

test("buildBlockedInjuryContextSummary keeps first-valid fallback when no guided card matches signals", () => {
  const summary = buildBlockedInjuryContextSummary({
    triage: {
      red_flags: ["loss_of_consciousness"],
      matched_high_risk_categories: [],
      reasons: ["Coach review required"],
      routing_reasons: ["manual_review"],
    },
    guidedInjuries: [
      { area: "Left ankle", injury_type: "sprain", severity: "mild" },
      { area: "Right wrist", injury_type: "tightness", severity: "mild" },
    ],
  });

  assert.equal(summary.capturedInjury, "Left ankle — Sprain · Mild");
});
