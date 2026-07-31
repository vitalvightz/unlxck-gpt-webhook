import test from "node:test";
import assert from "node:assert/strict";

import {
  formatMilestoneDurationLabel,
  resolveMilestoneDurations,
} from "./generation-milestone-duration";
import type { ProgressMilestone } from "./types";

const START = Date.parse("2026-07-31T10:00:00Z");

function milestone(code: string, offsetSeconds: number): ProgressMilestone {
  return {
    code,
    label: code,
    detail: "",
    at: new Date(START + offsetSeconds * 1000).toISOString(),
  };
}

test("the stage still in flight reports how long it has been running", () => {
  // The feed used to print the stage's start offset ("+1m 06s") and leave it
  // frozen while the stage kept going — next to a total clock that kept
  // climbing, the two readings looked unsynchronised.
  const views = resolveMilestoneDurations([milestone("stage1_done", 0), milestone("stage2_model_call", 66)], {
    nowMs: START + 292_000,
    startedAtMs: START,
  });

  assert.equal(views[1].isRunning, true);
  assert.equal(views[1].durationLabel, "3m 46s");
  assert.equal(formatMilestoneDurationLabel(views[1]), "running for 3m 46s");
  // The start offset is kept as secondary context, not as the headline number.
  assert.equal(views[1].offsetLabel, "+1m 06s");
});

test("a finished stage reports the gap to the milestone that ended it", () => {
  const views = resolveMilestoneDurations(
    [milestone("stage1_done", 0), milestone("stage2_model_call", 66), milestone("plan_saved", 279)],
    { nowMs: START + 600_000, startedAtMs: START },
  );

  assert.equal(views[1].isRunning, false);
  assert.equal(formatMilestoneDurationLabel(views[1]), "3m 33s");
});

test("once the job ends, the last stage freezes on the job's terminal timestamp", () => {
  const views = resolveMilestoneDurations([milestone("stage1_done", 0), milestone("stage2_model_call", 66)], {
    nowMs: START + 3_600_000,
    endedAtMs: START + 345_000,
    startedAtMs: START,
  });

  assert.equal(views[1].isRunning, false);
  assert.equal(formatMilestoneDurationLabel(views[1]), "4m 39s");
});

test("a milestone the backend wrote without a timestamp does not swallow the stage before it", () => {
  const untimed: ProgressMilestone = { code: "no_clock", label: "no_clock", detail: "", at: "" };
  const views = resolveMilestoneDurations([milestone("stage2_model_call", 66), untimed], {
    nowMs: START + 292_000,
    startedAtMs: START,
  });

  // The untimed row cannot end stage 2, so stage 2 is still the running one.
  assert.equal(views[0].isRunning, true);
  assert.equal(views[0].durationLabel, "3m 46s");
  assert.equal(views[1].durationLabel, null);
  assert.equal(formatMilestoneDurationLabel(views[1]), null);
});

test("only the last stage of a live job is running", () => {
  const views = resolveMilestoneDurations(
    [milestone("a", 0), milestone("b", 10), milestone("c", 20)],
    { nowMs: START + 30_000, startedAtMs: START },
  );

  assert.deepEqual(
    views.map((view) => view.isRunning),
    [false, false, true],
  );
});

test("an empty feed produces no rows", () => {
  assert.deepEqual(resolveMilestoneDurations([], { nowMs: START }), []);
});
