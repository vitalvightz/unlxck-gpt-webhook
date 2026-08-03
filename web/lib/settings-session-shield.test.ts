import assert from "node:assert/strict";
import test from "node:test";

import { reconcileSettingsMe } from "./settings-session-shield.ts";
import type { MeResponse } from "./types.ts";

function makeMe(): MeResponse {
  return {
    profile: {
      athlete_id: "11111111-1111-4111-8111-111111111111",
      email: "athlete@example.com",
      role: "athlete",
      full_name: "Michael",
      technical_style: ["boxing"],
      tactical_style: [],
      stance: "orthodox",
      professional_status: "amateur",
      record: "0-0",
      athlete_timezone: "Europe/London",
      athlete_locale: "en-GB",
      appearance_mode: "dark",
      avatar_url: "https://example.com/avatar.jpg",
      nutrition_profile: {
        dietary_restrictions: [],
        food_preferences: [],
        foods_avoided_pre_session: [],
        foods_avoided_fight_week: [],
        supplement_use: [],
      },
      created_at: "2026-08-03T19:00:00Z",
      updated_at: "2026-08-03T20:00:00Z",
    },
    latest_intake: null,
    latest_plan: null,
    plan_count: 0,
    username_rate_limit: {
      remaining: 4,
      max_changes_per_window: 4,
      window_days: 30,
      next_available_at: null,
    },
  };
}

test("keeps the settings me identity for a delayed timezone-only response", () => {
  const current = makeMe();
  const timezoneResponse: MeResponse = {
    ...current,
    profile: {
      ...current.profile,
      athlete_timezone: "Asia/Tokyo",
      updated_at: "2026-08-03T20:01:00Z",
    },
  };

  assert.strictEqual(reconcileSettingsMe(current, timezoneResponse), current);
});

test("accepts account-field changes so a successful save can rehydrate", () => {
  const current = makeMe();
  const savedAccount: MeResponse = {
    ...current,
    profile: {
      ...current.profile,
      full_name: "Michael Okafor",
      updated_at: "2026-08-03T20:02:00Z",
    },
  };

  assert.strictEqual(reconcileSettingsMe(current, savedAccount), savedAccount);
});

test("accepts a different account instead of preserving the old snapshot", () => {
  const current = makeMe();
  const nextAccount: MeResponse = {
    ...current,
    profile: {
      ...current.profile,
      athlete_id: "22222222-2222-4222-8222-222222222222",
      athlete_timezone: "Asia/Tokyo",
    },
  };

  assert.strictEqual(reconcileSettingsMe(current, nextAccount), nextAccount);
});
