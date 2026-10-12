import assert from "node:assert/strict";
import { test } from "node:test";

import { weekdayName } from "./exercise-customisation";

test("weekdayName reads the ISO date as a calendar day in any timezone", () => {
  assert.equal(weekdayName("2026-10-12"), "Monday");
  assert.equal(weekdayName("2026-10-18"), "Sunday");
  assert.equal(weekdayName("2026-10-12T23:30:00-08:00"), "Monday");
});
