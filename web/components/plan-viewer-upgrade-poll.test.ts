import test from "node:test";
import assert from "node:assert/strict";

import { startStructuredPlanUpgradePoll } from "./plan-viewer";

type PollDocument = NonNullable<Parameters<typeof startStructuredPlanUpgradePoll>[0]["doc"]>;

function fakeDocument(initial: DocumentVisibilityState = "visible") {
  const target = new EventTarget();
  const state = { visibilityState: initial };
  const doc = {
    get visibilityState() {
      return state.visibilityState;
    },
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
  };
  const setVisibility = (next: DocumentVisibilityState) => {
    state.visibilityState = next;
    target.dispatchEvent(new Event("visibilitychange"));
  };
  return { doc: doc as unknown as PollDocument, setVisibility };
}

const INTERVAL = 2_500;
const WINDOW = 10_000;

async function flush() {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
}

test("upgrade poll fetches on each interval while the tab is visible", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc } = fakeDocument();
  let polls = 0;
  const stop = startStructuredPlanUpgradePoll({
    poll: async () => {
      polls += 1;
    },
    onWindowExpired: () => {},
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  t.mock.timers.tick(INTERVAL);
  await flush();
  t.mock.timers.tick(INTERVAL);
  await flush();

  assert.equal(polls, 2);
  stop();
});

test("upgrade poll never starts a fetch while the previous one is still out", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc } = fakeDocument();
  let polls = 0;
  let release: () => void = () => {};
  const stop = startStructuredPlanUpgradePoll({
    poll: () => {
      polls += 1;
      return new Promise<void>((resolve) => {
        release = resolve;
      });
    },
    onWindowExpired: () => {},
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  t.mock.timers.tick(INTERVAL);
  t.mock.timers.tick(INTERVAL);
  t.mock.timers.tick(INTERVAL);
  await flush();
  assert.equal(polls, 1);

  release();
  await flush();
  t.mock.timers.tick(INTERVAL);
  await flush();
  assert.equal(polls, 2);
  stop();
});

test("upgrade poll is silent while hidden and checks at once on return", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument("hidden");
  let polls = 0;
  const stop = startStructuredPlanUpgradePoll({
    poll: async () => {
      polls += 1;
    },
    onWindowExpired: () => {},
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  t.mock.timers.tick(INTERVAL * 3);
  await flush();
  assert.equal(polls, 0);

  setVisibility("visible");
  await flush();
  assert.equal(polls, 1);
  stop();
});

test("upgrade poll window closes on time while the tab is visible", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc } = fakeDocument();
  let expired = 0;
  const stop = startStructuredPlanUpgradePoll({
    poll: async () => {},
    onWindowExpired: () => {
      expired += 1;
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  t.mock.timers.tick(WINDOW - 1);
  assert.equal(expired, 0);
  t.mock.timers.tick(1);
  assert.equal(expired, 1);
  stop();
});

test("a window that ends while hidden closes only after the return check", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const stop = startStructuredPlanUpgradePoll({
    poll: async () => {
      events.push("poll");
    },
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  setVisibility("hidden");
  t.mock.timers.tick(WINDOW * 2);
  await flush();
  assert.deepEqual(events, []);

  setVisibility("visible");
  await flush();
  assert.deepEqual(events, ["poll", "expired"]);
  stop();
});

test("stopping the upgrade poll ends fetches, expiry and the visibility listener", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  let polls = 0;
  let expired = 0;
  const stop = startStructuredPlanUpgradePoll({
    poll: async () => {
      polls += 1;
    },
    onWindowExpired: () => {
      expired += 1;
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    doc,
  });

  stop();
  t.mock.timers.tick(WINDOW * 2);
  setVisibility("hidden");
  setVisibility("visible");
  await flush();

  assert.equal(polls, 0);
  assert.equal(expired, 0);
});
