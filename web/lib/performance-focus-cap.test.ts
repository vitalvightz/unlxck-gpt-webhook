import assert from "node:assert/strict";
import test from "node:test";

import { getPerformanceFocusCap } from "./performance-focus-cap.ts";

test("returns null when fight date is missing or invalid", () => {
  assert.equal(getPerformanceFocusCap(""), null);
  assert.equal(getPerformanceFocusCap("not-a-date"), null);
  assert.equal(getPerformanceFocusCap("2026-02-31"), null);
});

test("uses the fight-week cap for events within seven days", () => {
  assert.deepStrictEqual(
    getPerformanceFocusCap("2026-04-07", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    }),
    {
      daysUntilFight: 5,
      weeksOut: 1,
      maxSelections: 3,
      windowLabel: "Fight week",
      reason: "Fight-week plans stay extremely selective so sharpness and readiness do not get buried under too many priorities.",
    },
  );
});

test("steps through cap windows as the fight gets closer", () => {
  assert.equal(
    getPerformanceFocusCap("2026-04-20", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    4,
  );

  assert.equal(
    getPerformanceFocusCap("2026-05-05", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    5,
  );

  assert.equal(
    getPerformanceFocusCap("2026-06-06", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    6,
  );

  assert.equal(
    getPerformanceFocusCap("2026-08-20", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    7,
  );
});

test("uses the provided athlete time zone when calculating the calendar day", () => {
  assert.deepStrictEqual(
    getPerformanceFocusCap("2026-04-02", {
      now: new Date("2026-04-02T00:30:00Z"),
      timeZone: "America/Los_Angeles",
    }),
    {
      daysUntilFight: 1,
      weeksOut: 1,
      maxSelections: 3,
      windowLabel: "Fight week",
      reason: "Fight-week plans stay extremely selective so sharpness and readiness do not get buried under too many priorities.",
    },
  );
});

test("falls back to the local calendar when the saved time zone is invalid", () => {
  assert.equal(
    getPerformanceFocusCap("2026-04-07", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "Mars/OlympusMons",
    })?.maxSelections,
    3,
  );
});
