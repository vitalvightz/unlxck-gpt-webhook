import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { BlockCard } from "./structured-plan-renderer";

test("Band-Resisted Punch does not label taper safety text as Progress", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "accessory",
        display_name: "Band-Resisted Punch",
        progression_rule:
          "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain, new swelling, or loss of balance.",
      }}
    />,
  );

  assert.equal(html.includes(">Progress</span>"), false);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("any sharp ankle pain, new swelling, or loss of balance."), true);
});

test("a genuine progression and stop rule render as separate rows", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "accessory",
        display_name: "Band-Resisted Punch",
        progression_rule: "Increase band resistance when punch speed stays high.",
        stop_rules: ["Sharp shoulder pain or a clear drop in punch mechanics."],
      }}
    />,
  );

  assert.equal(html.includes(">Progress</span>"), true);
  assert.equal(html.includes("Increase band resistance when punch speed stays high."), true);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("Sharp shoulder pain or a clear drop in punch mechanics."), true);
});

test("exercise card hides planning transcript and deduplicates Easier guidance", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "power",
        display_name: "Band-Resisted Punch",
        purpose: "Low-volume neural strength to preserve punch power and speed.",
        why_today: "Single sharp neural touch in the sharpness week.",
        coaching_cues: [
          "Purpose: maintain punch speed under slight resistance",
          "Why today: keep the dose small in sharpness week",
          "Explosive intent; accelerate through full range",
          "Easier: reduce band tension",
          "Reset guard immediately",
        ],
        regression_options: ["Reduce band tension"],
      }}
    />,
  );

  assert.equal(html.includes("Low-volume neural strength to preserve punch power and speed."), false);
  assert.equal(html.includes("Single sharp neural touch in the sharpness week."), false);
  assert.equal(html.includes("maintain punch speed under slight resistance"), false);
  assert.equal(html.includes("keep the dose small in sharpness week"), false);
  assert.equal(html.includes("Explosive intent; accelerate through full range"), true);
  assert.equal(html.includes("Reset guard immediately"), true);
  assert.equal(html.split("Reduce band tension").length - 1, 1);
});
