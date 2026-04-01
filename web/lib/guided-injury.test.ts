import assert from "node:assert/strict";
import test from "node:test";

import { parseGuidedInjuryState } from "./guided-injury.ts";

test("preserves note sentences that contain periods", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Right shoulder. Notes: Range of motion limited. Follow PT exercises daily."),
    {
      area: "Right shoulder",
      severity: "",
      trend: "",
      avoid: "",
      notes: "Range of motion limited. Follow PT exercises daily",
    },
  );
});

test("merges multiple avoid phrases into the avoid field", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Left knee. Avoid: deep squats. Movements to avoid: sprinting."),
    {
      area: "Left knee",
      severity: "",
      trend: "",
      avoid: "deep squats. sprinting",
      notes: "",
    },
  );
});

test("keeps dashed anatomical names while still parsing descriptors", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Hip flexor-iliopsoas – high, worsening. Notes: Monitor soreness."),
    {
      area: "Hip flexor-iliopsoas",
      severity: "high",
      trend: "worsening",
      avoid: "",
      notes: "Monitor soreness",
    },
  );
});

test("captures notes-only text that begins with Notes and includes later sentences", () => {
  assert.deepStrictEqual(
    parseGuidedInjuryState("Notes: Chronic inflammation. Monitor swelling after sessions."),
    {
      area: "",
      severity: "",
      trend: "",
      avoid: "",
      notes: "Chronic inflammation. Monitor swelling after sessions",
    },
  );
});
