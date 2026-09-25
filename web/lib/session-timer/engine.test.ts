import test from "node:test";
import assert from "node:assert/strict";

import {
  addTime,
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

test("a set range: rest to the minimum, optional window to the maximum, finish once the minimum is met", () => {
  let step = startItem(createTimerState([SQUAT, MOBILITY]), T0);
  assert.deepEqual(step.events, ["set_start"]);
  assert.equal(viewAt(step.state, T0).remainingMs, null);

  step = completeSet(step.state, T0 + 30_000);
  assert.deepEqual(step.events, ["rest_start"]);
  assert.equal(step.state.phase, "rest");
  assert.equal(step.state.phaseMs, 90_000);

  step = advance(step.state, T0 + 120_000);
  assert.deepEqual(step.events, ["rest_end", "set_start"]);
  assert.equal(step.state.phase, "work");
  assert.equal(step.state.unit, 2);
  assert.equal(viewAt(step.state, T0 + 120_000).windowRemainingMs, 30_000);

  step = advance(step.state, T0 + 150_000);
  assert.deepEqual(step.events, ["window_closed"]);
  assert.equal(soundForEvents(step.events), "soft_chime");

  step = completeSet(step.state, T0 + 160_000);
  step = skipRest(step.state, T0 + 170_000);
  step = completeSet(step.state, T0 + 200_000);
  assert.deepEqual(step.state.completed, [3, 0]);
  assert.equal(step.state.phase, "rest");

  step = finishItem(step.state, T0 + 205_000);
  assert.deepEqual(step.events, ["item_complete"]);
  assert.equal(step.state.index, 1);
  assert.equal(step.state.phase, "ready");
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
  // Not adjustable once running.
  const running = startItem(state, T0).state;
  assert.equal(updateIntervalItem(running, { rounds: 9 }), running);
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
