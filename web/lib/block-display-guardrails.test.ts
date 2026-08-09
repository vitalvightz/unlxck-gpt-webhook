import test from "node:test";
import assert from "node:assert/strict";

import {
  applySourceSetRange,
  getSourcePrescriptionRangeOverrides,
  selectCompactStopRule,
  stripSafetyOwnedClause,
} from "./block-display-guardrails";

test("keeps one block-specific stop rule after plan safety owns injury criteria", () => {
  const selected = selectCompactStopRule(
    [
      "Any sharp pain at the left shoulder",
      "Wound irritation",
      "If speed degrades and form breaks",
    ],
    [
      "Left shoulder surface abrasion. Keep the area clean and covered.",
      "Stop and seek care if bleeding, spreading redness, or increased pain.",
    ],
  );
  assert.equal(selected, "If speed degrades and form breaks");
});

test("renders only the first stop rule when there is no higher-level safety owner", () => {
  assert.equal(
    selectCompactStopRule(["Stop if speed drops", "Stop if technique breaks"]),
    "Stop if speed drops",
  );
});

test("removes escalation from Active Notes when Safety Priority already owns it", () => {
  const note =
    "Left shoulder surface abrasion. No open wound or infection reported. Keep the area clean and covered during training; stop and seek care if bleeding, spreading redness, or increased pain.";
  const result = stripSafetyOwnedClause(note, [
    "Stop and seek care for bleeding, spreading redness, or increased pain.",
  ]);
  assert.equal(
    result,
    "Left shoulder surface abrasion. No open wound or infection reported. Keep the area clean and covered during training",
  );
});

test("recovers exact set and effort ranges from the matching countdown block", () => {
  const source = `D-13 (Monday): Neural speed touch\n- Band-Resisted Jab-Cross Primer — 2-3 sets x 6 punches per set, full recovery 90-120 sec, RPE 6-7.\n\nD-6 (Monday): Freshness primer\n- Band-Resisted Jab-Cross Primer — 1-2 sets x 4 punches, RPE 5-6.`;
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Band-Resisted Jab-Cross Primer", "D-13"),
    { sets: "2-3", effort: "RPE 6-7" },
  );
});

test("puts the source set range back onto an orphaned per-set volume", () => {
  assert.deepEqual(
    applySourceSetRange([{ label: "Volume", value: "6 punches per set" }], "2-3"),
    [{ label: "Volume", value: "2-3 × 6 punches" }],
  );
});
