import type { UserRole } from "@/lib/types";

// The plan viewer is shared between athletes and admins. Admin-only controls
// (approve, reject approval, archive/admin review actions) must be gated by the
// viewer's role, not merely by the presence of admin_outputs in the payload, so
// an athlete can never see them even if admin data were ever attached.
export function canUseAdminPlanControls(
  viewerRole: UserRole | null | undefined,
  hasAdminOutputs: boolean,
): boolean {
  return viewerRole === "admin" && hasAdminOutputs;
}
