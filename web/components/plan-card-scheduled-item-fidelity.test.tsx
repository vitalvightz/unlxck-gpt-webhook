// Production regression: every authoritative scheduled item in plan_text must
// materialise in the athlete card.
//
// The reported failure: a taper plan whose `structured_plan` was null rendered
// D-10 and D-9 as "Rest / Recovery" even though plan_text scheduled Joint Prep,
// a Breathing Reset and a Pressure Step-Cut Reset on those days. The countdown
// headings for those items carried no weekday parenthetical, the parser only
// recognised a heading WITH one, so the items were swallowed into the previous
// day's body and the countdown gap-filler manufactured a rest row on top of
// them.
//
// These tests pin the invariant at both ends: the adapted structured plan keeps
// every scheduled item, and the renderer never prints a rest row for a day that
// carries one.
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { StructuredPlanRenderer, buildDayTimeline } from "./structured-plan-renderer";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import {
  classifySessionlessDay,
  getDays,
  getPhysicalSessions,
  getSessions,
  getWeeks,
  isCoachLedPhysicalTrainingDay,
  isZeroLoadSupportSession,
} from "@/lib/structured-plan";
import { dayCompletion, weekCompletion, weekSessionSummary } from "@/lib/camp-map";
import type { StructuredDay, StructuredPlan } from "@/lib/types";

// D-0 is Thursday 15 Oct 2026, so D-10 is a Monday exactly as in production.
const FIGHT_DATE = "2026-10-15";

/** The production plan, countdown-only headings and all. */
const PRODUCTION_PLAN_TEXT = [
  "Lead notes — taper week, keep freshness priority.",
  "",
  "D-10 (Monday) — Joint Prep",
  "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks.",
  "Stay smooth and pain-free.",
  "",
  "D-9 (Tuesday) — Breathing Reset",
  "Nasal breathing, 5 minutes, box pattern. Finish calmer than you started.",
  "",
  "D-9 (Tuesday) — Pressure Step-Cut Reset",
  "Why: read the opponent's exit lane and cut it.",
  "- Pressure Step-Cut Reset: 2 sets x 4 clean reactions each direction, RPE 5.",
  "",
  "D-8 — Neural Visualisation",
  "5 minutes.",
  "Rehearse the opening exchange, opponent reaction and composed reset.",
  "",
  "D-7 (Thursday) — Tactical Watch",
  "- Pocket Exchange Map: 10 minutes, tactical review only. No physical load.",
  "",
  "D-5 — Freshness Primer",
  "Why: sharpen speed without soreness.",
  "- Explosive Boxing Burst Intervals: 2-3 x 5-6 sec bursts, RPE 6.",
  "",
  "D-5 — Fight Visualisation",
  "Quiet visualisation only. Rehearse first exchange, best entry and final-round composure.",
  "",
  "D-4 (Sunday) — Technical-only combat",
  "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority.",
  "",
  "D-3 (Monday) — Technical Shadow Rhythm",
  "Light shadow rhythm only. Smooth entries, exits, and reset cues.",
  "",
  "D-0 (Thursday) — Fight day protocol",
  "Fight day protocol — follow coach warm-up and fight protocol; no additional S&C.",
].join("\n");

function planDays(plan: StructuredPlan): StructuredDay[] {
  return getWeeks(plan).flatMap((week) => getDays(week));
}

function dayFor(plan: StructuredPlan, countdown: string): StructuredDay {
  const day = planDays(plan).find((entry) => entry.countdown_label === countdown);
  assert.ok(day, `expected ${countdown} to exist in the adapted plan`);
  return day;
}

/** The renderer's own rest decision (structured-plan-renderer.isPlainRestDay). */
function rendersAsRest(day: StructuredDay): boolean {
  return getSessions(day).length === 0 && classifySessionlessDay(day).kind === "rest";
}

const productionPlan = buildStructuredPlanFromText(PRODUCTION_PLAN_TEXT, FIGHT_DATE);

test("D-10 keeps its blockless Joint Prep session instead of becoming rest", () => {
  const day = dayFor(productionPlan, "D-10");
  const sessions = getSessions(day);

  assert.equal(sessions.length, 1);
  assert.equal(sessions[0]?.title, "Joint Prep");
  assert.match(sessions[0]?.objective ?? "", /Neck CARs, shoulder CARs/);
  assert.match(sessions[0]?.objective ?? "", /Stay smooth and pain-free/);
  // No exercise block is invented for an item the source never dosed.
  assert.deepEqual(sessions[0]?.blocks, []);
  assert.equal(rendersAsRest(day), false);
  // Substantial mobility is physical work.
  assert.equal(getPhysicalSessions(day).length, 1);
});

test("both D-9 items survive and only the physical one counts", () => {
  const day = dayFor(productionPlan, "D-9");
  const titles = getSessions(day).map((session) => session.title);

  assert.deepEqual(titles, ["Breathing Reset", "Pressure Step-Cut Reset"]);
  assert.equal(rendersAsRest(day), false);
  assert.deepEqual(
    getPhysicalSessions(day).map((session) => session.title),
    ["Pressure Step-Cut Reset"],
  );
  assert.equal(isZeroLoadSupportSession(getSessions(day)[0]), true);
  assert.equal(dayCompletion(day).total, 1);
});

test("a countdown-only heading is still a scheduled day", () => {
  // The production plan headings all carry their weekday, but a countdown-only
  // heading is valid and used to be swallowed into the previous day's body,
  // leaving the gap-filler to print a rest row over real work.
  const plan = buildStructuredPlanFromText(
    [
      "D-12 (Saturday) — Neural speed touch",
      "- Trap bar deadlift: 2-3 sets x 3 reps",
      "",
      "D-10 — Joint Prep",
      "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks.",
      "",
      "D-9 — Breathing Reset",
      "Nasal breathing, 5 minutes, box pattern.",
    ].join("\n"),
    FIGHT_DATE,
  );

  assert.deepEqual(
    getDays(getWeeks(plan)[0]).map((day) => day.countdown_label),
    ["D-12", "D-10", "D-9"],
  );
  assert.equal(getSessions(dayFor(plan, "D-10"))[0]?.title, "Joint Prep");
  assert.equal(getSessions(dayFor(plan, "D-9"))[0]?.title, "Breathing Reset");
  // A countdown RANGE is not a heading: it must not become a session titled D-7.
  const range = buildStructuredPlanFromText(
    ["D-14 — D-7 is the sharpening block.", ""].join("\n"),
    FIGHT_DATE,
  );
  assert.deepEqual(getDays(getWeeks(range)[0] ?? {}), []);
});

test("D-3 technical shadow rhythm survives as a blockless physical session", () => {
  const day = dayFor(productionPlan, "D-3");
  const session = getSessions(day)[0];

  assert.equal(session?.title, "Technical Shadow Rhythm");
  assert.match(session?.objective ?? "", /Light shadow rhythm only/);
  assert.equal(rendersAsRest(day), false);
  assert.equal(isZeroLoadSupportSession(session), false);
});

test("a visualisation-only day renders and contributes no physical session", () => {
  const day = dayFor(productionPlan, "D-8");
  const session = getSessions(day)[0];

  assert.equal(session?.title, "Neural Visualisation");
  assert.match(session?.objective ?? "", /Rehearse the opening exchange/);
  assert.equal(rendersAsRest(day), false);
  assert.equal(isZeroLoadSupportSession(session), true);
  assert.equal(getPhysicalSessions(day).length, 0);
  assert.equal(dayCompletion(day).total, 0);
});

test("visualisation sharing a physical day keeps both, counting the day once", () => {
  const day = dayFor(productionPlan, "D-5");

  assert.deepEqual(
    getSessions(day).map((session) => session.title),
    ["Freshness Primer", "Fight Visualisation"],
  );
  assert.deepEqual(
    getPhysicalSessions(day).map((session) => session.title),
    ["Freshness Primer"],
  );
  assert.equal(dayCompletion(day).total, 1);
});

test("low-cost physical support is not demoted to zero load", () => {
  // The planner stamps stress_class "support" on joint prep, footwork
  // walkthroughs and technical shadow rhythm as well as on breathing resets.
  // Support means low cost, not absent movement, so these keep counting.
  for (const countdown of ["D-10", "D-3"]) {
    const day = dayFor(productionPlan, countdown);
    assert.equal(isZeroLoadSupportSession(getSessions(day)[0]), false);
    assert.equal(dayCompletion(day).total, 1);
  }
});

test("Tactical Watch stays visible and contributes nothing physical", () => {
  const day = dayFor(productionPlan, "D-7");
  const session = getSessions(day)[0];

  assert.equal(session?.title, "Tactical Watch");
  assert.equal(session?.blocks?.[0]?.display_name, "Pocket Exchange Map");
  assert.equal(isZeroLoadSupportSession(session), true);
  assert.equal(dayCompletion(day).total, 0);
});

test("coach-led technical combat reconciliation is unchanged", () => {
  const day = dayFor(productionPlan, "D-4");

  assert.deepEqual(getSessions(day), []);
  assert.match(
    day.today_card?.headline ?? "",
    /Technical-only combat/,
  );
  assert.equal(classifySessionlessDay(day).kind, "technical");
  assert.equal(classifySessionlessDay(day).coachLed, true);
});

test("a genuinely empty day still renders as rest", () => {
  const plan = buildStructuredPlanFromText(
    ["D-6 (Friday) — Freshness Primer", "- Band face pull: 2 sets x 12"].join("\n"),
    FIGHT_DATE,
  );
  const empty: StructuredDay = {
    date: "2026-10-11",
    countdown_label: "D-4",
    day_type: "rest",
    sessions: [],
  };

  assert.equal(rendersAsRest(empty), true);
  assert.equal(rendersAsRest(dayFor(plan, "D-6")), false);
});

test("no scheduled D-day is replaced by a synthesized countdown gap row", () => {
  const scheduled = new Set(["D-10", "D-9", "D-8", "D-7", "D-5", "D-4", "D-3", "D-0"]);
  const gapCountdowns = getWeeks(productionPlan)
    .flatMap((week) => buildDayTimeline(getDays(week), true))
    .flatMap((entry) => (entry.kind === "gap" ? [entry.countdown] : []));

  for (const countdown of gapCountdowns) {
    assert.equal(
      scheduled.has(countdown ?? ""),
      false,
      `${countdown} carries scheduled work and must not be a rest row`,
    );
  }
  // D-6 and D-2/D-1 are genuinely unprogrammed, so gap rows still fill them.
  assert.ok(gapCountdowns.includes("D-6"));
});

test("structured_plan = null: the rendered card shows every D-10/D-9 item", () => {
  const markup = renderToStaticMarkup(
    <StructuredPlanRenderer plan={productionPlan} today={new Date("2026-10-06T12:00:00")} />,
  );

  assert.match(markup, /Joint Prep/);
  assert.match(markup, /Breathing Reset/);
  assert.match(markup, /Pressure Step-Cut Reset/);
  assert.match(markup, /Neural Visualisation/);
  // The rest row markup must not appear on the days that carry work: the only
  // rest rows in this week are the genuinely unprogrammed D-6.
  const restRows = markup.split("cm-rest-day").length - 1;
  assert.equal(restRows, 1);
});

test("a coach-led combat day counts as physical training even with no app card", () => {
  const day = dayFor(productionPlan, "D-4");

  assert.deepEqual(getSessions(day), []);
  assert.equal(isCoachLedPhysicalTrainingDay(day), true);
  // Nothing on the day can be logged, so it reads 0/1 rather than disappearing.
  assert.deepEqual(dayCompletion(day), { done: 0, total: 1 });
});

test("fight day and a true rest day are not physical training days", () => {
  assert.equal(isCoachLedPhysicalTrainingDay(dayFor(productionPlan, "D-0")), false);
  assert.equal(
    isCoachLedPhysicalTrainingDay({
      date: "2026-10-11",
      countdown_label: "D-4",
      day_type: "rest",
      sessions: [],
    }),
    false,
  );
});

test("week 1: three physical training days count as /3", () => {
  // D-14 app session, D-12 app session, D-11 coach-led technical combat.
  const plan = buildStructuredPlanFromText(
    [
      "D-14 (Monday) — Neural speed touch",
      "- Trap bar deadlift: 2-3 sets x 3 reps",
      "",
      "D-12 (Wednesday) — Aerobic support",
      "- Easy bike: 20 min",
      "",
      "D-11 (Thursday) — Technical-only combat",
      "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority.",
      "",
      "D-11 (Thursday) — Tactical Focus",
      "- Pocket Exchange Map: 10 minutes, tactical review only. No physical load.",
    ].join("\n"),
    "2026-10-15",
  );
  const week = getWeeks(plan)[0];
  const combatDay = getDays(week).find((day) => day.countdown_label === "D-11");

  // Production shape: the combat day also carries a zero-load Tactical Focus
  // card. The card must not suppress the combat occupancy, and must not add
  // one of its own.
  assert.deepEqual(
    getSessions(combatDay).map((session) => session.title),
    ["Tactical Focus"],
  );
  assert.equal(isCoachLedPhysicalTrainingDay(combatDay), true);
  assert.deepEqual(dayCompletion(combatDay), { done: 0, total: 1 });
  assert.equal(weekCompletion(week).total, 3);
});

test("week 2: five physical training days count as /5", () => {
  // Joint prep, step-cut reset and two primers are app sessions; the technical
  // combat day is coach-owned with no app card. Breathing, visualisation and
  // the tactical card share those days and must not add to the count.
  const plan = buildStructuredPlanFromText(
    [
      "D-10 (Monday) — Joint Prep",
      "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks.",
      "",
      "D-9 (Tuesday) — Breathing Reset",
      "Nasal breathing, 5 minutes, box pattern.",
      "",
      "D-9 (Tuesday) — Pressure Step-Cut Reset",
      "- Pressure Step-Cut Reset: 2 sets x 4 clean reactions each direction, RPE 5.",
      "",
      "D-7 (Thursday) — Freshness Primer",
      "- Band face pull, light: 2 sets x 12 reps, RPE 3-4.",
      "",
      "D-6 (Friday) — Neural Visualisation",
      "Rehearse the opening exchange and composed reset.",
      "",
      "D-5 (Saturday) — Fight-Speed Primer",
      "- Explosive Boxing Burst Intervals: 2-3 x 5-6 sec bursts, RPE 6.",
      "",
      "D-4 (Sunday) — Technical-only combat",
      "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority.",
      "",
      "D-4 (Sunday) — Tactical Cue Card",
      "Write one fight cue only: entry, exit, counter, foot position, or guard reaction.",
    ].join("\n"),
    "2026-10-15",
  );
  const week = getWeeks(plan)[0];
  const physicalDays = getDays(week).filter(
    (day) => getPhysicalSessions(day).length > 0 || isCoachLedPhysicalTrainingDay(day),
  );

  assert.deepEqual(
    physicalDays.map((day) => day.countdown_label),
    ["D-10", "D-9", "D-7", "D-5", "D-4"],
  );
  // D-4 is combat + a zero-load Cue Card: one physical occupancy, not zero and
  // not two.
  const combatDay = getDays(week).find((day) => day.countdown_label === "D-4");
  assert.deepEqual(
    getSessions(combatDay).map((session) => session.title),
    ["Tactical Cue Card"],
  );
  assert.deepEqual(dayCompletion(combatDay), { done: 0, total: 1 });
  assert.equal(weekCompletion(week).total, 5);
});

test("coach contact alongside an app physical session is not double-counted", () => {
  const plan = buildStructuredPlanFromText(
    [
      "D-6 (Wednesday) — Technical-only combat",
      "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority.",
      "",
      "D-6 (Wednesday) — Freshness Primer",
      "- Band face pull, light: 2 sets x 12 reps, RPE 3-4.",
    ].join("\n"),
    "2026-10-15",
  );
  const day = getDays(getWeeks(plan)[0])[0];

  assert.equal(getPhysicalSessions(day).length, 1);
  assert.equal(isCoachLedPhysicalTrainingDay(day), false);
  assert.deepEqual(dayCompletion(day), { done: 0, total: 1 });
});

test("the App completed row stays app-only while the week badge counts combat", () => {
  const week = getWeeks(productionPlan).find((entry) =>
    getDays(entry).some((day) => day.countdown_label === "D-4"),
  );

  // Week badge / day tag: training sessions, coach-owned combat included.
  assert.equal(weekCompletion(week).total, weekCompletion(week, undefined, {}).total);
  // "App completed": app work only, so the coach-led D-4 is not in it.
  assert.equal(
    weekCompletion(week, undefined, { includeCoachLed: false }).total,
    weekCompletion(week).total - 1,
  );
});

test("weekly counters separate physical sessions from zero-load support", () => {
  const week = getWeeks(productionPlan).find((entry) =>
    getDays(entry).some((day) => day.countdown_label === "D-9"),
  );
  const summary = weekSessionSummary(week);

  // D-10 Joint Prep, D-9 Pressure Step-Cut Reset, D-5 Freshness Primer.
  assert.equal(summary.appSessions, 3);
  // D-9 Breathing Reset, D-8 visualisation, D-7 Tactical Watch, D-5 visualisation.
  assert.equal(summary.supportSessions, 4);
  // Every scheduled day is still an active day, support-only ones included.
  assert.equal(summary.trainingDays, 6);
});
