import type { UserRole } from "@/lib/types";

// The plan viewer is shared between athletes and admins, so its controls split
// into two gates.

// General admin-only controls (permanent delete, view athlete profile, and other
// role-only admin actions) depend on the viewer's role alone — they must stay
// available to an admin even when a plan carries no admin_outputs.
export function isAdminRole(viewerRole: UserRole | null | undefined): boolean {
  return viewerRole === "admin";
}

// Admin-output-dependent controls (approve, reject approval, archive/admin
// review actions) require BOTH the admin role AND admin_outputs on the payload,
// so an athlete can never see them even if admin data were ever attached.
export function canUseAdminPlanControls(
  viewerRole: UserRole | null | undefined,
  hasAdminOutputs: boolean,
): boolean {
  return isAdminRole(viewerRole) && hasAdminOutputs;
}
