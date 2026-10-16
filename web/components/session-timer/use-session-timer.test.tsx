import "../test-dom";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { endSession, pause, resume, startItem } from "@/lib/session-timer/engine";
import { timerAudio } from "@/lib/session-timer/audio";
import { freeRoundsItem } from "@/lib/session-timer/contact";
import { useSessionTimer, type SessionTimerController } from "./use-session-timer";

test("a running minimised timer retains one wake lock, reacquires after hiding, and releases on finish", async () => {
  window.localStorage.clear();
  const locks: Array<{ released: boolean; release: () => Promise<void> }> = [];
  Object.defineProperty(navigator, "wakeLock", { configurable: true, value: {
    request: async () => {
      const lock = { released: false, release: async () => { lock.released = true; } };
      locks.push(lock);
      return lock;
    },
  } });
  let controller: SessionTimerController;
  function Probe({ visible }: { visible: boolean }) {
    controller = useSessionTimer({ items: [freeRoundsItem()], storageKey: "wake-test", audible: visible });
    return null;
  }
  const node = document.createElement("div");
  const root = createRoot(node);
  try {
    await act(async () => root.render(<Probe visible />));
    assert.equal(locks.length, 1);
    await act(async () => controller.run(startItem));
    await act(async () => root.render(<Probe visible={false} />));
    assert.equal(locks[0].released, false, "minimising during work must not release the screen lock");
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    assert.equal(locks.length, 1, "visible events must not acquire duplicate locks");
    // Browsers automatically release the lock when a page becomes hidden.
    locks[0].released = true;
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    assert.equal(locks.length, 2);
    await act(async () => controller.update(pause));
    assert.equal(locks[1].released, true);
    await act(async () => controller.update(resume));
    assert.equal(locks.length, 3);
    await act(async () => controller.update(endSession));
    assert.equal(locks[2].released, true);
  } finally {
    await act(async () => root.unmount());
    Reflect.deleteProperty(navigator, "wakeLock");
    window.localStorage.clear();
  }
});

test("returning after several suspended rounds catches up without ringing old bells", async () => {
  window.localStorage.clear();
  const realNow = Date.now;
  let now = 1000;
  Date.now = () => now;
  const audio = timerAudio();
  const realPlay = audio.play;
  const played: string[] = [];
  audio.play = (sound) => { played.push(sound); };
  let controller: SessionTimerController;
  function Probe() {
    controller = useSessionTimer({ items: [{ ...freeRoundsItem(), rounds: 3, workSec: 5, restSec: 2 }], storageKey: "sleep-test", audible: true });
    return null;
  }
  const root = createRoot(document.createElement("div"));
  try {
    await act(async () => root.render(<Probe />));
    await act(async () => controller.run(startItem));
    assert.deepEqual(played, ["bell"]);
    played.length = 0;
    now = 17_000; // Round 3 began at 15,000; round 1/2 bells are stale.
    await act(async () => window.dispatchEvent(new Event("pageshow")));
    assert.equal(controller!.state.unit, 3);
    assert.deepEqual(controller!.state.completed, [2]);
    assert.deepEqual(played, []);
  } finally {
    await act(async () => root.unmount());
    Date.now = realNow;
    audio.play = realPlay;
    window.localStorage.clear();
  }
});
