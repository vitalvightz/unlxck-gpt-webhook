import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import "./test-dom";
import { act, type ComponentProps } from "react";
import { createRoot } from "react-dom/client";

import { selectLoadingTips } from "../lib/loading-tips";
import type { PlanRequest } from "../lib/types";
import { PublicGenerationScreen } from "./public-generation-screen";

test("public build omits diagnostics and shows leave reassurance", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="running" milestones={[{ code: "designing_camp", label: "Designing your camp", detail: "", at: "" }]} />);
  assert.match(html, /YOUR CAMP IS TAKING SHAPE/);
  assert.match(html, /Safe to leave/);
  for (const privateCopy of ["Job state", "payload", "Stage 1", "model", "Plan activity", "Elapsed"]) assert.ok(!html.includes(privateCopy));
});

test("public failure gives recovery actions without rendering raw errors", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="failed" error="worker traceback: secret" failureKind="job_failed" canRetry onRetry={() => {}} onReturnToWorkspace={() => {}} />);
  assert.match(html, /Try again/);
  assert.match(html, /Return to workspace/);
  assert.ok(!html.includes("traceback"));
});

test("finalizing does not mark the camp ready without server confirmation", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="finalizing" milestones={[{ code: "final_checks", label: "Final checks", detail: "", at: "" }]} />);
  assert.match(html, /aria-valuenow="90"/);
  assert.ok(!html.includes("public-build-milestone-complete\"><span>✓<\/span><div><strong>Camp ready"));
});

// A hand-cranked stand-in for window.setInterval so rotation can be stepped
// deterministically and every interval the screen leaves running is visible.
function installFakeIntervals() {
  const win = window as unknown as Record<string, unknown>;
  const original = { set: win.setInterval, clear: win.clearInterval };
  const live = new Map<number, { delay: number; fn: () => void }>();
  let nextId = 1;
  win.setInterval = (fn: () => void, delay: number) => {
    const id = nextId++;
    live.set(id, { delay, fn });
    return id;
  };
  win.clearInterval = (id: number) => {
    live.delete(id);
  };
  return {
    live: () => [...live.values()].map((entry) => entry.delay),
    fire: (delay: number) => {
      for (const entry of [...live.values()]) if (entry.delay === delay) entry.fn();
    },
    restore: () => {
      win.setInterval = original.set;
      win.clearInterval = original.clear;
    },
  };
}

function mountScreen(props: ComponentProps<typeof PublicGenerationScreen>) {
  window.localStorage.clear();
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(<PublicGenerationScreen {...props} />));
  return {
    rerender: (next: ComponentProps<typeof PublicGenerationScreen>) => act(() => root.render(<PublicGenerationScreen {...next} />)),
    activeTips: () => [...container.querySelectorAll(".public-build-tip-text-active")].map((node) => node.textContent ?? ""),
    tipBox: () => container.querySelector(".public-build-tip"),
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

const INJURY_INTAKE = {
  athlete: { technical_style: ["boxing"] },
  fight_date: "2099-01-01",
  equipment_access: [],
  training_availability: [],
  hard_sparring_days: [],
  support_work_days: [],
  key_goals: [],
  weak_areas: [],
  injuries: "left shoulder strain",
} as unknown as PlanRequest;

const running = { phase: "running" as const, startedAtMs: Date.now(), milestones: [] };

test("one tip shows immediately, rotates every 7s, and a 10-minute build never repeats a tip", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const screen = mountScreen(running);
  const shown = [...screen.activeTips()];
  assert.equal(shown.length, 1);
  // 10 minutes at one tip per 7 seconds.
  for (let step = 0; step < 86; step += 1) {
    act(() => timers.fire(7_000));
    const current = screen.activeTips();
    assert.equal(current.length, 1);
    shown.push(current[0]);
  }
  assert.equal(new Set(shown).size, shown.length);
  screen.unmount();
});

test("the next build opens on tips this athlete has not seen yet", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const first = mountScreen(running);
  const seen = [...first.activeTips()];
  for (let step = 0; step < 20; step += 1) {
    act(() => timers.fire(7_000));
    seen.push(first.activeTips()[0]);
  }
  first.unmount();
  const stored = window.localStorage.getItem("unlxck:loading-tips-seen");
  // Mount again without clearing storage, as a returning athlete would.
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  window.localStorage.setItem("unlxck:loading-tips-seen", stored ?? "[]");
  act(() => root.render(<PublicGenerationScreen {...running} />));
  const reopened: string[] = [];
  for (let step = 0; step < 20; step += 1) {
    reopened.push(container.querySelector(".public-build-tip-text-active")?.textContent ?? "");
    act(() => timers.fire(7_000));
  }
  act(() => root.unmount());
  container.remove();
  assert.ok(reopened.every((tip) => !seen.includes(tip)));
});

test("tips follow the intake: an injured athlete gets recovery and safety tips", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const allowed = new Set(selectLoadingTips(INJURY_INTAKE).map((tip) => tip.text));
  const screen = mountScreen({ ...running, intake: INJURY_INTAKE });
  for (let step = 0; step < 30; step += 1) {
    assert.ok(allowed.has(screen.activeTips()[0]));
    act(() => timers.fire(7_000));
  }
  screen.unmount();
});

test("rotation stops once the build finishes, and nothing is left running on unmount", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const screen = mountScreen(running);
  assert.ok(timers.live().includes(7_000));

  screen.rerender({ ...running, phase: "finalizing" });
  assert.ok(!timers.live().includes(7_000));
  const frozen = screen.activeTips();
  act(() => timers.fire(7_000));
  assert.deepEqual(screen.activeTips(), frozen);

  screen.unmount();
  assert.deepEqual(timers.live(), []);
});

test("unmounting mid-build clears the tip and clock intervals", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const screen = mountScreen(running);
  assert.deepEqual([...timers.live()].sort(), [1_000, 7_000]);
  screen.unmount();
  assert.deepEqual(timers.live(), []);
});

test("terminal states show no tip and start no rotation", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  for (const phase of ["failed", "review_paused", "already_generated"] as const) {
    const screen = mountScreen({ phase, startedAtMs: Date.now() });
    assert.equal(screen.tipBox(), null, phase);
    assert.ok(!timers.live().includes(7_000), phase);
    screen.unmount();
  }
});

test("server render reserves the tip box but leaves the shuffled pick to the client", () => {
  const html = renderToStaticMarkup(<PublicGenerationScreen phase="running" />);
  assert.match(html, /public-build-tip-stack/);
  assert.ok(!html.includes("public-build-tip-text-active"));
});

test("a refreshed but equivalent intake keeps the current tip", (t) => {
  const timers = installFakeIntervals();
  t.after(timers.restore);
  const screen = mountScreen({ ...running, intake: INJURY_INTAKE });
  act(() => timers.fire(7_000));
  const before = screen.activeTips();
  for (let i = 0; i < 10; i += 1) {
    screen.rerender({ ...running, intake: { ...INJURY_INTAKE } });
    assert.deepEqual(screen.activeTips(), before);
  }
  screen.unmount();
});
