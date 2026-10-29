import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { DaySessionContext, SessionCard } from "./structured-plan-renderer";
import { buildPlanCalendar } from "@/lib/plan-calendar";
import type { StructuredDay } from "@/lib/types";

test("declared technical combat is owned by its session, not repeated in day context", () => {
  const day: StructuredDay = { date: "2026-12-06", countdown_label: "D-5", day_type: "light",
    today_card: { headline: "Technical Combat" },
    sessions: [{ title: "Technical Combat", session_type: "skill", blocks: [] }] };
  const context = renderToStaticMarkup(<DaySessionContext day={day} />);
  assert.doesNotMatch(context, /Pads, drills, movement/);
});

test("countdown-prefixed reduced combat has one standard heading inside its box", () => {
  const html = renderToStaticMarkup(<SessionCard layout="plan" showDayLabels={false}
    session={{ title: "D-5 — Technical-only combat", session_type: "skill", blocks: [] }} />);
  assert.doesNotMatch(html, /D-5/);
  assert.equal((html.match(/class="sp-session-title"/g) ?? []).length, 1);
  assert.match(html, /Technical Combat/);
});

test("legacy optional prescription remains inside the purple disclosure", () => {
  const html = renderToStaticMarkup(<SessionCard layout="plan" session={{ title: "Fight Visualisation", session_type: "mindset",
    objective: "Optional. Rehearse your opening exchange.", blocks: [{ display_name: "Tactical Picture", block_type: "mindset", coaching_cues: ["Reset on guard."] }] }} />);
  assert.match(html, /sp-session-support/);
  assert.match(html, /sp-optional-content/);
  assert.match(html, /Reset on guard/);
});

test("fight day is marked independently of calendar completion state", () => {
  const rows = buildPlanCalendar([{ week_id: "fight-week", days: [{ date: "2026-12-11", countdown_label: "D-0", day_type: "competition", sessions: [] }] }]);
  assert.equal(rows.flatMap(row => row.cells).find(cell => cell.iso === "2026-12-11")?.isFightDay, true);
});
