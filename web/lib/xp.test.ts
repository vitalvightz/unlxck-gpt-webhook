import test from "node:test";
import assert from "node:assert/strict";

import {
  XP_ACTIONS,
  XP_LEVELS,
  parseXpAwardResponse,
  resolveXpLevel,
} from "./xp";

const apiAward = (overrides: Record<string, unknown> = {}) => ({
  id: "11111111-1111-1111-1111-111111111111",
  action: "daily_login",
  amount: 10,
  awarded_at: "2026-08-01T12:00:00+00:00",
  calendar_date: "2026-08-01",
  ...overrides,
});

test("XP reward values are defined once for every planned action", () => {
  assert.deepEqual(
    Object.fromEntries(Object.entries(XP_ACTIONS).map(([action, config]) => [action, config.xp])),
    {
      daily_login: 10,
      training_logged: 25,
      planned_session_completed: 50,
      recommended_fighter_content_watched: 10,
      full_training_week_completed: 100,
    },
  );
});

test("level resolution is correct immediately below and at every threshold", () => {
  XP_LEVELS.forEach((level, index) => {
    assert.equal(resolveXpLevel(level.threshold).currentLevel.level, level.level);
    if (index > 0) {
      assert.equal(resolveXpLevel(level.threshold - 1).currentLevel.level, XP_LEVELS[index - 1].level);
    }
  });
});

test("level resolution reports within-level percentage and remaining XP", () => {
  const progress = resolveXpLevel(1_240);
  assert.equal(progress.currentLevel.level, 6);
  assert.equal(progress.currentLevel.title, "Contender");
  assert.equal(progress.nextLevel?.level, 7);
  assert.equal(progress.xpWithinLevel, 240);
  assert.equal(progress.xpForNextLevel, 300);
  assert.equal(progress.xpRemaining, 60);
  assert.equal(progress.percentage, 80);
});

test("maximum level stays full and tolerates XP beyond its threshold", () => {
  const progress = resolveXpLevel(5_000);
  assert.equal(progress.currentLevel.level, 8);
  assert.equal(progress.nextLevel, null);
  assert.equal(progress.percentage, 100);
  assert.equal(progress.xpRemaining, 0);
});

test("invalid XP totals resolve safely to a fresh Level 1 state", () => {
  for (const invalid of [-1, Number.NaN, Number.POSITIVE_INFINITY, "250", null]) {
    const progress = resolveXpLevel(invalid);
    assert.equal(progress.totalXp, 0);
    assert.equal(progress.currentLevel.level, 1);
    assert.equal(progress.percentage, 0);
  }
});

test("server XP responses map to presentation state", () => {
  const result = parseXpAwardResponse({
    state: {
      total_xp: 10,
      last_daily_login_date: "2026-08-01",
      recent_awards: [apiAward()],
    },
    previous_total_xp: 0,
    awarded: true,
    award: apiAward(),
  });

  assert.equal(result.state.totalXp, 10);
  assert.equal(result.state.lastDailyLoginDate, "2026-08-01");
  assert.equal(result.state.recentAwards[0]?.action, "daily_login");
  assert.equal(result.state.recentAwards[0]?.awardedAt, "2026-08-01T12:00:00.000Z");
  assert.equal(result.previousTotalXp, 0);
  assert.equal(result.awarded, true);
});

test("same-day no-op responses remain valid without triggering an animation", () => {
  const result = parseXpAwardResponse({
    state: {
      total_xp: 10,
      last_daily_login_date: "2026-08-01",
      recent_awards: [apiAward()],
    },
    previous_total_xp: 10,
    awarded: false,
    award: null,
  });

  assert.equal(result.awarded, false);
  assert.equal(result.award, null);
  assert.equal(result.state.totalXp, 10);
});

test("malformed, unknown, or reward-mismatched server data fails closed", () => {
  const invalidResponses = [
    null,
    {},
    {
      state: { total_xp: -1, last_daily_login_date: null, recent_awards: [] },
      previous_total_xp: 0,
      awarded: false,
      award: null,
    },
    {
      state: { total_xp: 10, last_daily_login_date: "2026-02-30", recent_awards: [] },
      previous_total_xp: 0,
      awarded: true,
      award: apiAward({ amount: 999 }),
    },
    {
      state: { total_xp: 10, last_daily_login_date: "2026-08-01", recent_awards: [apiAward({ action: "coins" })] },
      previous_total_xp: 0,
      awarded: false,
      award: null,
    },
  ];

  for (const response of invalidResponses) {
    assert.throws(() => parseXpAwardResponse(response), /invalid XP data/);
  }
});
