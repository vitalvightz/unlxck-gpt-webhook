import assert from "node:assert/strict";
import test from "node:test";

import {
  filterBodyweightEntriesByRange,
  getBodyMassIndex,
  getRecentChange,
  getSevenDayAverage,
  getTargetGap,
} from "./nutrition-bodyweight.ts";

const entries = [
  { date: "2026-04-01", time: "07:10", weight_kg: 74.6, is_fasted: true, notes: "" },
  { date: "2026-04-03", time: "07:15", weight_kg: 74.1, is_fasted: true, notes: "" },
  { date: "2026-04-06", time: "07:20", weight_kg: 73.8, is_fasted: false, notes: "" },
  { date: "2026-04-08", time: "07:05", weight_kg: 73.4, is_fasted: true, notes: "" },
].map((entry) => ({ ...entry }));

test("filters 7D and 30D ranges relative to the latest logged entry", () => {
  assert.deepStrictEqual(
    filterBodyweightEntriesByRange(entries, "7D").map((entry) => entry.date),
    ["2026-04-08", "2026-04-06", "2026-04-03"],
  );

  assert.deepStrictEqual(
    filterBodyweightEntriesByRange(entries, "30D").map((entry) => entry.date),
    ["2026-04-08", "2026-04-06", "2026-04-03", "2026-04-01"],
  );
});

test("derives recent change from the latest two entries inside the active range", () => {
  assert.equal(getRecentChange(entries, "All"), -0.4);
  assert.equal(
    getRecentChange([{ date: "2026-04-08", time: "07:05", weight_kg: 73.4, is_fasted: true, notes: "" }], "All"),
    null,
  );
});

test("calculates 7-entry average using the most recent entries", () => {
  assert.equal(getSevenDayAverage(entries), 74);
});

test("calculates BMI and target gap only when enough data is present", () => {
  assert.equal(getBodyMassIndex(178, 73.4), 23.2);
  assert.equal(getBodyMassIndex(null, 73.4), null);
  assert.equal(getTargetGap(73.4, 70), 3.4);
  assert.equal(getTargetGap(null, 70), null);
});
