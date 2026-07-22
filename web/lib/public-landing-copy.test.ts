import test from "node:test";
import assert from "node:assert/strict";

import {
  LANDING_OUTCOME_POINTS,
  LANDING_PRODUCT_PROOF_POINTS,
  LANDING_WORKFLOW_STEPS,
  LANDING_WORKSPACE_ROWS,
  PUBLIC_HERO_SUMMARY,
} from "./public-landing-copy";

test("the hero summary leads with an athlete outcome, not a feature list", () => {
  const summary = PUBLIC_HERO_SUMMARY.toLowerCase();
  assert.ok(summary.includes("know what to train"), "hero should promise knowing what to train");
  assert.ok(
    summary.includes("adjust before fatigue"),
    "hero should promise adjusting before fatigue",
  );
  // The old copy was a bare feature enumeration; make sure it is gone.
  assert.ok(
    !summary.includes("intake, readiness, camp plan, and saved history"),
    "hero should no longer be a feature list",
  );
});

test("the hero proof strip stays to three concise outcome points", () => {
  assert.ok(
    LANDING_OUTCOME_POINTS.length <= 3,
    `expected at most 3 outcome points, got ${LANDING_OUTCOME_POINTS.length}`,
  );
  const values = LANDING_OUTCOME_POINTS.map((point) => point.value.toLowerCase());
  assert.ok(values.some((value) => value.includes("know what to train")));
  assert.ok(values.some((value) => value.includes("decisions, not guesses")));
});

test("the proof grid headlines are outcome-led and each distinct", () => {
  const titles: string[] = LANDING_PRODUCT_PROOF_POINTS.map((point) => point.title);
  const outcomeSignals = [
    "know what to train today",
    "adjust before fatigue becomes failure",
    "turn check-ins into clear training decisions",
    "keep the camp moving without guessing",
  ];
  for (const signal of outcomeSignals) {
    assert.ok(
      titles.some((title) => title.toLowerCase().includes(signal)),
      `expected a proof headline for: ${signal}`,
    );
  }
  // No section should simply restate a stored-feature title.
  assert.equal(new Set(titles).size, titles.length, "proof headlines must be unique");
  assert.ok(!titles.includes("Context before output."));
  assert.ok(!titles.includes("The plan is structured."));
});

test("no proof-grid body overpromises medical safety or guaranteed performance", () => {
  const forbidden = ["injury-free", "keeps you safe", "prevent injury", "guarantee", "diagnos"];
  for (const point of LANDING_PRODUCT_PROOF_POINTS) {
    const body = point.body.toLowerCase();
    for (const term of forbidden) {
      assert.ok(!body.includes(term), `proof body must not claim "${term}": ${point.body}`);
    }
  }
});

test("the workspace preview remains the single place the pipeline is enumerated", () => {
  const labels = LANDING_WORKSPACE_ROWS.map((row) => row.label);
  assert.ok(labels.includes("Intake"));
  assert.ok(labels.includes("Readiness"));
  assert.ok(labels.includes("Camp plan"));
});

test("the how-it-works steps stay a four-step setup flow", () => {
  assert.equal(LANDING_WORKFLOW_STEPS.length, 4);
  assert.deepEqual(
    LANDING_WORKFLOW_STEPS.map((step) => step.label),
    ["Step 1", "Step 2", "Step 3", "Step 4"],
  );
});
