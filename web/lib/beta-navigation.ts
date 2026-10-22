// Beta navigation contract.
//
// For the live beta the standalone Nutrition workspace is switched off and Plan
// access is promoted to a first-class destination. On phones the bottom bar is
// the primary navigation (Overview, Today, Plan, History, Timer); Camp Setup is
// an occasional task reached from Plan's "New programme" chooser rather than a
// permanent tab. The Progress page is deliberately reached from the XP card on
// Overview for now, rather than being promoted into primary navigation.

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
  { href: "/history", label: "History" },
  { href: "/timer", label: "Timer" },
] as const;

export const SIDE_NAV_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Overview", meta: "Camp status" },
  { href: "/today", label: "Today", meta: "Check-in and session log" },
  { href: "/plans", label: "Plan", meta: "Active and saved plans" },
  { href: "/history", label: "History", meta: "Sessions, check-ins, injuries" },
  { href: "/timer", label: "Round timer", meta: "Rounds and rest, any time" },
  { href: "/onboarding", label: "Camp Setup", meta: "Start or edit your camp" },
  { href: "/settings", label: "Settings", meta: "Account & preferences" },
] as const;

// While the bottom bar is showing, the phone menu becomes a compact account
// menu: everything the bar already covers (and Camp Setup, which lives under
// Plan) is left out so the profile, language and sign out always fit.
export function isAccountMenuItem(href: string): boolean {
  return href === "/settings";
}

export function isStandaloneNutritionPath(path: string): boolean {
  return /^\/nutrition(\/|\?|#|$)/.test(path);
}
