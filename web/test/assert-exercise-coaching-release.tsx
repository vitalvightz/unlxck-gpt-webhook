// Invoked by the Python release test with the actual persisted API payload.
// Deliberately outside the unit-test glob: this requires backend dependencies.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { ExerciseRow } from "../components/structured-plan-renderer";
import { getBlockExecutionDisplay } from "../lib/structured-plan";
import type { StructuredBlock, StructuredPlan } from "../lib/types";

const { plan, expected } = JSON.parse(readFileSync(0, "utf8")) as {
  plan: StructuredPlan;
  expected: Array<{ id: string; fields: StructuredBlock; forbidden?: string[] }>;
};
const blocks = (plan.weeks ?? []).flatMap(w => (w.days ?? []).flatMap(d =>
  (d.sessions ?? []).flatMap(s => s.blocks ?? [])));
const text = (html: string) => html.replace(/<[^>]*>/g, "").replace(/&#x27;|&#39;/g, "'")
  .replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&gt;/g, ">").replace(/&lt;/g, "<");
let progress = 0, easier = 0, cues = 0, stops = 0;
for (const row of expected) {
  const block = blocks.find(b => b.block_id === row.id);
  assert.ok(block, row.id);
  const html = renderToStaticMarkup(<ExerciseRow block={block} open onToggle={() => {}} />);
  const visible = text(html);
  for (const copy of row.forbidden ?? []) {
    assert.ok(!visible.includes(copy), `${row.id}: borrowed another session's instruction: ${copy}`);
  }
  for (const [field, label] of [
    ["coaching_cues", "Coaching cues"], ["regression_options", "Easier"],
    ["stop_rules", "Stop rule"],
  ] as const) {
    const value = field === "coaching_cues" ? getBlockExecutionDisplay(row.fields).cues.slice(0, 1) : row.fields[field];
    const values = typeof value === "string" ? [value] : value ?? [];
    if (values.length && field !== "coaching_cues") assert.ok(visible.includes(label), `${row.id}: missing ${label}`);
    for (const copy of values) {
      const expectedCopy = field === "stop_rules" ? copy.replace(/^Stop(?: rule)?:\s*/i, "") : copy;
      assert.ok(visible.includes(expectedCopy), `${row.id}: lost ${field}: ${copy}`);
    }
  }
  assert.ok(!/>Progress<\/span>/.test(html), row.id);
  assert.equal(block.progression_rule ?? null, row.fields.progression_rule ?? null, `${row.id}: saved guidance changed`);
  if (row.fields.progression_rule) progress++;
  if (row.fields.regression_options?.length) easier++;
  if (row.fields.coaching_cues?.length) cues++;
  if (row.fields.stop_rules?.length) stops++;
}
console.log(JSON.stringify({ physicalCards: expected.length, cues, progress, easier, stops }));
