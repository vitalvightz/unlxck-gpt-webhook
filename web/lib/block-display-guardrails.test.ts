import test from "node:test";
import assert from "node:assert/strict";

import {
  applySourceSetRange,
  getSourcePrescriptionRangeOverrides,
  stripSafetyOwnedClause,
} from "./block-display-guardrails";


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

test("does not strip an unrelated single-symptom escalation from another body part", () => {
  const note = "Right calf strain. Stop if calf pain increases.";
  const result = stripSafetyOwnedClause(note, [
    "Stop and seek care if shoulder pain increases.",
  ]);
  assert.equal(result, note);
});

test("recovers exact set and effort ranges from the matching countdown block", () => {
  const source = `D-13 (Monday): Neural speed touch
- Band-Resisted Jab-Cross Primer — 2-3 sets x 6 punches per set, full recovery 90-120 sec, RPE 6-7.

D-6 (Monday): Freshness primer
- Band-Resisted Jab-Cross Primer — 1-2 sets x 4 punches, RPE 5-6.`;
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Band-Resisted Jab-Cross Primer", "D-13"),
    { sets: "2-3", effort: "RPE 6-7", rest: "90-120 sec" },
  );
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Band-Resisted Jab-Cross Primer", "D-6"),
    { sets: "1-2", effort: "RPE 5-6", rest: null },
  );
});

test("fails closed instead of borrowing a same-named block from another countdown day", () => {
  const source = `D-13 (Monday): Neural speed touch
- Band-Resisted Jab-Cross Primer — 2-3 sets x 6 punches, RPE 6-7.`;
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Band-Resisted Jab-Cross Primer", "D-6"),
    { sets: null, effort: null, rest: null },
  );
});

test("requires the exact block title rather than a substring match", () => {
  const source = `D-6 (Monday): Freshness primer
- Band-Resisted Jab-Cross Primer Plus — 4-5 sets x 4 punches, RPE 7-8.
- Band-Resisted Jab-Cross Primer — 1-2 sets x 4 punches, RPE 5-6.`;
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Band-Resisted Jab-Cross Primer", "D-6"),
    { sets: "1-2", effort: "RPE 5-6", rest: null },
  );
});


test("recovers source ranges after an A-or-B title is split to the chosen exercise", () => {
  const source =
    "- Short sprint bounds or low box jumps — 2-3 sets x 4 reps, RPE 6-7, rest 60-90 sec.";
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Short sprint bounds"),
    { sets: "2-3", effort: "RPE 6-7", rest: "60-90 sec" },
  );
});

test("treats legacy D0 and D-0 countdown labels as the same fight-day section", () => {
  const source = `D0 (Fight day): Primer
- Fast Hands Primer — 1-2 sets x 4 punches, RPE 4-5.`;
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Fast Hands Primer", "D-0"),
    { sets: "1-2", effort: "RPE 4-5", rest: null },
  );
});

test("recovers an explicit rest range instead of collapsing it to one endpoint", () => {
  const source = "- Trap bar deadlift: 3 x 5 @ RPE 7. Rest 2-3 min.";
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Trap bar deadlift"),
    { sets: null, effort: "RPE 7", rest: "2-3 min" },
  );
});

test("recovers scalar effort and postfix rest from a period-delimited block", () => {
  const source = "- Trap-Bar Romanian Deadlift. 3 sets x 6 reps @ RPE 7. 90 sec rest.";
  assert.deepEqual(
    getSourcePrescriptionRangeOverrides(source, "Trap-Bar Romanian Deadlift"),
    { sets: null, effort: "RPE 7", rest: "90 sec" },
  );
});

test("puts the source set range back onto an orphaned per-set volume", () => {
  assert.deepEqual(
    applySourceSetRange([{ label: "Volume", value: "6 punches per set" }], "2-3"),
    [{ label: "Volume", value: "2-3 × 6 punches" }],
  );
});
