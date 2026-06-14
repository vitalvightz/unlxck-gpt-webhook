import test from "node:test";
import assert from "node:assert/strict";

import { isMeaningfulRiskBand, selectInjuryRiskAdvisory } from "./sparring-advisory.ts";
import type { PlanAdvisory } from "./types.ts";

function advisory(overrides: Partial<PlanAdvisory>): PlanAdvisory {
  return {
    kind: "sparring_adjustment",
    action: "convert",
    phase: "TAPER",
    week_label: "Week 1",
    days: ["Monday"],
    title: "Coach note",
    reason: "reason",
    suggestion: "suggestion",
    ...overrides,
  } as PlanAdvisory;
}

test("isMeaningfulRiskBand: only amber/red/black count as injury risk", () => {
  assert.equal(isMeaningfulRiskBand("amber"), true);
  assert.equal(isMeaningfulRiskBand("red"), true);
  assert.equal(isMeaningfulRiskBand("black"), true);
  assert.equal(isMeaningfulRiskBand("green"), false);
  assert.equal(isMeaningfulRiskBand(null), false);
  assert.equal(isMeaningfulRiskBand(undefined), false);
});

test("selectInjuryRiskAdvisory hides advisories with no real injury risk", () => {
  // The common redundant case: load tweaks the plan already makes, no injury risk.
  assert.equal(selectInjuryRiskAdvisory([advisory({ risk_band: "green" })]), null);
  assert.equal(selectInjuryRiskAdvisory([advisory({ risk_band: null })]), null);
  assert.equal(selectInjuryRiskAdvisory([advisory({})]), null);
  assert.equal(selectInjuryRiskAdvisory([]), null);
  assert.equal(selectInjuryRiskAdvisory(null), null);
  assert.equal(selectInjuryRiskAdvisory(undefined), null);
});

test("selectInjuryRiskAdvisory surfaces an advisory that carries injury risk", () => {
  const picked = selectInjuryRiskAdvisory([
    advisory({ risk_band: "green", days: ["Tuesday"] }),
    advisory({ risk_band: "amber", days: ["Monday"] }),
  ]);
  assert.equal(picked?.risk_band, "amber");
  assert.deepEqual(picked?.days, ["Monday"]);
});

test("selectInjuryRiskAdvisory picks the most severe injury risk", () => {
  const picked = selectInjuryRiskAdvisory([
    advisory({ risk_band: "amber" }),
    advisory({ risk_band: "black" }),
    advisory({ risk_band: "red" }),
  ]);
  assert.equal(picked?.risk_band, "black");
});
