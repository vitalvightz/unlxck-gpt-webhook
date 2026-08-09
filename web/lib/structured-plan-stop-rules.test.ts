import test from "node:test";
import assert from "node:assert/strict";

import { getBlockAdjustmentDisplay } from "./structured-plan.ts";

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
