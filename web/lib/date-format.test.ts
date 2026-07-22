import test from "node:test";
import assert from "node:assert/strict";

import {
  describeRelativeDay,
  formatAppDate,
  formatAppDateRange,
  formatAppDateTime,
} from "./date-format.ts";

test("formatAppDate renders date-only ISO as 'EEE DD MMM YYYY'", () => {
  assert.equal(formatAppDate("2026-07-02"), "Thu 02 Jul 2026");
});

test("formatAppDate does not shift across the month/year boundary", () => {
  // Anchored at noon UTC so the rendered day never rolls back to Dec 31.
  assert.equal(formatAppDate("2026-01-01"), "Thu 01 Jan 2026");
});

test("formatAppDate zero-pads the day", () => {
  assert.equal(formatAppDate("2026-06-09"), "Tue 09 Jun 2026");
});

test("formatAppDate returns the raw input when unparseable", () => {
  assert.equal(formatAppDate("not-a-date"), "not-a-date");
});

test("formatAppDate returns empty string for empty/nullish input", () => {
  assert.equal(formatAppDate(""), "");
  assert.equal(formatAppDate(null), "");
  assert.equal(formatAppDate(undefined), "");
});

test("formatAppDateTime appends the time to the canonical date", () => {
  const formatted = formatAppDateTime("2026-07-02T14:30:00Z");
  // Time is rendered in the local timezone, so assert on the stable shape
  // (no comma after the weekday, comma before the time).
  assert.match(formatted, /^\w{3} \d{2} \w{3} \d{4}, \d{2}:\d{2}$/);
});

test("formatAppDateTime returns the raw input when unparseable", () => {
  assert.equal(formatAppDateTime("nope"), "nope");
});

test("formatAppDateRange drops the shared month and year within one month", () => {
  assert.equal(
    formatAppDateRange("2026-07-22", "2026-07-28"),
    "Wed 22 → Tue 28 Jul 2026",
  );
});

test("formatAppDateRange drops only the shared year across months", () => {
  assert.equal(
    formatAppDateRange("2026-07-29", "2026-08-02"),
    "Wed 29 Jul → Sun 02 Aug 2026",
  );
});

test("formatAppDateRange keeps both years fully across a year boundary", () => {
  assert.equal(
    formatAppDateRange("2026-12-29", "2027-01-01"),
    "Tue 29 Dec 2026 → Fri 01 Jan 2027",
  );
});

test("formatAppDateRange falls back to the single date when one end is missing", () => {
  assert.equal(formatAppDateRange("2026-07-22", null), "Wed 22 Jul 2026");
  assert.equal(formatAppDateRange("", "2026-07-28"), "Tue 28 Jul 2026");
  assert.equal(formatAppDateRange(null, undefined), "");
});

test("formatAppDateRange falls back to an arrow-join when an end is unparseable", () => {
  assert.equal(
    formatAppDateRange("2026-07-22", "nope"),
    "Wed 22 Jul 2026 → nope",
  );
});

test("describeRelativeDay labels today, tomorrow, and near-future days", () => {
  const today = "2026-07-22";
  assert.equal(describeRelativeDay("2026-07-22", today), "Today");
  assert.equal(describeRelativeDay("2026-07-23", today), "Tomorrow");
  assert.equal(describeRelativeDay("2026-07-24", today), "in 2 days");
});

test("describeRelativeDay returns null for past, far-future, or unparseable dates", () => {
  const today = "2026-07-22";
  assert.equal(describeRelativeDay("2026-07-21", today), null);
  assert.equal(describeRelativeDay("2026-08-30", today), null);
  assert.equal(describeRelativeDay("nope", today), null);
  assert.equal(describeRelativeDay(null, today), null);
});

test("describeRelativeDay compares by calendar day, not wall clock", () => {
  // Reference and target given as full timestamps straddling midnight UTC. The
  // label must resolve by calendar date (22nd vs 23rd) regardless of the machine
  // timezone — the server/browser near-midnight disagreement the anchor fixes.
  assert.equal(
    describeRelativeDay("2026-07-23T00:30:00Z", "2026-07-22T23:30:00Z"),
    "Tomorrow",
  );
  assert.equal(
    describeRelativeDay("2026-07-22T02:00:00Z", "2026-07-22T23:30:00Z"),
    "Today",
  );
});

test("describeRelativeDay returns null when the reference day is missing", () => {
  assert.equal(describeRelativeDay("2026-07-24", null), null);
  assert.equal(describeRelativeDay("2026-07-24", undefined), null);
  assert.equal(describeRelativeDay("2026-07-24", ""), null);
});
