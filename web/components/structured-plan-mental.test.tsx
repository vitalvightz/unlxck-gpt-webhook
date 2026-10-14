import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { SessionCard } from "./structured-plan-renderer";
import { mentalSessionCategory } from "../lib/structured-plan";
import type { StructuredSession } from "../lib/types";

for (const [title, category] of [["Fight Visualisation", "Visualise"], ["Neural Visualisation", "Visualise"],
  ["Tactical Watch", "Analyse"], ["Tactical Focus", "Analyse"], ["Self-Review Cues", "Reflect"]]) {
  test(`${title} keeps instructions collapsed in both layouts`, () => {
    const session: StructuredSession = { session_id: `saved-${title}`, title, session_type: "skill",
      planned_duration: { value: 5, unit: "minutes" }, objective: "Original selected scenario instruction.",
      blocks: [{ block_id: "original-block", display_name: title, coaching_cues: ["Keep the original bank cue."],
        duration: { value: 5, unit: "minutes" } }] };
    assert.equal(mentalSessionCategory(session), category);
    for (const layout of ["card", "section"] as const) {
      const html = renderToStaticMarkup(<SessionCard session={session} layout={layout} defaultOpenBlocks
        completionInfo={{ onLog: () => {}, display: { state: "done", label: "Done", tone: "green" } }} />);
      assert.match(html, new RegExp(`${category} · 5 min`));
      assert.match(html, /<details class="sp-section-details"><summary>/);
      assert.doesNotMatch(html, /<details[^>]* open/);
      assert.match(html, /Original selected scenario instruction/);
      assert.match(html, /Keep the original bank cue/);
      assert.match(html, /Log this session/);
      assert.doesNotMatch(html, /Zero load/);
    }
  });
}

test("physical coaching and passive resets keep their normal presentation", () => {
  for (const title of ["Breathing Reset", "Strength", "Hard sparring"]) {
    assert.equal(mentalSessionCategory({ title, session_type: "strength_power" }), null);
  }
  assert.equal(mentalSessionCategory({ title: "Strength", session_type: "strength_power",
    blocks: [{ display_name: "Neural Visualisation" }] }), null);
});
