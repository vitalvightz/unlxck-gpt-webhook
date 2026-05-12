import assert from "node:assert/strict";
import test from "node:test";

import { summarizeBlockedInjuryContext } from "./triage-block-reasons.ts";

test("summarizeBlockedInjuryContext prioritises structured guided injury context", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
    guidedInjuries: [{ area: "Left ankle", surface_type: "bruise", severity: "moderate", trend: "stable", impact_related: "yes" }],
  });

  assert.equal(summary, "Captured injury: Left ankle — Bruise / contusion · Moderate · Stable · Impact-related");
});

test("summarizeBlockedInjuryContext falls back to note inference when no structured guided context exists", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Right shoulder", notes: "Feels unstable and keeps giving way" }],
  });

  assert.equal(summary, "Blocked trigger: Instability + Right shoulder");
});
