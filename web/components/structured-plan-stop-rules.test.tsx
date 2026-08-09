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
