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

test("exercise Progress is hidden while the separate stop rule remains visible", () => {
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

  assert.equal(html.includes(">Progress</span>"), false);
  assert.equal(html.includes("Increase band resistance when punch speed stays high."), false);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("Sharp shoulder pain or a clear drop in punch mechanics."), true);
});

test("exercise card keeps execution and reset while hiding planning transcript and deduplicating Easier", () => {
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
  assert.equal(html.includes("Coaching cues"), false);
  assert.equal(html.split("Reduce band tension").length - 1, 1);
});


test("exercise card renders every stored stop criterion in one row", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-jab-cross",
        block_type: "skill",
        display_name: "Band-Resisted Jab-Cross Primer",
        stop_rules: [
          "Any sharp pain at the left shoulder",
          "Wound irritation",
          "If speed degrades and form breaks",
        ],
      }}
    />,
  );
  assert.equal(html.split(">Stop rule</span>").length - 1, 1);
  assert.equal(html.includes("Any sharp pain at the left shoulder"), true);
  assert.equal(html.includes("Wound irritation"), true);
  assert.equal(html.includes("If speed degrades and form breaks"), true);
});


test("enhanced block exposes Easier and Stop while hiding saved AI Progress", () => {
  const html = renderToStaticMarkup(
    <BlockCard block={{
      block_id: "strength-push", block_type: "strength",
      display_name: "Weighted Push-Up", sets: 2, reps: "6",
      coaching_cues: [
        "Brace the trunk; drive smoothly.",
        "Brace the trunk and drive smoothly.",
      ],
      regression_options: ["Reduce sets to 1"],
      progression_rule: "Next D-28: add 1 rep/set if controlled and recovered.",
      stop_rules: ["Stop if form breaks"],
    }} />,
  );
  assert.equal(html.split("Brace the trunk; drive smoothly.").length - 1, 1);
  assert.equal(html.includes("Brace the trunk and drive smoothly."), false);
  assert.equal(html.includes("Coaching cues"), false);
  assert.match(html, />Easier<\/span>/);
  assert.doesNotMatch(html, />Progress<\/span>/);
  assert.match(html, />Stop rule<\/span>/);
  assert.doesNotMatch(html, /Next D-28: add 1 rep\/set if controlled and recovered/);
});
