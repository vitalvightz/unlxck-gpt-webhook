const PENDING_SOURCE_KEY = "unlxck:pending-plan-source";
const QUICK_BUILD_PLAN_IDS_KEY = "unlxck:quick-build-plan-ids";
const DISMISSED_KEY = "unlxck:quick-build-banner-dismissed";
const QUICK_BUILD_VALUE = "quick_build";
const PLAN_IDS_CAP = 25;
const DISMISSED_CAP = 50;

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

function readStringArray(storage: Storage, key: string): string[] {
  const raw = storage.getItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === "string") : [];
  } catch {
    storage.removeItem(key);
    return [];
  }
}

function writeCappedList(storage: Storage, key: string, list: string[], cap: number): void {
  const trimmed = list.length > cap ? list.slice(list.length - cap) : list;
  storage.setItem(key, JSON.stringify(trimmed));
}

export function markPendingQuickBuild(): void {
  if (!hasWindow()) return;
  try {
    window.sessionStorage.setItem(PENDING_SOURCE_KEY, QUICK_BUILD_VALUE);
  } catch {
    // sessionStorage can throw in private modes; failure here just disables the banner — non-critical.
  }
}

export function consumePendingQuickBuildForPlan(planId: string): void {
  if (!hasWindow() || !planId) return;
  try {
    const pending = window.sessionStorage.getItem(PENDING_SOURCE_KEY);
    if (pending !== QUICK_BUILD_VALUE) return;
    window.sessionStorage.removeItem(PENDING_SOURCE_KEY);

    const ids = readStringArray(window.localStorage, QUICK_BUILD_PLAN_IDS_KEY);
    if (ids.includes(planId)) return;
    ids.push(planId);
    writeCappedList(window.localStorage, QUICK_BUILD_PLAN_IDS_KEY, ids, PLAN_IDS_CAP);
  } catch {
    // Storage failures are non-critical; banner simply won't show.
  }
}

export function isQuickBuildPlan(planId: string): boolean {
  if (!hasWindow() || !planId) return false;
  try {
    return readStringArray(window.localStorage, QUICK_BUILD_PLAN_IDS_KEY).includes(planId);
  } catch {
    return false;
  }
}

export function isBannerDismissed(planId: string): boolean {
  if (!hasWindow() || !planId) return false;
  try {
    return readStringArray(window.localStorage, DISMISSED_KEY).includes(planId);
  } catch {
    return false;
  }
}

export function dismissBanner(planId: string): void {
  if (!hasWindow() || !planId) return;
  try {
    const list = readStringArray(window.localStorage, DISMISSED_KEY);
    if (list.includes(planId)) return;
    list.push(planId);
    writeCappedList(window.localStorage, DISMISSED_KEY, list, DISMISSED_CAP);
  } catch {
    // Non-critical.
  }
}
