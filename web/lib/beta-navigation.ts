// Beta navigation contract.
//
// For the live beta the standalone Nutrition workspace is switched off and Plan
// access is promoted to a first-class destination. Intake remains in the compact
// bottom navigation. The Progress page is deliberately reached from the XP card
// on Overview for now, rather than being promoted into primary navigation.

export type NavItem = {
  href: string;
  label: string;
  meta?: string;
};

// Standalone Nutrition is disabled for beta. Plan-level nutrition inside a
// generated structured plan is unaffected by this flag.
export const STANDALONE_NUTRITION_ENABLED: boolean = false;

export const NUTRITION_DISABLED_REDIRECT = "/";

export const BOTTOM_NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/today", label: "Today" },
  { href: "/plans", label: "Plan" },
  { href: "/onboarding", label: "Intake" },
] as const;

export const SIDE_NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview", meta: "Camp status" },
  { href: "/today", label: "Today", meta: "Check-in and session log" },
  { href: "/plans", label: "Plan", meta: "Active and saved plans" },
  { href: "/history", label: "History", meta: "Sessions, check-ins, injuries" },
  { href: "/onboarding", label: "Intake", meta: "Profile and camp setup" },
  { href: "/settings", label: "Settings", meta: "Athlete profile" },
] as const;

export function isStandaloneNutritionPath(path: string): boolean {
  return /^\/nutrition(\/|\?|#|$)/.test(path);
}
