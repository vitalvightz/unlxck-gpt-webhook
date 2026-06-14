import type { UserRole } from "@/lib/types";

export function isAdminRole(viewerRole: UserRole | null | undefined): boolean {
  return viewerRole === "admin";
}

export function canUseAdminPlanControls(
  viewerRole: UserRole | null | undefined,
  hasAdminOutputs: boolean,
): boolean {
  return isAdminRole(viewerRole) && hasAdminOutputs;
}
