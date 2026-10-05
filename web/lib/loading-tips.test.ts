import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTipDeck,
  LOADING_TIPS,
  resolveLoadingTipContexts,
  selectLoadingTips,
  type LoadingTipCategory,
} from "./loading-tips.ts";
import type { PlanRequest } from "./types.ts";

const NOW = Date.UTC(2026, 9, 5, 12, 0, 0);
const DAY = 86_400_000;
const isoDate = (offsetDays: number) => new Date(NOW + offsetDays * DAY).toISOString().slice(0, 10);

function intake(overrides: Partial<PlanRequest> = {}): PlanRequest {
  return {
    athlete: { technical_style: ["boxing"] } as unknown as PlanRequest["athlete"],
    fight_date: isoDate(70),
    equipment_access: [],
    training_availability: [],
    hard_sparring_days: [],
    support_work_days: [],
    key_goals: ["power"],
    weak_areas: [],
    ...overrides,
  };
}

const categoriesOf = (tips: { category: LoadingTipCategory }[]) => new Set(tips.map((tip) => tip.category));

test("tip bank has at least 30 unique tips across every category", () => {
  assert.ok(LOADING_TIPS.length >= 30);
  assert.equal(new Set(LOADING_TIPS.map((tip) => tip.id)).size, LOADING_TIPS.length);
  const expected: LoadingTipCategory[] = [
    "training", "recovery", "sleep", "hydration", "nutrition",
    "weight_management", "supplements", "fight_week", "injury_safety", "combat_performance",
  ];
  assert.deepEqual([...categoriesOf([...LOADING_TIPS])].sort(), [...expected].sort());
});

test("every tip is 10-25 words and avoids unsafe or overclaiming language", () => {
  for (const tip of LOADING_TIPS) {
    const words = tip.text.trim().split(/\s+/).length;
    assert.ok(words >= 10 && words <= 25, `${tip.id} has ${words} words`);
    assert.doesNotMatch(tip.text, /sauna|sweat suit|diuretic|laxative|spitting|water load|\bcures?\b|\bheals?\b|guarantee|diagnos|\btreat(s|ment)?\b/i, tip.id);
  }
});

test("no intake or an unremarkable intake falls back to general combat-performance tips", () => {
  for (const source of [null, intake()]) {
    const categories = categoriesOf(selectLoadingTips(source, NOW));
    assert.ok(categories.has("combat_performance"));
    assert.ok(!categories.has("injury_safety"));
    assert.ok(!categories.has("weight_management"));
    assert.ok(!categories.has("fight_week"));
  }
});

test("an active injury selects recovery and safety tips", () => {
  assert.deepEqual(resolveLoadingTipContexts(intake({ injuries: "left shoulder strain" }), NOW), ["injury"]);
  assert.deepEqual(resolveLoadingTipContexts(intake({ guided_injuries: [{ area: "knee" }] }), NOW), ["injury"]);
  const categories = categoriesOf(selectLoadingTips(intake({ injuries: "left shoulder strain" }), NOW));
  assert.deepEqual([...categories].sort(), ["injury_safety", "recovery", "sleep"]);
});

test("'none' style injury answers do not count as an injury", () => {
  for (const injuries of ["", "  ", "none", "None.", "n/a", "no"]) {
    assert.deepEqual(resolveLoadingTipContexts(intake({ injuries }), NOW), [], injuries);
  }
});

test("a weight-cut goal selects nutrition, hydration and weight-management tips", () => {
  assert.deepEqual(resolveLoadingTipContexts(intake({ key_goals: ["weight_cut"] }), NOW), ["weight"]);
  assert.deepEqual(resolveLoadingTipContexts(intake({ primary_goal: "weight_cut" }), NOW), ["weight"]);
  const camp = { current_weight_kg: 74, target_weight_kg: 70 } as PlanRequest["shared_camp_context"];
  assert.deepEqual(resolveLoadingTipContexts(intake({ shared_camp_context: camp }), NOW), ["weight"]);
  const categories = categoriesOf(selectLoadingTips(intake({ key_goals: ["weight_cut"] }), NOW));
  assert.deepEqual([...categories].sort(), ["hydration", "nutrition", "weight_management"]);
});

test("a fight within two weeks selects taper and fight-week tips", () => {
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: isoDate(5) }), NOW), ["fight_week"]);
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: isoDate(0) }), NOW), ["fight_week"]);
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: isoDate(30) }), NOW), []);
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: isoDate(-3) }), NOW), []);
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: isoDate(5), no_scheduled_fight: true }), NOW), []);
  assert.deepEqual(resolveLoadingTipContexts(intake({ fight_date: "not-a-date" }), NOW), []);
  assert.ok(categoriesOf(selectLoadingTips(intake({ fight_date: isoDate(5) }), NOW)).has("fight_week"));
});

test("several signals combine their tip categories", () => {
  const contexts = resolveLoadingTipContexts(
    intake({ injuries: "sore wrist", key_goals: ["weight_cut"], fight_date: isoDate(7) }),
    NOW,
  );
  assert.deepEqual(contexts, ["injury", "weight", "fight_week"]);
});

test("a tip deck is a full shuffle of the pool", () => {
  const pool = selectLoadingTips(null, NOW);
  const deck = buildTipDeck(pool);
  assert.equal(deck.length, pool.length);
  assert.deepEqual(deck.map((tip) => tip.id).sort(), pool.map((tip) => tip.id).sort());
});

test("a new deck never opens with the tip that closed the last one", () => {
  const pool = selectLoadingTips(null, NOW);
  // random() === 0.999 leaves the deck in pool order, so the first tip is
  // deterministic and has to be swapped away from.
  const deck = buildTipDeck(pool, () => 0.999, pool[0].id);
  assert.notEqual(deck[0].id, pool[0].id);
});

test("cycling decks never shows the same tip twice in a row", () => {
  const pool = selectLoadingTips(intake({ injuries: "knee" }), NOW);
  let deck = buildTipDeck(pool);
  let previous: string | null = null;
  for (let pass = 0; pass < 200; pass += 1) {
    for (const tip of deck) {
      assert.notEqual(tip.id, previous);
      previous = tip.id;
    }
    deck = buildTipDeck(pool, Math.random, previous);
  }
});
