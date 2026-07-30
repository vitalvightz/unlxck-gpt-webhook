import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { TodayDecisionPanel } from "./today-decision-panel";
import type { TodayDecisionBanner } from "@/lib/today";

const BANNER: TodayDecisionBanner = {
  state: "modify",
  displayState: "adjust",
  chip: "ADJUST",
  title: "Session reduced",
  detail: "Poor sleep means your body has less room to recover today.",
  action: "Cut 1 round and do not add extra conditioning.",
  tone: "amber",
  blocksTraining: false,
};

test("contributors render as the 'what moved this' signal list", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} contributors={["Poor sleep", "Heavy recent load"]} />,
  );
  assert.ok(html.includes("What moved this"));
  assert.ok(html.includes("Poor sleep"));
  assert.ok(html.includes("Heavy recent load"));
});

test("the signal list is omitted when the backend sends no contributors", () => {
  const html = renderToStaticMarkup(<TodayDecisionPanel banner={BANNER} />);
  assert.ok(!html.includes("What moved this"));
  assert.ok(!html.includes("today-decision-signals"));
});

test("blank contributors never render an empty chip", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} contributors={["", "   "]} />,
  );
  assert.ok(!html.includes("What moved this"));
});

test("sources render as a spoken 'Based on' line", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel
      banner={BANNER}
      sources={["today's check-in", "your last few check-ins", "your recent sessions"]}
    />,
  );
  assert.ok(
    html.includes(
      "Based on today&#x27;s check-in, your last few check-ins and your recent sessions.",
    ),
  );
});

test("a single source reads without a list separator", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} sources={["your tracked injuries"]} />,
  );
  assert.ok(html.includes("Based on your tracked injuries."));
});

test("the panel stays null before check-in even with contributors supplied", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={null} contributors={["Poor sleep"]} sources={["today's check-in"]} />,
  );
  assert.equal(html, "");
});

test("the explanation never claims a signal caused the change", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} contributors={["Poor sleep"]} sources={["today's check-in"]} />,
  );
  for (const causal of ["caused", "because of", "due to"]) {
    assert.ok(!html.toLowerCase().includes(causal), `explanation must not claim cause: ${causal}`);
  }
});
