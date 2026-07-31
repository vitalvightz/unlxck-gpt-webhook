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

/** React escapes apostrophes in static markup, so compare against plain text. */
function render(props: Parameters<typeof TodayDecisionPanel>[0]): string {
  return renderToStaticMarkup(<TodayDecisionPanel {...props} />).replace(/&#x27;/g, "'");
}

test("the action reads before the reason", () => {
  // An athlete in a gym scans for what to do first. If the reason lands above the
  // instruction, the instruction is what gets skipped.
  const html = render({ banner: BANNER });
  assert.ok(html.indexOf(BANNER.action!) < html.indexOf(BANNER.detail));
});

test("triggers and context render as separate rows", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep, 3 days"],
    context: ["Fight week", "Taper phase"],
  });
  assert.ok(html.includes("Trigger"));
  assert.ok(html.includes("Poor sleep, 3 days"));
  assert.ok(html.includes("Context"));
  assert.ok(html.includes("Fight week · Taper phase"));
});

test("context never renders inside the trigger row", () => {
  // The whole point of the split: a flat list made "Fight week" a peer of
  // "High pain", which reads as though being close to a fight were a symptom.
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep"],
    context: ["Fight week"],
  });
  const triggerRow = html.slice(html.indexOf("Trigger"), html.indexOf("Context"));
  assert.ok(triggerRow.includes("Poor sleep"));
  assert.ok(!triggerRow.includes("Fight week"));
});

test("a row with nothing in it does not render", () => {
  const html = render({ banner: BANNER, triggers: ["Poor sleep"] });
  assert.ok(html.includes("Trigger"));
  assert.ok(!html.includes("Context"));
});

test("blank labels never render an empty row", () => {
  const html = render({ banner: BANNER, triggers: ["", "   "], context: [""] });
  assert.ok(!html.includes("Trigger"));
  assert.ok(!html.includes("Context"));
});

test("high confidence lists what was available", () => {
  const html = render({
    banner: BANNER,
    confidence: "high",
    sources: ["today's check-in", "your recent sessions"],
  });
  assert.ok(html.includes("Confidence"));
  assert.ok(html.includes("High"));
  assert.ok(html.includes("today's check-in"));
  assert.ok(html.includes("your recent sessions"));
});

test("below high, the card names what was missing instead", () => {
  // The useful half. At high the inputs list says the same thing the other way
  // round, so showing both would only repeat the point.
  const html = render({
    banner: BANNER,
    confidence: "moderate",
    sources: ["today's check-in"],
    confidenceNote: "Less to go on today: today's session isn't resolved yet.",
  });
  assert.ok(html.includes("Moderate"));
  assert.ok(html.includes("today's session isn't resolved yet"));
  assert.ok(!html.includes("today-decision-inputs"));
  assert.ok(html.includes('data-band="moderate"'));
});

test("confidence is hidden when the backend sends no band", () => {
  // A recommendation stored before the engine recorded triggers has nothing to
  // judge it by. Rendering a default "High" there would put the most confident
  // claim on the one decision nothing is known about.
  assert.ok(!render({ banner: BANNER }).includes("Confidence"));
  assert.ok(
    !render({ banner: BANNER, sources: ["today's check-in"], confidence: null }).includes(
      "Confidence",
    ),
  );
});

test("the panel stays null before check-in even with an explanation supplied", () => {
  const html = render({ banner: null, triggers: ["Poor sleep"], confidence: "high" });
  assert.equal(html, "");
});

test("the explanation never claims a signal caused the change", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep"],
    context: ["Fight week"],
    confidence: "high",
    sources: ["today's check-in"],
  }).toLowerCase();
  for (const causal of ["caused", "because of", "due to"]) {
    assert.ok(!html.includes(causal), `explanation must not claim cause: ${causal}`);
  }
});

test("nothing on the card calls context a warning", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep"],
    context: ["Fight week", "Taper phase"],
    confidence: "moderate",
    confidenceNote: "Less to go on today: today's session isn't resolved yet.",
  }).toLowerCase();
  assert.ok(!html.includes("warning"));
});
