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
// Longer than any stretch the ordinary tests advance, so only the hang tests
// reach it.
const FETCH_TIMEOUT = 60_000;

async function flush() {
  for (let i = 0; i < 20; i += 1) {
    await Promise.resolve();
  }
}

/** A poll whose fetches finish only when the test says so. */
function controlledPoll(events: string[]) {
  const finishers: Array<() => void> = [];
  let started = 0;
  const poll = () => {
    started += 1;
    const n = started;
    events.push(`start ${n}`);
    return new Promise<void>((resolve) => {
      finishers[n] = () => {
        events.push(`end ${n}`);
        resolve();
      };
    });
  };
  return { poll, finish: (n: number) => finishers[n]() };
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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

test("a fetch still out from before the tab was hidden does not count as the return check", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const { poll, finish } = controlledPoll(events);
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: FETCH_TIMEOUT,
    doc,
  });

  t.mock.timers.tick(INTERVAL);
  await flush();
  setVisibility("hidden");
  t.mock.timers.tick(WINDOW * 2);
  setVisibility("visible");
  await flush();
  // The old fetch is still out: no overlapping fetch, and the window stays open.
  assert.deepEqual(events, ["start 1"]);

  finish(1);
  await flush();
  // The old fetch may predate the upgrade, so a fresh one runs before closing.
  assert.deepEqual(events, ["start 1", "end 1", "start 2"]);

  finish(2);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1", "start 2", "end 2", "expired"]);
  stop();
});

test("a return that is hidden again before its check keeps the window open", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const { poll, finish } = controlledPoll(events);
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: FETCH_TIMEOUT,
    doc,
  });

  t.mock.timers.tick(INTERVAL);
  await flush();
  setVisibility("hidden");
  t.mock.timers.tick(WINDOW * 2);
  setVisibility("visible");
  setVisibility("hidden");
  finish(1);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1"]);

  setVisibility("visible");
  await flush();
  finish(2);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1", "start 2", "end 2", "expired"]);
  stop();
});

test("a tab hidden again while the return check is out keeps the window open", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const { poll, finish } = controlledPoll(events);
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: FETCH_TIMEOUT,
    doc,
  });

  setVisibility("hidden");
  t.mock.timers.tick(WINDOW * 2);
  setVisibility("visible");
  await flush();
  setVisibility("hidden");
  finish(1);
  await flush();
  // The check's fetch finished while hidden, so the window stays open.
  assert.deepEqual(events, ["start 1", "end 1"]);

  setVisibility("visible");
  await flush();
  finish(2);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1", "start 2", "end 2", "expired"]);
  stop();
});

test("with overlapping returns only the latest return's check closes the window", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const { poll, finish } = controlledPoll(events);
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: FETCH_TIMEOUT,
    doc,
  });

  setVisibility("hidden");
  t.mock.timers.tick(WINDOW * 2);
  setVisibility("visible");
  await flush();
  setVisibility("hidden");
  setVisibility("visible");
  finish(1);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1", "start 2"]);

  finish(2);
  await flush();
  assert.deepEqual(events, ["start 1", "end 1", "start 2", "end 2", "expired"]);
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
    fetchTimeoutMs: FETCH_TIMEOUT,
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

/** Advance mock time in interval-sized steps, letting promises settle between. */
async function advance(t: { mock: { timers: { tick: (ms: number) => void } } }, ms: number) {
  for (let elapsed = 0; elapsed < ms; elapsed += 500) {
    t.mock.timers.tick(Math.min(500, ms - elapsed));
    await flush();
  }
}

test("a fetch that never settles cannot hold the window open after the return", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  const events: string[] = [];
  const { poll } = controlledPoll(events); // no fetch ever finishes
  const fetchTimeout = 20_000;
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {
      events.push("expired");
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: fetchTimeout,
    doc,
  });

  await advance(t, INTERVAL);
  setVisibility("hidden");
  await advance(t, WINDOW); // the window ends while hidden, fetch 1 still out
  setVisibility("visible");
  await flush();
  assert.deepEqual(events, ["start 1"]);

  // Fetch 1 is abandoned at its deadline and a fresh check starts; that one
  // hangs too, and its own deadline closes the window.
  await advance(t, fetchTimeout);
  assert.deepEqual(events, ["start 1", "start 2"]);
  await advance(t, fetchTimeout);
  assert.deepEqual(events, ["start 1", "start 2", "expired"]);
  stop();
});

test("a fetch that never settles does not stall later ticks", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc } = fakeDocument();
  const events: string[] = [];
  const { poll } = controlledPoll(events);
  const stop = startStructuredPlanUpgradePoll({
    poll,
    onWindowExpired: () => {},
    intervalMs: INTERVAL,
    windowMs: 60_000,
    fetchTimeoutMs: 5_000,
    doc,
  });

  await advance(t, INTERVAL * 2);
  assert.deepEqual(events, ["start 1"]); // no overlap before the deadline
  await advance(t, INTERVAL * 2);
  assert.deepEqual(events, ["start 1", "start 2"]); // deadline passed, polling resumes
  stop();
});

test("the window closing stops the poll without waiting for the component", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "setTimeout"] });
  const { doc, setVisibility } = fakeDocument();
  let polls = 0;
  let pollsAtExpiry = -1;
  startStructuredPlanUpgradePoll({
    poll: async () => {
      polls += 1;
    },
    onWindowExpired: () => {
      pollsAtExpiry = polls;
    },
    intervalMs: INTERVAL,
    windowMs: WINDOW,
    fetchTimeoutMs: FETCH_TIMEOUT,
    doc,
  });

  await advance(t, WINDOW);
  assert.ok(pollsAtExpiry >= 0);

  // No stop() call here: the component's cleanup has not run yet.
  await advance(t, INTERVAL * 4);
  setVisibility("hidden");
  setVisibility("visible");
  await flush();
  assert.equal(polls, pollsAtExpiry);
});
