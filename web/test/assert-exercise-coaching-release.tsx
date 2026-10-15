// Invoked by the Python release test with the actual persisted API payload.
// Deliberately outside the unit-test glob: this requires backend dependencies.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { ExerciseRow } from "../components/structured-plan-renderer";
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
  // Full source fields stay intact in the stored API payload (Python asserts
  // exact equality). The athlete-visible projection is intentionally smaller:
  // ONE execution cue and ONE easier, with measured Progress and full safety.
  if (row.fields.coaching_cues?.length) {
    const lead = row.fields.coaching_cues[0].replace(/^Cue:\s*/i, "");
    const expectedStart = lead.split(/[;,]/)[0].trim();
    assert.ok(visible.includes(expectedStart) || visible.includes("Key cue") || visible.includes(">Cue"),
      `${row.id}: missing execution cue`);
    assert.ok(!visible.includes("Coaching cues"), `${row.id}: duplicate coaching accordion`);
  }
  if (row.fields.regression_options?.length) {
    assert.ok(visible.includes("Easier"), `${row.id}: missing Easier`);
  }
  if (row.fields.stop_rules?.length) {
    assert.ok(visible.includes("Stop"), `${row.id}: missing Stop`);
    for (const criterion of row.fields.stop_rules) {
      assert.ok(visible.includes(criterion), `${row.id}: missing stop trigger: ${criterion}`);
    }
  }
  if (row.fields.progression_rule) {
    assert.ok(visible.includes("Progress"), `${row.id}: missing Progress`);
    const m = row.fields.progression_rule.match(/\badd\s+(\d+(?:\.\d+)?)\s*(kg|lb|reps?|sets?|rounds?|m)\b/i);
    if (m) assert.ok(visible.includes(m[1]), `${row.id}: lost numeric progression amount`);
  }
  if (!row.fields.progression_rule) assert.ok(!/>Progress<\/span>/.test(html), row.id);
  if (row.fields.progression_rule) progress++;
  if (row.fields.regression_options?.length) easier++;
  if (row.fields.coaching_cues?.length) cues++;
  if (row.fields.stop_rules?.length) stops++;
}
console.log(JSON.stringify({ physicalCards: expected.length, cues, progress, easier, stops }));
