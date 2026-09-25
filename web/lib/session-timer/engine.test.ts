import test from "node:test";
import assert from "node:assert/strict";

import {
  addTime,
  adjustItem,
  advance,
  completeSet,
  createTimerState,
  crossedCues,
  endRound,
  endSession,
  finishItem,
  metPlan,
  pause,
  resume,
  setRestLength,
  skipRest,
  soundForEvents,
  startItem,
  summarizeRun,
  updateIntervalItem,
  viewAt,
} from "./engine.ts";
import type { IntervalItem, SetsItem, TaskItem } from "./plan.ts";

const ROUNDS: IntervalItem = {
  kind: "interval",
  id: "spar",
  title: "Sparring",
  detail: null,
  blockType: "sparring",
  rounds: 3,
  workSec: 180,
  restSec: 60,
  sparring: true,
  needsSetup: false,
};

const SQUAT: SetsItem = {
  kind: "sets",
  id: "squat",
  title: "Back squat",
  detail: "5 reps",
  blockType: "strength",
  sets: { min: 3, max: 5 },
  holdSec: null,
  restSec: { min: 90, max: 120 },
};

const HOLD: SetsItem = {
  kind: "sets",
  id: "hold",
  title: "Plank hold",
  detail: null,
  blockType: "rehab",
  sets: { min: 2, max: 2 },
  holdSec: 30,
  restSec: { min: 30, max: 30 },
};

const MOBILITY: TaskItem = { kind: "task", id: "mob", title: "Hip flow", detail: null, blockType: null };

const T0 = 1_000_000;

test("rounds run work, rest, work and finish on the last bell", () => {
  let step = startItem(createTimerState([ROUNDS]), T0);
  assert.deepEqual(step.events, ["round_start"]);
  assert.equal(step.state.phase, "work");

  step = advance(step.state, T0 + 179_000);
  assert.equal(step.events.length, 0);
  assert.equal(viewAt(step.state, T0 + 179_000).remainingMs, 1_000);

  step = advance(step.state, T0 + 180_000);
  assert.deepEqual(step.events, ["round_end", "rest_start"]);
  assert.equal(step.state.phase, "rest");
  assert.equal(step.state.unit, 2);

  step = advance(step.state, T0 + 240_000);
  assert.deepEqual(step.events, ["round_start"]);
  assert.equal(step.state.phase, "work");

  // Phone locked through round 2, rest and round 3: one advance replays all of it.
  step = advance(step.state, T0 + 10_000_000);
  assert.equal(step.state.phase, "done");
  assert.deepEqual(step.state.completed, [3]);
  assert.ok(step.events.includes("session_complete"));
  assert.equal(soundForEvents(step.events), "finish");
});

test("pause freezes the clock and resume shifts the phase", () => {
  let state = startItem(createTimerState([ROUNDS]), T0).state;
  state = pause(state, T0 + 60_000);
  assert.equal(advance(state, T0 + 500_000).state, state);
  assert.equal(viewAt(state, T0 + 500_000).remainingMs, 120_000);
  state = resume(state, T0 + 500_000);
  assert.equal(viewAt(state, T0 + 500_000).remainingMs, 120_000);
  assert.equal(advance(state, T0 + 619_000).state.phase, "work");
  assert.equal(advance(state, T0 + 620_000).state.phase, "rest");
});

test("+30s and end round", () => {
  let state = startItem(createTimerState([ROUNDS]), T0).state;
  state = addTime(state, 30);
  assert.equal(viewAt(state, T0).remainingMs, 210_000);
  const ended = endRound(state, T0 + 5_000);
  assert.deepEqual(ended.events, ["round_end", "rest_start"]);
  assert.deepEqual(ended.state.completed, [1]);
});

test("a set range: rest stays rest until the athlete starts the set, finish once the minimum is met", () => {
  let step = startItem(createTimerState([SQUAT, MOBILITY]), T0);
  assert.deepEqual(step.events, ["set_start"]);
  assert.equal(viewAt(step.state, T0).remainingMs, null);

  step = completeSet(step.state, T0 + 30_000);
  assert.deepEqual(step.events, ["rest_start"]);
  assert.equal(step.state.phase, "rest");
  // The rest runs to its maximum; the minimum is only a "ready" signal.
  assert.equal(step.state.phaseMs, 120_000);
  assert.equal(viewAt(step.state, T0 + 30_000).readyRemainingMs, 90_000);

  step = advance(step.state, T0 + 120_000);
  assert.deepEqual(step.events, ["rest_ready"]);
  assert.equal(soundForEvents(step.events), "soft_chime");
  assert.equal(step.state.phase, "rest");
  assert.equal(step.state.unit, 2);
  assert.equal(viewAt(step.state, T0 + 120_000).readyRemainingMs, 0);
  assert.equal(viewAt(step.state, T0 + 120_000).remainingMs, 30_000);

  // Still resting 20 s later: nothing has started behind the athlete's back.
  step = advance(step.state, T0 + 140_000);
  assert.deepEqual(step.events, []);
  assert.equal(step.state.phase, "rest");

  step = skipRest(step.state, T0 + 145_000);
  assert.deepEqual(step.events, ["set_start"]);
  assert.equal(step.state.phase, "work");
  assert.equal(step.state.phaseStartedAt, T0 + 145_000);

  step = completeSet(step.state, T0 + 160_000);
  // Set 3 only unlocks once the 90 s minimum has passed.
  step = skipRest(step.state, T0 + 250_000);
  step = completeSet(step.state, T0 + 280_000);
  assert.deepEqual(step.state.completed, [3, 0]);
  assert.equal(step.state.phase, "rest");

  step = finishItem(step.state, T0 + 285_000);
  assert.deepEqual(step.events, ["item_complete"]);
  assert.equal(step.state.index, 1);
  assert.equal(step.state.phase, "ready");
});

test("a ranged rest refuses Start set before its minimum and accepts it after", () => {
  let state = startItem(createTimerState([SQUAT]), T0).state;
  state = completeSet(state, T0).state;
  // 90-120 s rest: a tap at +30 s is refused and the athlete keeps resting.
  const early = skipRest(state, T0 + 30_000);
  assert.equal(early.state, state);
  assert.deepEqual(early.events, []);
  assert.equal(early.state.phase, "rest");
  // A tap at +100 s (inside the range) starts the next set.
  const late = skipRest(advance(state, T0 + 100_000).state, T0 + 100_000);
  assert.deepEqual(late.events, ["set_start"]);
  assert.equal(late.state.phase, "work");
  assert.equal(late.state.unit, 2);
  // Even before a tick announces "ready", a tap past the minimum is accepted.
  assert.equal(skipRest(state, T0 + 95_000).state.phase, "work");
});

test("a ranged rest starts the next set by itself only at its maximum", () => {
  let step = startItem(createTimerState([SQUAT]), T0);
  step = completeSet(step.state, T0 + 10_000);
  step = advance(step.state, T0 + 10_000 + 120_000);
  assert.deepEqual(step.events, ["rest_ready", "rest_end", "set_start"]);
  assert.equal(step.state.phase, "work");
  assert.equal(step.state.phaseStartedAt, T0 + 130_000);
});

test("timed holds with a 90-120 s rest: no hold starts or finishes inside the rest range", () => {
  const hold: SetsItem = { ...HOLD, sets: { min: 3, max: 3 }, holdSec: 20, restSec: { min: 90, max: 120 } };
  let step = startItem(createTimerState([hold]), T0);
  step = advance(step.state, T0 + 20_000);
  assert.deepEqual(step.events, ["hold_end", "rest_start"]);
  assert.deepEqual(step.state.completed, [1]);
  const restStart = T0 + 20_000;

  // At the minimum: ready, but the next hold has not started.
  step = advance(step.state, restStart + 90_000);
  assert.deepEqual(step.events, ["rest_ready"]);
  assert.equal(step.state.phase, "rest");

  // Where the old behaviour had already run and logged a whole hold.
  step = advance(step.state, restStart + 110_000);
  assert.deepEqual(step.events, []);
  assert.equal(step.state.phase, "rest");
  assert.deepEqual(step.state.completed, [1]);

  // The maximum runs out: only now does hold 2 begin, and it runs its full 20 s.
  step = advance(step.state, restStart + 120_000);
  assert.deepEqual(step.events, ["rest_end", "hold_start"]);
  assert.equal(viewAt(step.state, restStart + 120_000).remainingMs, 20_000);
  assert.deepEqual(step.state.completed, [1]);

  // Tapping Start set inside the range begins the hold at the tap.
  let tapped = startItem(createTimerState([hold]), T0);
  tapped = advance(tapped.state, T0 + 20_000);
  tapped = skipRest(advance(tapped.state, restStart + 100_000).state, restStart + 100_000);
  assert.equal(skipRest(advance(tapped.state, restStart).state, restStart + 30_000).events.length, 0);
  assert.deepEqual(tapped.events, ["hold_start"]);
  assert.equal(viewAt(tapped.state, restStart + 100_000).remainingMs, 20_000);
});

test("pausing a ranged rest shifts both its minimum and maximum", () => {
  let state = completeSet(startItem(createTimerState([SQUAT]), T0).state, T0).state;
  state = pause(state, T0 + 30_000);
  state = resume(state, T0 + 90_000);
  assert.deepEqual(advance(state, T0 + 140_000).events, []);
  assert.deepEqual(advance(state, T0 + 150_000).events, ["rest_ready"]);
});

test("hitting the set maximum moves straight to the next item", () => {
  let state = startItem(createTimerState([{ ...SQUAT, restSec: null }, MOBILITY]), T0).state;
  for (let set = 1; set <= 5; set += 1) {
    state = completeSet(state, T0 + set * 1000).state;
    if (set < 5) {
      assert.equal(state.phase, "rest");
      // No rest in the plan: the rest is untimed until a preset is picked.
      assert.equal(state.phaseMs, null);
      state = skipRest(state, T0 + set * 1000 + 500).state;
    }
  }
  assert.equal(state.index, 1);
  assert.equal(state.phase, "ready");
});

test("an untimed rest can be given a preset length", () => {
  let state = startItem(createTimerState([{ ...SQUAT, restSec: null }]), T0).state;
  state = completeSet(state, T0 + 1_000).state;
  state = setRestLength(state, 90, T0 + 2_000);
  assert.equal(viewAt(state, T0 + 2_000).remainingMs, 90_000);
  assert.equal(advance(state, T0 + 92_000).state.phase, "work");
});

test("timed holds end themselves and rest between sets", () => {
  let step = startItem(createTimerState([HOLD]), T0);
  assert.deepEqual(step.events, ["hold_start"]);
  step = advance(step.state, T0 + 30_000);
  assert.deepEqual(step.events, ["hold_end", "rest_start"]);
  step = advance(step.state, T0 + 60_000);
  assert.deepEqual(step.events, ["rest_end", "hold_start"]);
  step = advance(step.state, T0 + 90_000);
  assert.equal(step.state.phase, "done");
  assert.ok(metPlan(step.state));
});

test("ready-screen adjustments clamp and clear the setup flag", () => {
  const state = createTimerState([{ ...ROUNDS, needsSetup: true }]);
  const next = updateIntervalItem(state, { rounds: 0, workSec: 2, restSec: -5 });
  const item = next.items[0];
  assert.ok(item.kind === "interval");
  assert.equal(item.rounds, 1);
  assert.equal(item.workSec, 5);
  assert.equal(item.restSec, 0);
  assert.equal(item.needsSetup, false);
});

test("mid-round adjustments apply to the running phase and never erase done work", () => {
  let state = startItem(createTimerState([ROUNDS]), T0).state;
  // Coach calls 2-minute rounds 30 s into round 1.
  state = adjustItem(state, { workSec: 120 });
  assert.equal(viewAt(state, T0 + 30_000).remainingMs, 90_000);
  state = advance(state, T0 + 120_000).state;
  assert.equal(state.phase, "rest");
  // Shorter rest, applied to the rest already running.
  state = adjustItem(state, { restSec: 30 });
  assert.equal(viewAt(state, T0 + 120_000).remainingMs, 30_000);
  // Rounds cannot drop below the round that is already under way.
  state = adjustItem(state, { rounds: 1 });
  const item = state.items[0];
  assert.ok(item.kind === "interval");
  assert.equal(item.rounds, 2);
});

test("set adjustments make the target and rest exact, even mid-rest", () => {
  let state = startItem(createTimerState([SQUAT]), T0).state;
  state = completeSet(state, T0).state;
  state = completeSet(skipRest(state, T0 + 100_000).state, T0 + 110_000).state;
  // Two sets done: the target can't go below that.
  state = adjustItem(state, { sets: 1, restSec: 60 });
  const item = state.items[0];
  assert.ok(item.kind === "sets");
  assert.deepEqual(item.sets, { min: 2, max: 2 });
  assert.deepEqual(item.restSec, { min: 60, max: 60 });
  // The running rest is now an exact 60 s with no separate minimum.
  assert.equal(state.readyAt, null);
  assert.equal(viewAt(state, T0 + 110_000).remainingMs, 60_000);
  assert.equal(adjustItem(state, { restSec: 5 }).items[0].kind === "sets" &&
    (adjustItem(state, { restSec: 5 }).items[0] as SetsItem).restSec?.min, 15);
});

test("warning cues: clapper at ten seconds of work, 3-2-1 at the end of rest", () => {
  assert.deepEqual(crossedCues("work", 180_000, 10_100, 9_900), ["ten_seconds"]);
  assert.deepEqual(crossedCues("work", 20_000, 10_100, 9_900), []);
  assert.deepEqual(crossedCues("rest", 60_000, 3_050, 2_950), ["count_3"]);
  assert.deepEqual(crossedCues("rest", 60_000, 1_050, 950), ["count_1"]);
  assert.deepEqual(crossedCues("rest", 60_000, null, 950), []);
});

test("ending early is not a met plan, and the summary records what was done", () => {
  let state = startItem(createTimerState([ROUNDS, SQUAT, MOBILITY]), T0).state;
  state = advance(state, T0 + 180_000).state;
  state = finishItem(state, T0 + 181_000).state;
  state = startItem(state, T0 + 200_000).state;
  state = completeSet(state, T0 + 230_000).state;
  state = endSession(state, T0 + 240_000);
  assert.equal(state.phase, "done");
  assert.equal(metPlan(state), false);
  assert.equal(summarizeRun(state), "Timer: Sparring: 1/3 rounds · Back squat: 1 set (plan 3–5)");
});
