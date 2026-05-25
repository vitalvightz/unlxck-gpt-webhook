import type { UserRole } from "@/lib/types";

export function shouldShowAdminPanelLink(
  role: UserRole | null | undefined,
  isAdminRoute = false,
): boolean {
  return role === "admin" || isAdminRoute;
}
