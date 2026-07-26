import assert from "node:assert/strict";
import test from "node:test";

import { getPerformanceFocusCap, validatePerformanceFocusSelections } from "./performance-focus-cap.ts";

test("uses the open-plan cap when fight date is missing or invalid", () => {
  assert.deepStrictEqual(getPerformanceFocusCap(""), {
    daysUntilFight: Number.POSITIVE_INFINITY,
    weeksOut: Number.POSITIVE_INFINITY,
    maxSelections: 5,
    windowLabel: "Open plan",
    reason: "Open plans use a focused cap to keep goals and weak areas clear without a fight-date countdown.",
  });
  assert.equal(getPerformanceFocusCap("not-a-date")?.maxSelections, 5);
  assert.equal(getPerformanceFocusCap("2026-02-31")?.maxSelections, 5);
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
      maxSelections: 2,
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
    3,
  );

  assert.equal(
    getPerformanceFocusCap("2026-05-05", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    4,
  );

  assert.equal(
    getPerformanceFocusCap("2026-06-06", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    5,
  );

  assert.equal(
    getPerformanceFocusCap("2026-08-20", {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    })?.maxSelections,
    6,
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
      maxSelections: 2,
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
    2,
  );
});

test("flags over-cap performance selections with a generation-safe message", () => {
  const result = validatePerformanceFocusSelections(
    "2026-04-07",
    {
      keyGoals: ["power", "conditioning"],
      weakAreas: ["defense", "gas_tank"],
    },
    {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    },
  );

  assert.equal(result.isOverCap, true);
  assert.equal(result.excessSelections, 2);
  assert.equal(
    result.errorMessage,
    "This camp allows 2 total focus picks. Remove 2 goal or weak-area selections before generating.",
  );
});

// D-140 is the "Long camp" band, capped at 6 (pinned by the cap-table test
// above). These two cases sit either side of that boundary.
test("does not flag selections when the total stays within the current cap", () => {
  const result = validatePerformanceFocusSelections(
    "2026-08-20",
    {
      keyGoals: ["power", "conditioning", "fight_sharpness"],
      weakAreas: ["defense", "gas_tank", "timing"],
    },
    {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    },
  );

  assert.equal(result.totalSelections, 6);
  assert.equal(result.isOverCap, false);
  assert.equal(result.errorMessage, null);
});

test("flags one selection over the long-camp cap", () => {
  const result = validatePerformanceFocusSelections(
    "2026-08-20",
    {
      keyGoals: ["power", "conditioning", "fight_sharpness", "volume"],
      weakAreas: ["defense", "gas_tank", "timing"],
    },
    {
      now: new Date("2026-04-02T08:00:00Z"),
      timeZone: "UTC",
    },
  );

  assert.equal(result.isOverCap, true);
  assert.equal(result.excessSelections, 1);
  assert.equal(
    result.errorMessage,
    "This camp allows 6 total focus picks. Remove 1 goal or weak-area selection before generating.",
  );
});
