import { requiresPrivateTrialAcknowledgement } from "@/lib/private-trial";
import type { MeResponse } from "@/lib/types";

/**
 * Where an athlete belongs once the private trial briefing is behind them:
 * their latest plan if they have one, otherwise onboarding.
 *
 * Kept separate from `getAuthenticatedLandingHref` so the trial screen can send
 * the tester onwards after they acknowledge without re-entering the gate.
 */
export function getAthleteWorkspaceHref(me: MeResponse | null): string {
  if (me?.latest_plan?.plan_id) {
    return `/plans/${me.latest_plan.plan_id}`;
  }

  return "/onboarding";
}

export function getAuthenticatedLandingHref(me: MeResponse | null): string {
  if (me?.profile.role === "admin") {
    return "/admin";
  }

  // Coach and gym_owner are not live yet. No account currently holds these
  // roles, but route defensively to the protected "Coming soon" pages so they
  // never land in the athlete intake/dashboard flow if one is ever assigned.
  if (me?.profile.role === "coach") {
    return "/coach";
  }

  if (me?.profile.role === "gym_owner") {
    return "/gym-owner";
  }

  // The trial briefing sits between account creation and onboarding: a tester
  // has to know what the trial asks of them before they start answering intake
  // questions. It is shown once — the acknowledgement lives on the profile.
  if (requiresPrivateTrialAcknowledgement(me)) {
    return "/private-trial";
  }

  return getAthleteWorkspaceHref(me);
}
