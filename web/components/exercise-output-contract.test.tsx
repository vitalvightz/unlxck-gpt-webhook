import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { BlockCard, ExerciseRow } from "./structured-plan-renderer";
import { openBlockWeekIntent } from "@/lib/open-block";
import type { StructuredBlock } from "@/lib/types";

const tabata: StructuredBlock = {
  display_name: "Burpee-to-Punch (Tabata)", block_type: "conditioning",
  rounds: 8, work: { value: 20, unit: "seconds" }, rest: { value: 10, unit: "seconds" },
  interval_blocks: 1, between_block_rest: { value: 120, unit: "seconds" },
  effort: { method: "RPE", value: 9 },
  week_prescription: "8 rounds of 20s all-out work / 10s rest; 1 blocks, 2 min between blocks.",
  coaching_cues: ["Go hard, finish with a controlled punch.",
    "8 rounds of 20s all-out work / 10s rest; 1 blocks, 2 min between blocks."],
  execution_instructions: "Complete 8 rounds of 20 seconds work with 10 seconds rest. After the single block, rest 120 seconds before next item.",
  stop_rules: ["Stop for dizziness or form loss."],
};

test("screenshot regression: nested Tabata dose appears in stats, never How/This week/cues", () => {
  const html = renderToStaticMarkup(<BlockCard block={tabata} openWeekIntent={openBlockWeekIntent(2)} />);
  assert.match(html, />Rounds</);
  assert.match(html, />Work</);
  assert.match(html, /20 sec/);
  assert.match(html, />Rest</);
  assert.match(html, /10 sec/);
  assert.match(html, />Between blocks</);
  assert.match(html, /2 min/);
  assert.equal(html.split("Go hard, finish with a controlled punch.").length - 1, 1);
  assert.match(html, /Stop for dizziness or form loss/);
  assert.doesNotMatch(html, /This week|>How<|8 rounds of/);
});

test("collapsed summaries keep every quantity; expansion shows the complete stats once", () => {
  const collapsed = renderToStaticMarkup(<ExerciseRow block={tabata} open={false} onToggle={() => {}} />);
  for (const text of ["8 rounds", "20 sec work", "rest 10 sec", "rest between blocks 2 min", "RPE 9"]) {
    assert.ok(collapsed.includes(text), text);
  }
  const expanded = renderToStaticMarkup(<ExerciseRow block={tabata} open onToggle={() => {}} />);
  assert.match(expanded, /class="ex-row-summary" hidden=""/);
  assert.match(expanded, /sp-block-stats/);
  assert.match(expanded, /20 sec/);
});

test("real movement sequences and an authored week change remain visible once", () => {
  const html = renderToStaticMarkup(<BlockCard openWeekIntent={openBlockWeekIntent(2)} block={{
    ...tabata, execution_instructions: "Step back, lower smoothly, then finish with a controlled punch.",
    progression_rule: "Add one round only if technique stays controlled.",
  }} />);
  assert.match(html, />How<\/span>Step back/);
  assert.match(html, /This week/);
  assert.equal(html.split("Add one round only if technique stays controlled.").length - 1, 1);
  assert.doesNotMatch(html, /8 rounds of/);
});
