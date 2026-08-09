import test from "node:test";
import assert from "node:assert/strict";

import { getBlockAdjustmentDisplay, getBlockExecutionDisplay } from "./structured-plan.ts";

test("pure exercise progression stays under Progress", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({ progression_rule: "Increase band resistance when speed stays high." }),
    { progression: "Increase band resistance when speed stays high.", stopRules: [] },
  );
});

test("legacy pure stop text becomes a stop rule instead of Progress", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({ progression_rule: "Stop if sharp quad pain appears." }),
    { progression: null, stopRules: ["Stop if sharp quad pain appears."] },
  );
});

test("legacy mixed progression splits into Progress and Stop rule", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      progression_rule: "Increase band resistance when speed stays high — Stop: sharp shoulder pain.",
    }),
    {
      progression: "Increase band resistance when speed stays high",
      stopRules: ["sharp shoulder pain."],
    },
  );
});

test("taper programming is not shown as exercise progression", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      progression_rule:
        "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain or uncontrolled balance loss.",
    }),
    {
      progression: null,
      stopRules: ["any sharp ankle pain or uncontrolled balance loss."],
    },
  );
});

test("explicit and legacy stop rules are preserved and deduplicated", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      stop_rules: ["Stop: sharp ankle pain."],
      coaching_cues: ["Fast hands", "Stop: sharp ankle pain."],
    }),
    { progression: null, stopRules: ["sharp ankle pain."] },
  );
});

test("legacy labelled planning prose is hidden from execution cues", () => {
  assert.deepEqual(
    getBlockExecutionDisplay({
      coaching_cues: [
        "Purpose: transfer horizontal punching force under slight resistance",
        "Why today: single neural touch without disrupting taper",
        "Explosive intent; accelerate through full range",
        "Easier: reduce band tension",
        "Reset guard immediately",
        "Stop: sharp ankle pain",
      ],
      regression_options: ["Reduce band tension"],
    }),
    {
      cues: ["Explosive intent; accelerate through full range", "Reset guard immediately"],
      stopRules: ["sharp ankle pain"],
      regressions: ["Reduce band tension"],
      substitutions: [],
      progressions: [],
    },
  );
});
