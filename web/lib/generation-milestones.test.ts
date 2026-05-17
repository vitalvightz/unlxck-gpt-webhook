import test from "node:test";
import assert from "node:assert/strict";

import { GENERATION_MILESTONES, getGenerationMilestoneView } from "@/lib/generation-milestones";

test("milestones include exactly 20 title/detail entries", () => {
  assert.equal(GENERATION_MILESTONES.length, 20);
  for (const milestone of GENERATION_MILESTONES) {
    assert.ok(milestone.title.length > 0);
    assert.ok(milestone.detail.length > 0);
  }
});

test("queued/running start at early milestone", () => {
  const now = Date.now();
  const queued = getGenerationMilestoneView("queued", now, now);
  const running = getGenerationMilestoneView("running", now, now);
  assert.equal(queued.currentIndex, 0);
  assert.equal(running.currentIndex, 0);
});

test("running never reaches final saving milestone", () => {
  const startedAt = Date.now() - 999_999_999;
  const view = getGenerationMilestoneView("running", startedAt, Date.now());
  assert.ok(view.currentIndex <= 17);
  assert.notEqual(view.current.title, "Saving finished plan");
});

test("completed uses final saving milestone", () => {
  const view = getGenerationMilestoneView("finalizing", Date.now() - 10_000, Date.now());
  assert.equal(view.current.title, "Saving finished plan");
  assert.equal(view.currentIndex, 19);
});

test("failed status does not show active running milestones", () => {
  const view = getGenerationMilestoneView("failed", Date.now() - 10_000, Date.now());
  assert.equal(view.completed.length, 0);
});

test("index never exceeds milestone bounds", () => {
  const view = getGenerationMilestoneView("running", Date.now() - 999_999_999, Date.now());
  assert.ok(view.currentIndex >= 0);
  assert.ok(view.currentIndex < GENERATION_MILESTONES.length);
});
