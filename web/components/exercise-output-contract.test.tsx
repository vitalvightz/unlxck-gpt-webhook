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

for (const week of [1, 2, 4]) {
  test(`legacy week ${week}: missing side, tempo and load details survive alongside existing metrics`, () => {
    const html = renderToStaticMarkup(<BlockCard openWeekIntent={openBlockWeekIntent(week)} block={{
      display_name: "Split Squat", block_type: "strength", sets: 3, reps: 8,
      week_prescription: "3 sets x 8 reps per side; tempo 3-1-X-1; load 25 kg; stop for sharp pain.",
    }} />);
    assert.match(html, />Volume</);
    for (const detail of ["per side", "tempo 3-1-X-1", "load 25 kg", "stop for sharp pain"]) assert.ok(html.includes(detail), detail);
    assert.doesNotMatch(html, /3 sets x 8 reps|This week/);
  });
}

test("a complete strength card does not repeat its dose or already visible qualifiers", () => {
  const html = renderToStaticMarkup(<BlockCard block={{
    display_name: "Split Squat", block_type: "strength", sets: 3, reps: "8 per side",
    rest: { value: 90, unit: "seconds" }, load: { method: "absolute", value: 25, unit: "kg" },
    effort: { method: "RPE", value: 7 }, execution_instructions: "Tempo 3-1-X-1.",
    week_prescription: "3 sets x 8 reps per side; tempo 3-1-X-1; load 25 kg; rest 90 sec; RPE 7.",
  }} />);
  assert.equal(html.split("per side").length - 1, 1);
  assert.equal((html.match(/[Tt]empo 3-1-X-1/g) ?? []).length, 1);
  assert.doesNotMatch(html, /3 sets x 8 reps|load 25 kg|rest 90 sec/);
});

test("partial legacy intervals keep work, rounds and between-block recovery that have no metric", () => {
  const html = renderToStaticMarkup(<BlockCard block={{ ...tabata,
    rounds: null, work: null, interval_blocks: null, between_block_rest: null,
  }} />);
  for (const detail of ["8 rounds", "20s", "1 blocks", "2 min between blocks"]) assert.ok(html.includes(detail), detail);
  assert.doesNotMatch(html, /10s rest/);
});

test("legacy safety limits and conflicting quantitative values are preserved verbatim", () => {
  const html = renderToStaticMarkup(<BlockCard block={{
    display_name: "Squat", block_type: "strength", sets: 3, reps: 8,
    load: { method: "absolute", value: 25, unit: "kg" }, effort: { method: "RPE", value: 7 },
    week_prescription: "3 sets x 6 reps; Never exceed 3 sets; load 2.5 kg; RPE 7–8; RPE 7/10; stop if pain exceeds 3/10.",
  }} />);
  for (const detail of ["3 sets x 6 reps", "Never exceed 3 sets", "load 2.5 kg", "RPE 7–8", "RPE 7/10", "stop if pain exceeds 3/10"]) assert.ok(html.includes(detail), detail);
});

test("a complete compound dose is not repeated after its metrics", () => {
  const html = renderToStaticMarkup(<BlockCard block={{
    display_name: "Squat", block_type: "strength", sets: 3, reps: 8,
    load: { method: "percentage", value: 75, unit: "percent", ref: "1RM" },
    rest: { value: 90, unit: "seconds" }, effort: { method: "RPE", value: 7 },
    week_prescription: "3 sets x 8 reps @ 75% 1RM; rest 90 sec; RPE 7.",
  }} />);
  assert.doesNotMatch(html, /3 sets x 8 reps|rest 90 sec|sp-block-purpose/);
  assert.equal(html.split("75% 1RM").length - 1, 1);
});

test("explicit prescription text does not hide additional legacy qualifiers", () => {
  const html = renderToStaticMarkup(<BlockCard block={{
    display_name: "Split Squat", block_type: "strength", sets: 3, reps: 8,
    prescription_text: "3 sets x 8 reps", week_prescription: "3 sets x 8 reps; per side; tempo 3-1-X-1.",
  }} />);
  for (const detail of ["3 sets x 8 reps", "per side", "tempo 3-1-X-1"]) assert.ok(html.includes(detail), detail);
  assert.equal(html.split("3 sets x 8 reps").length - 1, 1);
});
