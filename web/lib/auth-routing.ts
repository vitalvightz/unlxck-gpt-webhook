import type { MeResponse } from "@/lib/types";

export function getAuthenticatedLandingHref(me: MeResponse | null): string {
  if (me?.profile.role === "admin") {
    return "/admin";
  }

  if (me?.latest_plan?.plan_id) {
    return `/plans/${me.latest_plan.plan_id}`;
  }

  return "/onboarding";
}
