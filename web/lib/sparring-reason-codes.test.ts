import assert from "node:assert/strict";
import test from "node:test";

import {
  explainEffectiveLoad,
  explainReasonCode,
  explainRiskBand,
  explainSparringClass,
  knownReasonCodes,
} from "./sparring-reason-codes.ts";

test("known reason codes have non-empty title and body", () => {
  for (const code of knownReasonCodes()) {
    const explanation = explainReasonCode(code);
    assert.ok(explanation.title.trim(), `missing title for ${code}`);
    assert.ok(explanation.body.trim(), `missing body for ${code}`);
  }
});

test("unknown reason codes fall back to humanized text", () => {
  const explanation = explainReasonCode("some_brand_new_code");
  assert.equal(explanation.title, "Some brand new code");
  assert.match(explanation.body, /coach review/i);
});

test("planner-emitted reason codes are all covered", () => {
  // Mirrors the strings emitted by fightcamp/sparring_dose_planner.py
  // and sparring_advisories.py. If the planner adds a new code, a copy
  // entry should land alongside it.
  const plannerEmitted = [
    "high_fatigue",
    "moderate_fatigue",
    "high_cut",
    "moderate_cut",
    "high_week_pressure",
    "moderate_week_pressure",
    "high_injury",
    "moderate_injury",
    "worsening",
    "instability",
    "daily_symptoms",
    "two_hard_days",
    "four_hard_days",
    "consecutive_hard_days",
    "hard_day_cap",
    "fight_week_taper",
    "final_week_sparring_cap",
    "d14_hard_sparring_ban",
    "d17_hard_sparring_ban",
    "serious_contact_safety",
    "medical_contact_restriction",
    "d21_d18_cap_one",
  ];

  const covered = new Set(knownReasonCodes());
  for (const code of plannerEmitted) {
    assert.ok(covered.has(code), `reason-code dictionary is missing ${code}`);
  }
});

test("effective load explanations exist for every load value", () => {
  for (const load of ["hard", "technical", "reduced", "none"] as const) {
    const explanation = explainEffectiveLoad(load);
    assert.ok(explanation.title.trim());
    assert.ok(explanation.body.trim());
  }
});

test("sparring class explanations exist for every class value", () => {
  const classes = [
    "primary_hard",
    "secondary_hard",
    "managed_hard",
    "technical",
    "none",
  ] as const;
  for (const value of classes) {
    const explanation = explainSparringClass(value);
    assert.ok(explanation.title.trim());
    assert.ok(explanation.body.trim());
  }
});

test("risk band explanations cover all bands", () => {
  for (const band of ["green", "amber", "red", "black"]) {
    const explanation = explainRiskBand(band);
    assert.ok(explanation, `missing risk band explanation for ${band}`);
    assert.ok(explanation!.title.trim());
    assert.ok(explanation!.body.trim());
  }
  assert.equal(explainRiskBand(null), null);
  assert.equal(explainRiskBand(undefined), null);
});
