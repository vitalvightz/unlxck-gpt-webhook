// Local-only dismissal store for the Quick Build refinement banner.
// The source of truth for "this plan came from Quick Build" lives in the backend
// (generation_jobs.source, surfaced as PlanDetail.plan_source). This file only
// remembers which plan ids the user has chosen to hide the banner for, on this device.

const DISMISSED_KEY = "unlxck:quick-build-banner-dismissed";
const DISMISSED_CAP = 50;

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

function readDismissed(): string[] {
  const raw = window.localStorage.getItem(DISMISSED_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === "string") : [];
  } catch {
    window.localStorage.removeItem(DISMISSED_KEY);
    return [];
  }
}

export function isBannerDismissed(planId: string): boolean {
  if (!hasWindow() || !planId) return false;
  try {
    return readDismissed().includes(planId);
  } catch {
    return false;
  }
}

export function dismissBanner(planId: string): void {
  if (!hasWindow() || !planId) return;
  try {
    const list = readDismissed();
    if (list.includes(planId)) return;
    list.push(planId);
    const trimmed = list.length > DISMISSED_CAP ? list.slice(list.length - DISMISSED_CAP) : list;
    window.localStorage.setItem(DISMISSED_KEY, JSON.stringify(trimmed));
  } catch {
    // Non-critical: dismissal failures just mean the banner reappears next visit.
  }
}
