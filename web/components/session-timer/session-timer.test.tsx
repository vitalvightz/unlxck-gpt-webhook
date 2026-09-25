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
    />,
  );
}

test("the ready screen shows the first exercise, its adjustable rounds and what is next", () => {
  const html = render(ITEMS);
  assert.match(html, /role="dialog"/);
  assert.match(html, /Up next/);
  assert.match(html, /Hard sparring/);
  assert.match(html, /Start round 1/);
  assert.match(html, /aria-label="Increase rounds"/);
  assert.match(html, />3:00</);
  assert.match(html, /Back squat · 3–5 sets · 90s–2 min rest/);
  assert.doesNotMatch(html, /Round length isn/);
});

test("rounds with no length in the plan ask the athlete to check them", () => {
  const first = ITEMS[0];
  assert.ok(first.kind === "interval");
  const html = render([{ ...first, needsSetup: true }]);
  assert.match(html, /Round length isn&#x27;t in your plan/);
});

test("a minimised timer on its ready screen renders the mini bar", () => {
  const html = render(ITEMS, false);
  assert.match(html, /class="st-mini"/);
  assert.match(html, /Hard sparring/);
  assert.doesNotMatch(html, /role="dialog"/);
});
