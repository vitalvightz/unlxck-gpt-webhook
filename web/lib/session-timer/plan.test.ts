import test from "node:test";
import assert from "node:assert/strict";

import {
  blockToTimerItem,
  buildTimerItems,
  formatClock,
  formatRange,
  measuredSeconds,
  parseCountRange,
  parseDurationRange,
  sessionTimerItems,
  timerSessionFor,
} from "./plan.ts";
import type { StructuredBlock, StructuredSession } from "../types.ts";

test("measured values convert to seconds and reject unknown units", () => {
  assert.equal(measuredSeconds({ value: 3, unit: "min" }), 180);
  assert.equal(measuredSeconds({ value: 45, unit: "seconds" }), 45);
  assert.equal(measuredSeconds({ value: 90, unit: "s" }), 90);
  assert.equal(measuredSeconds({ value: 400, unit: "m_distance" }), null);
  assert.equal(measuredSeconds({ value: 5, unit: null }), null);
  assert.equal(measuredSeconds({ value: Number.NaN, unit: "s" }), null);
});

test("count and duration ranges parse exact and ranged doses", () => {
  assert.deepEqual(parseCountRange("3-5"), { min: 3, max: 5 });
  assert.deepEqual(parseCountRange("4"), { min: 4, max: 4 });
  assert.equal(parseCountRange("5-3"), null);
  assert.deepEqual(parseDurationRange("90-120 s"), { min: 90, max: 120 });
  assert.deepEqual(parseDurationRange("2-3 min"), { min: 120, max: 180 });
  assert.deepEqual(parseDurationRange("30s"), { min: 30, max: 30 });
  assert.deepEqual(parseDurationRange("1:30"), { min: 90, max: 90 });
  assert.equal(parseDurationRange("easy"), null);
});

test("sparring rounds use the plan's round and rest length", () => {
  const item = blockToTimerItem(
    {
      block_type: "sparring",
      display_name: "Hard sparring",
      rounds: 6,
      work: { value: 3, unit: "min" },
      rest: { value: 60, unit: "seconds" },
    },
    0,
  );
  assert.equal(item?.kind, "interval");
  assert.ok(item?.kind === "interval");
  assert.equal(item.rounds, 6);
  assert.equal(item.workSec, 180);
  assert.equal(item.restSec, 60);
  assert.equal(item.sparring, true);
  assert.equal(item.needsSetup, false);
});

test("a long block duration with rounds is split per round, a short one is per round", () => {
  const total = blockToTimerItem(
    { block_type: "conditioning", display_name: "Bike", rounds: 4, duration: { value: 20, unit: "min" } },
    0,
  );
  assert.ok(total?.kind === "interval");
  assert.equal(total.workSec, 300);
  const perRound = blockToTimerItem(
    { block_type: "conditioning", display_name: "Bag", rounds: 5, duration: { value: 2, unit: "min" } },
    0,
  );
  assert.ok(perRound?.kind === "interval");
  assert.equal(perRound.workSec, 120);
});

test("rounds without a length are flagged for setup instead of silently timed", () => {
  const item = blockToTimerItem({ block_type: "sparring", display_name: "Sparring", rounds: 5 }, 0);
  assert.ok(item?.kind === "interval");
  assert.equal(item.needsSetup, true);
  assert.equal(item.rounds, 5);
});

test("strength sets keep an exact dose and rest", () => {
  const block: StructuredBlock = {
    block_type: "strength",
    display_name: "Trap bar deadlift",
    sets: 4,
    reps: 3,
    rest: { value: 120, unit: "seconds" },
    load: { display: "80% 1RM" },
    effort: { method: "RPE", value: 7 },
  };
  const item = blockToTimerItem(block, 0);
  assert.ok(item?.kind === "sets");
  assert.deepEqual(item.sets, { min: 4, max: 4 });
  assert.deepEqual(item.restSec, { min: 120, max: 120 });
  assert.equal(item.holdSec, null);
  assert.equal(item.detail, "3 reps · 80% 1RM · RPE 7");
});

test("a set and rest range from the source plan stays a range", () => {
  const source = [
    "### D-21",
    "- Trap bar deadlift — 3-5 sets x 3 reps @ RPE 7, rest 90-120 s",
  ].join("\n");
  const item = blockToTimerItem(
    { block_type: "strength", display_name: "Trap bar deadlift", sets: 4, reps: 3 },
    0,
    { sourceText: source, countdown: "D-21" },
  );
  assert.ok(item?.kind === "sets");
  assert.deepEqual(item.sets, { min: 3, max: 5 });
  assert.deepEqual(item.restSec, { min: 90, max: 120 });
});

test("missing sets and rest stay unknown rather than invented", () => {
  const item = blockToTimerItem({ block_type: "accessory", display_name: "Band pull-apart", reps: "15" }, 0);
  assert.ok(item?.kind === "sets");
  assert.equal(item.sets, null);
  assert.equal(item.restSec, null);
});

test("rehab holds become timed sets", () => {
  const fromDuration = blockToTimerItem(
    {
      block_type: "rehab",
      display_name: "Copenhagen plank hold",
      sets: 3,
      reps: 1,
      duration: { value: 20, unit: "seconds" },
      rest: { value: 45, unit: "seconds" },
    },
    0,
  );
  assert.ok(fromDuration?.kind === "sets");
  assert.equal(fromDuration.holdSec, 20);
  const fromReps = blockToTimerItem(
    { block_type: "rehab", display_name: "Wall sit", sets: 2, reps: "30s" },
    0,
  );
  assert.ok(fromReps?.kind === "sets");
  assert.equal(fromReps.holdSec, 30);
});

test("guidance blocks are skipped and dose-less blocks become tasks", () => {
  assert.equal(blockToTimerItem({ block_type: "nutrition", display_name: "Carbs" }, 0), null);
  assert.equal(blockToTimerItem({ block_type: "mindset", display_name: "Visualise" }, 0), null);
  const task = blockToTimerItem({ block_type: "mobility_activation", display_name: "Hip flow" }, 0);
  assert.equal(task?.kind, "task");
  const timed = blockToTimerItem(
    { block_type: "preparation", display_name: "Warm-up", duration: { value: 10, unit: "min" } },
    0,
  );
  assert.ok(timed?.kind === "interval");
  assert.equal(timed.rounds, 1);
  assert.equal(timed.workSec, 600);
});

test("items from several sessions get unique ids", () => {
  const block: StructuredBlock = { block_id: "b1", block_type: "strength", display_name: "Squat", sets: 3, reps: 5 };
  const sessions = [{ blocks: [block] }, { blocks: [block] }] as StructuredSession[];
  const items = buildTimerItems(sessions);
  assert.equal(items.length, 2);
  assert.notEqual(items[0].id, items[1].id);
});

test("formatting helpers", () => {
  assert.equal(formatClock(185), "3:05");
  assert.equal(formatClock(0), "0:00");
  assert.equal(formatRange({ min: 3, max: 5 }), "3–5");
  assert.equal(formatRange({ min: 4, max: 4 }), "4");
});

const LOWER_POWER: StructuredSession = {
  session_id: "s1",
  title: "Lower power",
  blocks: [{ block_type: "strength", display_name: "Trap bar jump", sets: 4, reps: 3 }],
};
const SPRINT: StructuredSession = {
  session_id: "s2",
  title: "Sprint",
  blocks: [
    {
      block_type: "conditioning",
      display_name: "Hill sprints",
      rounds: 6,
      work: { value: 10, unit: "s" },
      rest: { value: 90, unit: "s" },
    },
  ],
};
const TACTICAL_FOCUS: StructuredSession = {
  session_id: "s3",
  title: "Tactical Focus",
  blocks: [{ block_type: "mindset", display_name: "Pocket Exchange Map" }],
};

test("a zero-load Tactical Focus session has no timer items, never generic rounds", () => {
  assert.deepEqual(buildTimerItems([TACTICAL_FOCUS]), []);
  assert.deepEqual(sessionTimerItems([TACTICAL_FOCUS], "s3"), []);
});

test("the timer only ever holds the session being completed", () => {
  const day = [LOWER_POWER, SPRINT, TACTICAL_FOCUS];
  // Start s1: only s1's blocks.
  const first = sessionTimerItems(day, "s1");
  assert.deepEqual(first.map((item) => item.title), ["Trap bar jump"]);
  // s1 completed, the backend advances to s2: only s2's blocks, s1 is not repeated.
  const second = sessionTimerItems(day, "s2");
  assert.deepEqual(second.map((item) => item.title), ["Hill sprints"]);
  // s3 is zero-load: no session timer.
  assert.deepEqual(sessionTimerItems(day, "s3"), []);
});

test("a session that cannot be identified confidently gets no timer", () => {
  assert.equal(timerSessionFor([LOWER_POWER, SPRINT], "missing"), null);
  assert.equal(timerSessionFor([LOWER_POWER, SPRINT], null), null);
  assert.equal(timerSessionFor([LOWER_POWER, { ...SPRINT, session_id: "s1" }], "s1"), null);
  // Several id-less sessions are ambiguous; a lone id-less (legacy) session is not.
  const unnamed = { ...LOWER_POWER, session_id: null };
  assert.equal(timerSessionFor([unnamed, { ...SPRINT, session_id: null }], "2026-09-25"), null);
  assert.equal(timerSessionFor([unnamed], "2026-09-25"), unnamed);
  // A lone session with a different explicit id is not silently adopted.
  assert.equal(timerSessionFor([LOWER_POWER], "s9"), null);
});
