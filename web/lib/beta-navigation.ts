// Beta navigation contract.
//
// For the live beta the standalone Nutrition workspace is switched off and Plan
// access is promoted to a first-class destination. On phones the bottom bar is
// the primary navigation (Overview, Today, Plan, History, Timer), with + Create
// (the /create choice screen) and the account menu at the top instead of a
// sidebar. Camp Setup is an occasional task reached from Create, not a tab. The Progress page is deliberately reached from the XP card on
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

// `/private-trial` and `/consent` are one-way gates: every tab would only bounce
// the athlete straight back to the gate, so the bar is dead chrome there (and it
// sat on top of the gate's only action). The Menu keeps sign-out reachable.
const TAB_BAR_HIDDEN_ROUTES = new Set<string>([
  "/get-started",
  "/generate",
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/private-trial",
  "/consent",
]);

// Whether the phone bottom bar (and with it + Create and the account button
// in place of the sidebar) belongs on this route. Admin keeps its sidebar.
export function showsMobileTabBar(pathname: string, signedIn: boolean): boolean {
  const isAdminRoute = pathname === "/admin" || pathname.startsWith("/admin/");
  return signedIn && !isAdminRoute && !TAB_BAR_HIDDEN_ROUTES.has(pathname);
}

export function isStandaloneNutritionPath(path: string): boolean {
  return /^\/nutrition(\/|\?|#|$)/.test(path);
}
