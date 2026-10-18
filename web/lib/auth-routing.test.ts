import assert from "node:assert/strict";
import test from "node:test";
import { getAuthenticatedLandingHref, needsStartingPath } from "./auth-routing";
import type { MeResponse } from "./types";

function account(overrides: Record<string, unknown> = {}): MeResponse {
  return { profile: { role: "athlete", starting_path: null, date_of_birth: "1995-01-01", meets_minimum_age: true, terms_accepted: true },
    plan_count: 0, latest_plan: null, latest_intake: null, ...overrides } as MeResponse;
}

test("only a resolved new athlete with no previous setup sees the choice", () => {
  assert.equal(getAuthenticatedLandingHref(account()), "/get-started");
  assert.equal(needsStartingPath(null), false);
  assert.equal(needsStartingPath(account({ profile: { role: "athlete" } })), false);
  assert.equal(needsStartingPath(account({ plan_count: 1 })), false);
  assert.equal(needsStartingPath(account({ latest_intake: {} })), false);
  const draft = account(); draft.profile.onboarding_draft = { current_step: 1 };
  assert.equal(needsStartingPath(draft), false);
});

test("saved paths survive landing and a saved plan still takes priority", () => {
  const me = account(); me.profile.starting_path = "tracking_first";
  assert.equal(getAuthenticatedLandingHref(me), "/today");
  me.latest_plan = { plan_id: "plan-9" } as NonNullable<MeResponse["latest_plan"]>;
  assert.equal(getAuthenticatedLandingHref(me), "/plans/plan-9");
  me.latest_plan = null; me.profile.starting_path = "plan_first";
  assert.equal(getAuthenticatedLandingHref(me), "/quick-build");
});

test("mandatory consent and staff routing precede starting choices", () => {
  const me = account(); me.profile.terms_accepted = false;
  assert.equal(getAuthenticatedLandingHref(me), "/consent");
  for (const [role, destination] of [["admin", "/admin"], ["coach", "/coach"], ["gym_owner", "/gym-owner"]] as const) {
    me.profile.role = role;
    assert.equal(getAuthenticatedLandingHref(me), destination);
  }
});
