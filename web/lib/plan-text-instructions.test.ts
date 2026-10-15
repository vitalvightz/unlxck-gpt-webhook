import test from "node:test";
import assert from "node:assert/strict";
import { buildStructuredPlanFromText } from "./plan-text-adapter";

test("raw-text fallback separates drill explanation from its coach cue", () => {
  const how = "Feint at range, enter once, throw, then exit.";
  for (const separator of ["\n  ", " "]) {
    const plan = buildStructuredPlanFromText(`### D-13 (Saturday): Skill
- Coach Drill: 1 x 5 sec
  How: ${how}${separator}Cue: Keep guard ready.`, "2026-10-29");
    const block = plan.weeks?.flatMap(w => w.days ?? [])
      .flatMap(d => d.sessions ?? []).flatMap(s => s.blocks ?? [])
      .find(b => b.display_name === "Coach Drill");
    assert.ok(block);
    assert.equal(block.execution_instructions, how);
    assert.deepEqual(block.coaching_cues, ["Cue: Keep guard ready."]);
  }
});
