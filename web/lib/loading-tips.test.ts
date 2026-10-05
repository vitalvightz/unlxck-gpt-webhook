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

test("a deck covers the whole bank, contextual tips first", () => {
  const primary = selectLoadingTips(intake({ injuries: "knee" }), NOW);
  const deck = buildTipDeck(primary);
  assert.equal(deck.length, LOADING_TIPS.length);
  assert.equal(new Set(deck.map((tip) => tip.id)).size, LOADING_TIPS.length);
  const primaryIds = new Set(primary.map((tip) => tip.id));
  assert.ok(deck.slice(0, primary.length).every((tip) => primaryIds.has(tip.id)));
});

test("the bank is big enough that a 10-minute build at 5s per tip never repeats", () => {
  // 10 minutes / 5 seconds = 120 tips; every context must have more than that.
  assert.ok(LOADING_TIPS.length > 120, `${LOADING_TIPS.length} tips`);
  for (const category of new Set(LOADING_TIPS.map((tip) => tip.category))) {
    const count = LOADING_TIPS.filter((tip) => tip.category === category).length;
    assert.ok(count >= 15, `${category} has only ${count} tips`);
  }
});

test("tips seen in earlier builds move behind fresh ones", () => {
  const primary = selectLoadingTips(null, NOW);
  const recentlySeen = primary.slice(0, 10).map((tip) => tip.id);
  const deck = buildTipDeck(primary, { recentlySeen });
  const freshCount = LOADING_TIPS.length - recentlySeen.length;
  assert.ok(deck.slice(0, freshCount).every((tip) => !recentlySeen.includes(tip.id)));
  assert.deepEqual(new Set(deck.slice(freshCount).map((tip) => tip.id)), new Set(recentlySeen));
});

test("a new deck never opens with the tip that closed the last one", () => {
  const primary = selectLoadingTips(null, NOW);
  // random() === 0.999 leaves each tier in its original order, so the first
  // tip is deterministic and has to be swapped away from.
  const deck = buildTipDeck(primary, { random: () => 0.999, avoidFirstId: primary[0].id });
  assert.notEqual(deck[0].id, primary[0].id);
});

test("cycling decks never shows the same tip twice in a row", () => {
  const primary = selectLoadingTips(intake({ injuries: "knee" }), NOW);
  let deck = buildTipDeck(primary);
  let previous: string | null = null;
  for (let pass = 0; pass < 50; pass += 1) {
    for (const tip of deck) {
      assert.notEqual(tip.id, previous);
      previous = tip.id;
    }
    deck = buildTipDeck(primary, { avoidFirstId: previous });
  }
});
