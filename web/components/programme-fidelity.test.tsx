// Actual anonymised backend replay, not hand-authored training assignments.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import "./test-dom";
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { ExerciseRow, StructuredPlanRenderer } from "./structured-plan-renderer";
import { blockToTimerItem } from "@/lib/session-timer/plan";
import { doseFromBlock } from "@/lib/exercise-dose";
import { logFieldsForBlock } from "@/lib/exercise-log";
import { getDays, getSessions, getWeeks } from "@/lib/structured-plan";
import type { StructuredPlan } from "@/lib/types";

const plan = JSON.parse(readFileSync(new URL("../test/fixtures/programme-fidelity-card.json", import.meta.url), "utf8")) as StructuredPlan;
const days = getWeeks(plan).flatMap(getDays);
const dayAt = (offset: number) => {
  const day = days.find((d) => d.countdown_label === `D-${offset}`);
  assert.ok(day);
  return day;
};
const blockAt = (offset: number, name: string) => {
  const block = getSessions(dayAt(offset)).flatMap((s) => s.blocks ?? []).find((b) => b.display_name === name);
  assert.ok(block);
  return block;
};

test("the real programme renders all four hard-sparring appointments on Saturday", () => {
  for (const offset of [42, 35, 28, 21]) {
    const day = dayAt(offset);
    const week = getWeeks(plan).find((w) => getDays(w).includes(day))!;
    const html = renderToStaticMarkup(<StructuredPlanRenderer plan={{ ...plan, weeks: [{ ...week, days: [day] }] }} />);
    assert.match(html, /Hard sparring/i);
    assert.ok(html.includes(`D-${offset}`));
    assert.match(html, />Sat\b/);
  }
  for (const offset of [40, 26]) {
    assert.equal(dayAt(offset).weekday, "Mon");
  }
});

test("actual bag, lifting and hold prescriptions reach timer and logging controls", () => {
  const bag = blockAt(15, "Max-Power Bag Burst");
  const timer = blockToTimerItem(bag, 0);
  assert.ok(timer?.kind === "interval");
  assert.equal(timer.rounds, 8);
  assert.equal(timer.workSec, 5);
  assert.equal(timer.restSec, 60);
  assert.equal(timer.needsSetup, false);
  const draft = doseFromBlock(bag);
  assert.equal(draft.mode, "intervals");
  assert.equal(draft.rpe, 8);
  assert.equal(draft.rest_seconds, 60);
  const fields = logFieldsForBlock(bag);
  assert.equal(fields.find((f) => f.key === "rounds")?.hint, "8");
  assert.equal(fields.find((f) => f.key === "work")?.hint, "5");
  const thruster = blockToTimerItem(blockAt(33, "Barbell Thruster"), 1);
  assert.ok(thruster?.kind === "sets");
  assert.deepEqual(thruster.sets, { min: 4, max: 4 });
  assert.deepEqual(thruster.restSec, { min: 120, max: 120 });
  const hold = blockToTimerItem(blockAt(44, "Staggered Stance Hold"), 2);
  assert.ok(hold?.kind === "sets");
  assert.equal(hold.holdSec, 20);
  assert.deepEqual(hold.sets, { min: 2, max: 2 });
});

test("expanding the actual bag row reveals its exact dose and authored coaching cue", async () => {
  const bag = blockAt(15, "Max-Power Bag Burst");
  function Row() {
    const [open, setOpen] = useState(false);
    return <ExerciseRow block={bag} open={open} onToggle={() => setOpen((value) => !value)} />;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => { root.render(<Row />); });
    const toggle = container.querySelector<HTMLButtonElement>('button[aria-expanded="false"]');
    assert.ok(toggle);
    await act(async () => { toggle.dispatchEvent(new window.MouseEvent("click", { bubbles: true })); });
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.match(container.textContent ?? "", /Stop the burst if punch speed, shape or head position drops/);
    assert.match(container.textContent ?? "", /Rounds8/);
    assert.match(container.textContent ?? "", /Work5\s*(?:sec|s)/);
    assert.match(container.textContent ?? "", /Rest1 min/); // The UI formats 60 seconds as one minute.
  } finally {
    await act(async () => { root.unmount(); });
    container.remove();
  }
});
