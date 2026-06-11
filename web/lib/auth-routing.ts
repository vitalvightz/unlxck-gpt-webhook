import type { MeResponse } from "@/lib/types";

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

  if (me?.latest_plan?.plan_id) {
    return `/plans/${me.latest_plan.plan_id}`;
  }

  return "/onboarding";
}
