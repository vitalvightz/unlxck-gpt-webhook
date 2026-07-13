import test from "node:test";
import assert from "node:assert/strict";

import {
  OPEN_BLOCK_WEEK_LABELS,
  openBlockWeekDirective,
  openBlockWeekIntent,
} from "./open-block";
import type { StructuredBlock } from "./types";

function block(overrides: Partial<StructuredBlock> = {}): StructuredBlock {
  return {
    block_id: "b1",
    block_type: "strength_power",
    display_name: "Trap-bar deadlift",
    order_index: 0,
    ...overrides,
  } as StructuredBlock;
}

test("maps the four block weeks to their development intents", () => {
  assert.equal(openBlockWeekIntent(1)?.key, "baseline");
  assert.equal(openBlockWeekIntent(2)?.key, "progress");
  assert.equal(openBlockWeekIntent(3)?.key, "peak");
  assert.equal(openBlockWeekIntent(4)?.key, "deload");
  assert.deepEqual(
    [1, 2, 3, 4].map((week) => openBlockWeekIntent(week)?.label),
    [...OPEN_BLOCK_WEEK_LABELS],
  );
});

test("returns null outside the four-week block or without a week number", () => {
  assert.equal(openBlockWeekIntent(0), null);
  assert.equal(openBlockWeekIntent(5), null);
  assert.equal(openBlockWeekIntent(null), null);
  assert.equal(openBlockWeekIntent(undefined), null);
  assert.equal(openBlockWeekIntent(Number.NaN), null);
});

test("baseline week carries no per-block directive", () => {
  assert.equal(openBlockWeekDirective(openBlockWeekIntent(1), block()), null);
  assert.equal(openBlockWeekDirective(null, block()), null);
});

test("progression weeks surface the block's own progression rule", () => {
  const rule = "Add one set when every rep stays crisp.";
  for (const week of [2, 3]) {
    const directive = openBlockWeekDirective(
      openBlockWeekIntent(week),
      block({ progression_rule: rule }),
    );
    assert.equal(directive?.text, rule);
    assert.equal(directive?.usesProgressionRule, true);
  }
});

test("progression weeks fall back to a generic bump when the block has no rule", () => {
  const directive = openBlockWeekDirective(openBlockWeekIntent(2), block());
  assert.ok(directive);
  assert.equal(directive.usesProgressionRule, false);
  assert.match(directive.text, /only if last week felt controlled/i);
});

test("a stop rule is never presented as the week's progression", () => {
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(3),
    block({ progression_rule: "Stop when bar speed drops." }),
  );
  assert.ok(directive);
  assert.equal(directive.usesProgressionRule, false);
  assert.doesNotMatch(directive.text, /stop when bar speed drops/i);
});

test("the deload week always overrides with a volume cut", () => {
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(4),
    block({ progression_rule: "Add 2.5 kg when all sets complete." }),
  );
  assert.ok(directive);
  assert.equal(directive.usesProgressionRule, false);
  assert.match(directive.text, /deload/i);
  assert.match(directive.text, /half/i);
});
