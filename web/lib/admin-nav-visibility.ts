import type { UserRole } from "@/lib/types";

export function shouldShowAdminPanelLink(role: UserRole | null | undefined): boolean {
  return role === "admin";
}
