// Helpers for degrading admin review/resume queues when the profile service is
// temporarily unavailable. The queues must stay visible and actionable even
// when athlete profile enrichment fails, so this module:
//   * detects the "profile service temporarily unavailable" style errors,
//   * pulls the latest request id out of those messages for support,
//   * consolidates the per-section failures into a single compact banner.
// Keeping the logic here (pure, framework-free) lets it be unit tested with
// node:test and reused by the admin page without duplicating string matching.

export const PROFILE_SERVICE_WARNING_TITLE = "Profile service temporarily unavailable.";
export const PROFILE_SERVICE_WARNING_BODY =
  "Queues are shown with limited athlete details.";
export const PROFILE_UNAVAILABLE_ROW_LABEL = "Profile unavailable";

// Lower-cased fragments of the transient profile/store errors surfaced by the
// API layer (see web/lib/api.ts RETRYABLE_INTERNAL_ERROR_SNIPPETS and the
// backend 503 details). A section error containing any of these is treated as a
// degraded-profile signal rather than a hard failure.
const PROFILE_SERVICE_ERROR_SNIPPETS = [
  "profile service temporarily unavailable",
  "store service temporarily unavailable",
  "failed to ensure profile",
];

export function isProfileServiceUnavailableMessage(message: string | null | undefined): boolean {
  if (!message) return false;
  const normalized = message.toLowerCase();
  return PROFILE_SERVICE_ERROR_SNIPPETS.some((snippet) => normalized.includes(snippet));
}

// Error messages carry the request id inline as "(request id: <id>)" — see
// web/lib/api.ts. Pull the last one so the banner can surface the most recent
// failure for support without showing the full stacked error blocks.
export function extractRequestId(message: string | null | undefined): string | null {
  if (!message) return null;
  let requestId: string | null = null;
  const pattern = /\(request id:\s*([^)]+)\)/gi;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(message)) !== null) {
    const candidate = match[1]?.trim();
    if (candidate) {
      requestId = candidate;
    }
  }
  return requestId;
}

export type ProfileWarningInput = {
  // Per-section error strings (active jobs, triage, plans, reviews, directory).
  sectionErrors?: Array<string | null | undefined>;
  // True when any rendered row was returned with degraded profile enrichment.
  rowsDegraded?: boolean;
  // Latest request id observed on a degraded fetch, if the caller tracked it.
  requestId?: string | null;
};

export type ProfileWarningSummary = {
  show: boolean;
  requestId: string | null;
};

// Collapse every profile-service signal across the page into one banner. The
// banner shows when either a section failed with a profile-service error or a
// queue rendered rows with degraded enrichment. The newest available request id
// wins so support can trace the latest failure.
export function summarizeProfileWarning(input: ProfileWarningInput): ProfileWarningSummary {
  const sectionErrors = (input.sectionErrors ?? []).filter(
    (message): message is string => typeof message === "string" && message.length > 0,
  );
  const profileSectionErrors = sectionErrors.filter(isProfileServiceUnavailableMessage);
  const show = input.rowsDegraded === true || profileSectionErrors.length > 0;

  let requestId = input.requestId?.trim() || null;
  if (!requestId) {
    for (const message of profileSectionErrors) {
      const candidate = extractRequestId(message);
      if (candidate) {
        requestId = candidate;
      }
    }
  }

  return { show, requestId };
}

// A profile-service section error is no longer worth showing as its own block
// once the compact banner is visible. Returns the section errors that are NOT
// profile-service related, so genuine queue failures still surface inline.
export function nonProfileSectionError(message: string | null | undefined): string | null {
  if (!message) return null;
  return isProfileServiceUnavailableMessage(message) ? null : message;
}
