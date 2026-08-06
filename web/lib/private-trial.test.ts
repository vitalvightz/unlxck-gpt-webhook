import test from "node:test";
import assert from "node:assert/strict";

import { getAthleteWorkspaceHref, getAuthenticatedLandingHref } from "@/lib/auth-routing";
import {
  PRIVATE_TRIAL_CHECKS,
  PRIVATE_TRIAL_DUTIES,
  requiresPrivateTrialAcknowledgement,
} from "@/lib/private-trial";
import type { MeResponse, UserRole } from "@/lib/types";

function meFixture({
  role = "athlete" as UserRole,
  ack = null as string | null,
  planId = null as string | null,
}): MeResponse {
  return {
    profile: {
      role,
      private_trial_ack_at: ack,
    },
    latest_plan: planId ? { plan_id: planId } : null,
  } as unknown as MeResponse;
}

test("an athlete who has not acknowledged the briefing is gated", () => {
  assert.equal(requiresPrivateTrialAcknowledgement(meFixture({})), true);
});

test("an acknowledged athlete is never gated again", () => {
  const me = meFixture({ ack: "2026-08-06T09:00:00Z" });
  assert.equal(requiresPrivateTrialAcknowledgement(me), false);
});

test("non-athlete roles are never gated", () => {
  for (const role of ["admin", "coach", "gym_owner"] as UserRole[]) {
    assert.equal(requiresPrivateTrialAcknowledgement(meFixture({ role })), false);
  }
});

test("an unresolved profile is not gated, so loading never stalls behind the screen", () => {
  assert.equal(requiresPrivateTrialAcknowledgement(null), false);
});

test("a fresh sign-up lands on the briefing, not on intake", () => {
  assert.equal(getAuthenticatedLandingHref(meFixture({})), "/private-trial");
});

test("the briefing sits ahead of an existing plan too, and only once", () => {
  const unacknowledged = meFixture({ planId: "plan-9" });
  assert.equal(getAuthenticatedLandingHref(unacknowledged), "/private-trial");

  const acknowledged = meFixture({ planId: "plan-9", ack: "2026-08-06T09:00:00Z" });
  assert.equal(getAuthenticatedLandingHref(acknowledged), "/plans/plan-9");
});

test("acknowledging continues to intake for an athlete with no plan yet", () => {
  assert.equal(getAthleteWorkspaceHref(meFixture({})), "/onboarding");
});

test("acknowledging continues to the latest plan when one exists", () => {
  assert.equal(getAthleteWorkspaceHref(meFixture({ planId: "plan-9" })), "/plans/plan-9");
});

test("role destinations still win over the trial gate", () => {
  assert.equal(getAuthenticatedLandingHref(meFixture({ role: "admin" })), "/admin");
  assert.equal(getAuthenticatedLandingHref(meFixture({ role: "coach" })), "/coach");
  assert.equal(getAuthenticatedLandingHref(meFixture({ role: "gym_owner" })), "/gym-owner");
});

test("the briefing covers what the tester must do and what they must check", () => {
  assert.equal(PRIVATE_TRIAL_DUTIES.length, 5);
  assert.equal(PRIVATE_TRIAL_CHECKS.length, 5);
  assert.ok(PRIVATE_TRIAL_DUTIES.some((duty) => duty.includes("feedback after completed sessions")));
  assert.ok(PRIVATE_TRIAL_CHECKS.some((check) => check.includes("difficulty")));
});
