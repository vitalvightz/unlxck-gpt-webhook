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
};

const STOP_BANNER: TodayDecisionBanner = {
  state: "not_checked_in",
  displayState: "stop",
  chip: "STOP",
  title: "Stop today",
  detail: "A safety restriction is blocking training today.",
  action: "Do not start today's planned session. Follow the injury and safety guidance below.",
  tone: "red",
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

test("triggers and context render as separate stacked lists", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep for 3 days", "Feeling flat"],
    context: ["Fight week", "Taper phase"],
  });
  assert.ok(html.includes("Trigger"));
  assert.ok(html.includes("Poor sleep for 3 days"));
  assert.ok(html.includes("Feeling flat"));
  assert.ok(html.includes("Context"));
  assert.equal((html.match(/today-decision-values/g) ?? []).length, 2);
  assert.ok(html.includes('data-evidence-count="2"'));
  assert.ok(!html.includes(" · "));
});

test("dense evidence uses one command region and a three-group evidence rail", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep", "Feeling flat"],
    context: ["Fight week"],
    sources: ["today's check-in", "today's planned session"],
  });

  assert.equal((html.match(/today-decision-command/g) ?? []).length, 1);
  assert.equal((html.match(/today-decision-evidence/g) ?? []).length, 1);
  assert.ok(html.includes('data-evidence-count="3"'));
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

test("decision based on always lists the available sources", () => {
  const html = render({
    banner: BANNER,
    sources: ["today's check-in", "your recent sessions"],
  });
  assert.ok(html.includes("Decision based on"));
  assert.ok(html.includes("today-decision-inputs"));
  assert.ok(html.includes("today's check-in"));
  assert.ok(html.includes("your recent sessions"));
  assert.ok(!html.includes("Confidence"));
});

test("preview evidence names only the next session and drops today's readiness context", () => {
  const html = render({
    banner: {
      ...BANNER,
      displayState: "preview",
      chip: "PREVIEW",
      detail: "Mobility Reset is next on your plan.",
      action: "Review the mobility and recovery work before it opens.",
      tone: "neutral",
    },
    triggers: ["Pain reported today"],
    context: ["Taper phase"],
    sources: ["today's check-in", "today's planned session"],
    confidenceNote: "Less to go on today.",
  });

  assert.ok(html.includes("next planned session"));
  assert.ok(!html.includes("Pain reported today"));
  assert.ok(!html.includes("Taper phase"));
  assert.ok(!html.includes("today's check-in"));
  assert.ok(!html.includes("today's planned session"));
  assert.ok(!html.includes("Less to go on today"));
});

test("the status chip is the only decision-state label", () => {
  const html = render({ banner: STOP_BANNER, tier: "stop" });

  assert.ok(html.includes('data-state="stop"'));
  assert.ok(html.includes('data-tone="red"'));
  assert.ok(html.includes(">STOP<"));
  assert.ok(!html.includes("today-decision-title"));
  assert.ok(!html.includes(">Stop today<"));
  assert.ok(html.includes(STOP_BANNER.action!));
  assert.ok(html.includes(STOP_BANNER.detail));
  assert.ok(!html.includes("PULL BACK"));
});

test("a missing-data note renders beneath the available sources", () => {
  const html = render({
    banner: BANNER,
    sources: ["today's check-in"],
    confidenceNote: "Less to go on today: today's session isn't resolved yet.",
  });
  assert.ok(html.includes("Decision based on"));
  assert.ok(html.includes("today's session isn't resolved yet"));
  assert.ok(html.indexOf("today-decision-inputs") < html.indexOf("today-decision-gap"));
});

test("a missing-data note still renders when no source was available", () => {
  const html = render({
    banner: BANNER,
    confidenceNote: "Safety history is unavailable.",
  });
  assert.ok(html.includes("Decision based on"));
  assert.ok(html.includes("Safety history is unavailable."));
});

test("confidence bands are never rendered", () => {
  const html = render({ banner: BANNER, sources: ["today's check-in"] });
  for (const band of ["Confidence", "High", "Moderate", "Low", "data-band"]) {
    assert.ok(!html.includes(band), `must not render confidence band: ${band}`);
  }
});

test("the panel stays null before check-in even with an explanation supplied", () => {
  const html = render({ banner: null, triggers: ["Poor sleep"] });
  assert.equal(html, "");
});

test("the explanation never claims a signal caused the change", () => {
  const html = render({
    banner: BANNER,
    triggers: ["Poor sleep"],
    context: ["Fight week"],
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
    confidenceNote: "Less to go on today: today's session isn't resolved yet.",
  }).toLowerCase();
  assert.ok(!html.includes("warning"));
});
