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

test("aerobic work keeps its own rule and never gets a load/set bump", () => {
  const rule = "Add 5 minutes at the same easy pace if breathing stayed easy.";
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(2),
    block({
      block_type: "conditioning",
      display_name: "Easy assault bike",
      progression_rule: rule,
    }),
  );
  assert.equal(directive?.text, rule);
  assert.doesNotMatch(directive?.text ?? "", /add (?:one|a) set|load bump/i);
});

test("a block with no progression rule gets no invented directive", () => {
  assert.equal(openBlockWeekDirective(openBlockWeekIntent(2), block()), null);
  assert.equal(openBlockWeekDirective(openBlockWeekIntent(3), block()), null);
});

test("a stop rule is never presented as the week's progression", () => {
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(3),
    block({ progression_rule: "Stop when bar speed drops." }),
  );
  assert.equal(directive, null);
});

test("the deload week uses the block's own deload rule", () => {
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(4),
    block({
      progression_rule: "Add 2.5 kg when all sets complete.",
      deload_rule: "Drop to two working sets and keep the bar light.",
    }),
  );
  assert.ok(directive);
  assert.equal(directive.usesProgressionRule, false);
  assert.equal(directive.text, "Drop to two working sets and keep the bar light.");
});

test("the deload week invents nothing when the block has no deload rule", () => {
  const directive = openBlockWeekDirective(
    openBlockWeekIntent(4),
    block({ progression_rule: "Add 2.5 kg when all sets complete." }),
  );
  assert.equal(directive, null);
});
