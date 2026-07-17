export const PWA_DISPLAY_MODE_QUERY = "(display-mode: standalone)";
export const PWA_INSTALL_GUIDE_DISMISSED_KEY = "unlxck.pwaInstallGuideDismissedAt";

export type PwaInstallAvailability =
  | "checking"
  | "installed"
  | "ios-manual"
  | "native"
  | "unsupported";

const CRITICAL_WORKFLOW_PREFIXES = [
  "/admin",
  "/generate",
  "/intake",
  "/new-plan",
  "/onboarding",
  "/quick-build",
] as const;

export function isStandaloneDisplay(
  matchesStandalone: boolean,
  navigatorStandalone: boolean | undefined,
): boolean {
  return matchesStandalone || navigatorStandalone === true;
}

export function isIosDevice(userAgent: string, maxTouchPoints = 0): boolean {
  return /iPad|iPhone|iPod/i.test(userAgent) || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1);
}

export function resolvePwaInstallAvailability({
  hasNativePrompt,
  installed,
  ios,
}: {
  hasNativePrompt: boolean;
  installed: boolean | null;
  ios: boolean;
}): PwaInstallAvailability {
  if (installed === null) return "checking";
  if (installed) return "installed";
  if (hasNativePrompt) return "native";
  if (ios) return "ios-manual";
  return "unsupported";
}

export function isPwaCriticalWorkflow(pathname: string, search = ""): boolean {
  const normalizedPath = pathname !== "/" ? pathname.replace(/\/$/, "") : pathname;
  if (
    CRITICAL_WORKFLOW_PREFIXES.some(
      (prefix) => normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`),
    )
  ) {
    return true;
  }

  if (!normalizedPath.startsWith("/plans/")) {
    return false;
  }

  const params = new URLSearchParams(search);
  return params.get("review_required") === "1" || params.get("protected_triage") === "1";
}

export function shouldReloadForPwaControllerChange(
  refreshRequested: boolean,
  reloadStarted: boolean,
): boolean {
  return refreshRequested && !reloadStarted;
}

export function shouldRegisterServiceWorker(
  environment: string | undefined,
  serviceWorkerSupported: boolean,
): boolean {
  return environment === "production" && serviceWorkerSupported;
}

export function createPwaWorkerUrl(buildVersion: string | undefined): string {
  const versionInput = buildVersion?.trim() || "unlxck-local";
  let hash = 2166136261;

  for (let index = 0; index < versionInput.length; index += 1) {
    hash ^= versionInput.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return `/sw.js?build=${(hash >>> 0).toString(36)}`;
}

export function rememberInstallGuideDismissal(
  storage: Pick<Storage, "setItem">,
  dismissedAt = Date.now(),
): void {
  try {
    storage.setItem(PWA_INSTALL_GUIDE_DISMISSED_KEY, String(dismissedAt));
  } catch {
    // Installation remains available even if private browsing blocks storage.
  }
}
