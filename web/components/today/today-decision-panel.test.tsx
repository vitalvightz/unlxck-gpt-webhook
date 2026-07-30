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

test("the action reads before the reason", () => {
  // An athlete in a gym scans for what to do first. If the reason lands above the
  // instruction, the instruction is what gets skipped.
  const html = renderToStaticMarkup(<TodayDecisionPanel banner={BANNER} />);
  assert.ok(html.indexOf(BANNER.action!) < html.indexOf(BANNER.detail));
});

test("confidence renders whenever there is a live backend decision", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} sources={["today's check-in"]} confidence="high" />,
  );
  assert.ok(html.includes("Data coverage"));
  assert.ok(html.includes("High"));
});

test("a below-high band names the missing input", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel
      banner={BANNER}
      sources={["today's check-in"]}
      confidence="moderate"
      confidenceNote="Lower confidence today: no recent days to compare."
    />,
  );
  assert.ok(html.includes("Moderate"));
  assert.ok(html.includes("no recent days to compare"));
  assert.ok(html.includes('data-band="moderate"'));
});

test("confidence is hidden when the backend sends no band", () => {
  // A recommendation stored before the engine recorded triggers has nothing to
  // judge it by. Rendering a default "High" there would put the most confident
  // claim on the one decision nothing is known about.
  const html = renderToStaticMarkup(<TodayDecisionPanel banner={BANNER} />);
  assert.ok(!html.includes("Data coverage"));

  const withSources = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} sources={["today's check-in"]} confidence={null} />,
  );
  assert.ok(!withSources.includes("Data coverage"));
  assert.ok(withSources.includes("Based on today&#x27;s check-in."));
});

test("the explanation never claims a signal caused the change", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} contributors={["Poor sleep"]} sources={["today's check-in"]} />,
  );
  for (const causal of ["caused", "because of", "due to"]) {
    assert.ok(!html.toLowerCase().includes(causal), `explanation must not claim cause: ${causal}`);
  }
});

test("historical sources read in the past tense", () => {
  // A failed re-read beside a present-tense "Based on your last few check-ins"
  // reads as: you couldn't load them, yet you say you used them.
  const html = renderToStaticMarkup(
    <TodayDecisionPanel
      banner={BANNER}
      sources={["today's check-in", "your last few check-ins"]}
      confidence="moderate"
      confidenceNote="We couldn't refresh your recent check-ins just now."
      sourcesAreHistorical
    />,
  );
  assert.ok(
    html.includes("Today&#x27;s call was based on today&#x27;s check-in and your last few check-ins."),
  );
});

test("a decision made now stays in the present tense", () => {
  const html = renderToStaticMarkup(
    <TodayDecisionPanel banner={BANNER} sources={["today's check-in"]} confidence="moderate" />,
  );
  assert.ok(html.includes("Based on today&#x27;s check-in."));
  assert.ok(!html.includes("was based on"));
});
