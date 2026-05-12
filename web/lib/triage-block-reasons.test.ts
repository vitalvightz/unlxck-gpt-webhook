import assert from "node:assert/strict";
import test from "node:test";

import { summarizeBlockedInjuryContext } from "./triage-block-reasons.ts";

test("summarizeBlockedInjuryContext returns captured injury for structured injury only", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
    guidedInjuries: [{ area: "Left ankle", surface_type: "bruise", severity: "moderate", trend: "stable", impact_related: "yes" }],
  });

  assert.equal(summary, "Captured injury: Left ankle — Bruise / contusion · Moderate · Stable · Impact-related");
});

test("summarizeBlockedInjuryContext shows blocked trigger before captured injury when safety signal exists", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: ["loss_of_consciousness"], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Head", injury_type: "concussion", severity: "high" }],
  });

  assert.equal(summary, "Blocked trigger: Loss of consciousness · Captured injury: Head — Concussion · High");
});

test("summarizeBlockedInjuryContext prioritises red flags over high-risk labels", () => {
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
    "Blocked trigger: Loss of consciousness + Moderate stable injury · Captured injury: Head — Concussion · High",
  );
});

test("summarizeBlockedInjuryContext infers instability from guided notes when structured context has area only", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Right shoulder", notes: "Feels unstable and keeps giving way" }],
  });

  assert.equal(summary, "Blocked trigger: Instability · Captured injury: Right shoulder");
});

test("summarizeBlockedInjuryContext maps skin_irritation surface type", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Head", surface_type: "skin_irritation" }],
  });

  assert.equal(summary, "Captured injury: Head — Burn / skin irritation");
});

test("summarizeBlockedInjuryContext keeps fallback when guided injury is absent", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: ["moderate_stable_injury"], reasons: ["did not meet strict allowlist"] },
    injuriesText: "left ankle rolled in sparring",
  });

  assert.equal(summary, "Blocked trigger: Moderate stable injury + did not meet strict allowlist");
});
