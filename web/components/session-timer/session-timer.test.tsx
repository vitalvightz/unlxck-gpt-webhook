import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { SessionTimer } from "./session-timer";
import type { TimerItem } from "@/lib/session-timer/plan";

const ITEMS: TimerItem[] = [
  {
    kind: "interval",
    id: "spar",
    title: "Hard sparring",
    detail: null,
    blockType: "sparring",
    rounds: 6,
    workSec: 180,
    restSec: 60,
    sparring: true,
    needsSetup: false,
  },
  {
    kind: "sets",
    id: "squat",
    title: "Back squat",
    detail: "5 reps · RPE 7",
    blockType: "strength",
    sets: { min: 3, max: 5 },
    holdSec: null,
    restSec: { min: 90, max: 120 },
  },
];

function render(items: TimerItem[], visible = true): string {
  return renderToStaticMarkup(
    <SessionTimer
      items={items}
      storageKey="test-run"
      sessionTitle="Fight-pace day"
      visible={visible}
      onMinimize={() => undefined}
      onExpand={() => undefined}
      onFinish={() => undefined}
      onClose={() => undefined}
    />,
  );
}

test("the ready screen shows the first exercise, its adjustable rounds and what is next", () => {
  const html = render(ITEMS);
  assert.match(html, /role="dialog"/);
  assert.match(html, /Up next/);
  assert.match(html, /Hard sparring/);
  assert.match(html, /Start round 1/);
  // One summary line; the steppers live behind the Adjust icon.
  assert.match(html, /<span>6<\/span> × <span>3:00<\/span>/);
  assert.match(html, /aria-label="Adjust timer"/);
  assert.doesNotMatch(html, /aria-label="Increase rounds"/);
  assert.match(html, /Up next<\/span><span class="st-next-title">Back squat<\/span>/);
  assert.match(html, /3–5 sets · 90s–2 min rest/);
  assert.doesNotMatch(html, /Pick a format/);
});

test("rounds with no length in the plan ask the athlete to check them", () => {
  const first = ITEMS[0];
  assert.ok(first.kind === "interval");
  const html = render([{ ...first, needsSetup: true }]);
  assert.match(html, /Round length isn&#x27;t set in your plan\. Pick a format\./);
  // The athlete's own gym work is never framed as missing from their plan.
  const gym = render([{ ...first, needsSetup: true, setupNote: "Match your gym's rounds. Pick a format." }]);
  assert.match(gym, /Match your gym&#x27;s rounds\. Pick a format\./);
  assert.doesNotMatch(gym, /Not in your plan|isn&#x27;t set in your plan/);
});

test("a minimised timer on its ready screen renders the mini bar", () => {
  const html = render(ITEMS, false);
  assert.match(html, /class="st-mini"/);
  assert.match(html, /Hard sparring/);
  assert.doesNotMatch(html, /role="dialog"/);
});

test("the last exercise has no button that ends the session except the end link", () => {
  const last = ITEMS[1];
  // A single-exercise run is always on its last exercise.
  const html = render([last]);
  assert.doesNotMatch(html, />Finish</);
  assert.doesNotMatch(html, /Finish exercise/);
  assert.doesNotMatch(html, /Next exercise/);
  // Unstarted, that link only closes the timer.
  assert.match(html, />Close timer</);
});

test("Next exercise only appears when there is a next exercise", () => {
  assert.match(render(ITEMS), /Next exercise/);
});

test("an unstarted timer offers Close timer instead of ending a session", () => {
  const html = render(ITEMS);
  assert.match(html, />Close timer</);
  assert.doesNotMatch(html, />End session</);
});

test("the plan summary opens the adjust sheet and the first-run hint waits for storage", () => {
  const html = render(ITEMS);
  assert.match(html, /class="st-plan-summary"[^>]*aria-label="Edit rounds and timing"/);
  // Hidden on the server so it never flashes for athletes who have seen it.
  assert.doesNotMatch(html, /st-hint/);
});
