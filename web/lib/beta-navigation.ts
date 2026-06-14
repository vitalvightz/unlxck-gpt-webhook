// Beta navigation contract.
//
// For the live beta the standalone Nutrition workspace is switched off and Plan
// access is promoted to a first-class bottom-nav destination. Keeping the nav
// shape (and the nutrition kill-switch) in one pure module means the React
// shells stay declarative and the behaviour is unit-testable without a DOM.

export type NavItem = {
  href: string;
  label: string;
  // Optional supporting copy shown in the side drawer (ignored by the bottom bar).
  meta?: string;
};

// Standalone Nutrition is disabled for beta. Plan-level nutrition that ships
// *inside* a generated structured plan is unaffected by this flag — this only
// governs the standalone /nutrition workspace route and its nav entries.
// Typed as `boolean` (not the literal `false`) so callers that branch on it do
// not trip unreachable-code narrowing.
export const STANDALONE_NUTRITION_ENABLED: boolean = false;

// Where a direct hit on a disabled standalone Nutrition route lands.
export const NUTRITION_DISABLED_REDIRECT = "/";

// Mobile bottom navigation — exactly four first-class destinations for beta:
// Overview, Today, Plan, Intake. Plan replaces the old Nutrition tab so plans
// are never buried in the side drawer.
export const BOTTOM_NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/dashboard", label: "Today" },
  { href: "/plans", label: "Plan" },
  { href: "/onboarding", label: "Intake" },
] as const;

// Side drawer / workspace menu for signed-in athletes: Overview, Today, Plan,
// Intake, Settings. Standalone Nutrition is intentionally absent for beta.
export const SIDE_NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview", meta: "Camp status" },
  { href: "/dashboard", label: "Today", meta: "Check-in and session log" },
  { href: "/plans", label: "Plan", meta: "Active and saved plans" },
  { href: "/onboarding", label: "Intake", meta: "Profile and camp setup" },
  { href: "/settings", label: "Settings", meta: "Athlete profile" },
] as const;

// True for the standalone Nutrition workspace route and any of its sub-pages
// (e.g. /nutrition/bodyweight-log). Used to gate the beta redirect.
export function isStandaloneNutritionPath(path: string): boolean {
  return path === "/nutrition" || path.startsWith("/nutrition/");
}
