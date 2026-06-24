import test from "node:test";
import assert from "node:assert/strict";

import { formatAppDate, formatAppDateTime } from "./date-format.ts";

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
