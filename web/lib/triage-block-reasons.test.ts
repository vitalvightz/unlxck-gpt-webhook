import assert from "node:assert/strict";
import test from "node:test";

import { summarizeBlockedInjuryContext } from "./triage-block-reasons.ts";

test("summarizeBlockedInjuryContext uses guided injury_type labels before raw text", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    injuriesText: "left ankle rolled in sparring",
    guidedInjuries: [{ area: "Left ankle", injury_type: "sprain" }],
  });

  assert.equal(summary, "Blocked trigger: Sprain + left ankle rolled in sparring");
});

test("summarizeBlockedInjuryContext infers canonical reason from injury notes synonyms", () => {
  const summary = summarizeBlockedInjuryContext({
    triage: { red_flags: [], matched_high_risk_categories: [] },
    guidedInjuries: [{ area: "Right shoulder", notes: "Feels unstable and keeps giving way" }],
  });

  assert.equal(summary, "Blocked trigger: Instability + Right shoulder");
});
