import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import "./test-dom";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";

import { ToastProvider, useToast, useToastIdle } from "./toast-provider";

type ToastApi = ReturnType<typeof useToast>;

// jsdom owns window.setTimeout, so route it through the Node globals that
// mock.timers replaces.
function useMockClock(t: TestContext) {
  const originalSet = window.setTimeout;
  const originalClear = window.clearTimeout;
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  window.setTimeout = ((handler: () => void, ms?: number) => globalThis.setTimeout(handler, ms)) as typeof window.setTimeout;
  window.clearTimeout = ((id?: number) => globalThis.clearTimeout(id)) as typeof window.clearTimeout;
  t.after(() => {
    window.setTimeout = originalSet;
    window.clearTimeout = originalClear;
  });
  return (ms: number) => act(() => t.mock.timers.tick(ms));
}

function Probe({ onRender }: { onRender: (api: ToastApi, idle: boolean) => void }) {
  const api = useToast();
  const idle = useToastIdle();
  useEffect(() => onRender(api, idle));
  return null;
}

async function mount() {
  const latest: { api: ToastApi | null; idle: boolean } = { api: null, idle: true };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<ToastProvider><Probe onRender={(api, idle) => { latest.api = api; latest.idle = idle; }} /></ToastProvider>));
  return {
    api: () => latest.api!,
    idle: () => latest.idle,
    toasts: () => Array.from(container.querySelectorAll(".toast")),
    texts: () => Array.from(container.querySelectorAll(".toast-message")).map((node) => node.textContent),
    cleanup: () => { act(() => root.unmount()); container.remove(); },
  };
}

test("toasts stagger in and never show more than two at once", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    act(() => {
      ui.api().showToast("One");
      ui.api().showToast("Two");
      ui.api().showToast("Three");
    });
    assert.deepEqual(ui.texts(), ["One"]);
    tick(400);
    assert.deepEqual(ui.texts(), ["One", "Two"]);
    tick(1_000);
    assert.deepEqual(ui.texts(), ["One", "Two"], "third waits for a free slot");
    // "One" expires at 4.5s, exits, then "Three" takes its place.
    tick(3_100);
    assert.ok(ui.toasts()[0].classList.contains("is-leaving"));
    tick(220);
    assert.deepEqual(ui.texts(), ["Two", "Three"]);
  } finally {
    ui.cleanup();
  }
});

test("dismissing plays the exit before the toast leaves the DOM", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    let id = 0;
    act(() => { id = ui.api().showToast("Saved.", { tone: "success" }); });
    act(() => ui.api().dismissToast(id));
    assert.equal(ui.toasts().length, 1);
    assert.ok(ui.toasts()[0].classList.contains("is-leaving"));
    assert.equal(ui.idle(), false);
    tick(220);
    assert.equal(ui.toasts().length, 0);
    assert.equal(ui.idle(), true);
  } finally {
    ui.cleanup();
  }
});

test("an exiting toast keeps its slot until it leaves the DOM", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    let first = 0;
    act(() => {
      first = ui.api().showToast("One");
      ui.api().showToast("Two");
    });
    tick(400);
    tick(1_000); // well past the stagger, so only the slot limit holds "Three" back
    act(() => ui.api().dismissToast(first));
    tick(100);
    act(() => { ui.api().showToast("Three"); }); // arrives mid-exit
    tick(119);
    assert.equal(ui.toasts().length, 2, "never three on screen while one exits");
    assert.deepEqual(ui.texts(), ["One", "Two"]);
    tick(1);
    assert.deepEqual(ui.texts(), ["Two", "Three"]);
  } finally {
    ui.cleanup();
  }
});

test("a delayed reward folds into the confirmation it follows", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    act(() => { ui.api().showToast("Sparring logged.", { tone: "success", mergeKeys: ["training_logged"] }); });
    act(() => {
      ui.api().showToast("+25 XP: Session complete", {
        tone: "success",
        delayMs: 500,
        merge: { suffix: "+25 XP", keys: ["training_logged"] },
      });
    });
    tick(499);
    assert.deepEqual(ui.texts(), ["Sparring logged."]);
    tick(1);
    assert.deepEqual(ui.texts(), ["Sparring logged · +25 XP"]);
    // The merge restarts the read time from the moment the reward lands.
    tick(4_400);
    assert.equal(ui.toasts().length, 1);
    assert.equal(ui.toasts()[0].classList.contains("is-leaving"), false);
  } finally {
    ui.cleanup();
  }
});

test("a reward with nothing recent to join shows on its own", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    act(() => { ui.api().showToast("Could not save.", { tone: "error" }); });
    act(() => {
      ui.api().showToast("+10 XP: Check-in", {
        tone: "success",
        delayMs: 500,
        merge: { suffix: "+10 XP", keys: ["readiness_checkin_completed"] },
      });
    });
    tick(500);
    assert.deepEqual(ui.texts(), ["Could not save.", "+10 XP: Check-in"]);
  } finally {
    ui.cleanup();
  }
});

test("a reward only joins the confirmation of the action that earned it", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    act(() => {
      ui.api().showToast("Check-in saved.", { tone: "success", mergeKeys: ["readiness_checkin_completed"] });
      ui.api().showToast("Weigh-in saved.", { tone: "success" });
    });
    tick(400);
    // The most recent success toast is the weigh-in, but the reward is the check-in's.
    act(() => {
      ui.api().showToast("+10 XP: Check-in complete", {
        tone: "success",
        delayMs: 500,
        merge: { suffix: "+10 XP", keys: ["readiness_checkin_completed"] },
      });
    });
    tick(500);
    assert.deepEqual(ui.texts(), ["Check-in saved · +10 XP", "Weigh-in saved."]);
  } finally {
    ui.cleanup();
  }
});

test("a reward never joins a confirmation that did not opt in", async (t) => {
  const tick = useMockClock(t);
  const ui = await mount();
  try {
    act(() => { ui.api().showToast("Weigh-in saved.", { tone: "success" }); });
    act(() => {
      ui.api().showToast("+25 XP: Session complete", {
        tone: "success",
        delayMs: 500,
        merge: { suffix: "+25 XP", keys: ["training_logged"] },
      });
    });
    tick(500);
    assert.deepEqual(ui.texts(), ["Weigh-in saved.", "+25 XP: Session complete"]);
  } finally {
    ui.cleanup();
  }
});
