// Client-side view of the server's compliance rules.
//
// Nothing here *decides* anything: the server derives the age band and both
// consent verdicts and sends them on every `/api/me` read (see api/compliance.py).
// This module reads those verdicts to route and to label, and does one thing of
// its own — an under-13 pre-check on the signup form, so a child gets a clear
// message instead of a rejected request. That check is a courtesy, not the
// control; the backend and a Postgres trigger both reject an under-13 signup.

import type { MeResponse, ProfileRecord } from "@/lib/types";

/** Version strings mirroring api/compliance.py. Shown next to each consent. */
export const TERMS_VERSION = "0.1-pre-launch";
export const HEALTH_CONSENT_VERSION = "1.0";

export const MINIMUM_SIGNUP_AGE_YEARS = 13;
export const ADULT_AGE_YEARS = 18;

export const UNDER_MINIMUM_AGE_MESSAGE = `UNLXCK accounts are for athletes aged ${MINIMUM_SIGNUP_AGE_YEARS} or over.`;
export const DATE_OF_BIRTH_REQUIRED_MESSAGE = "Enter your date of birth to continue.";
export const DATE_OF_BIRTH_INVALID_MESSAGE = "Enter your date of birth as a valid date.";

export const TERMS_CONSENT_LABEL = "I have read and accept the Terms of Use.";
export const HEALTH_CONSENT_LABEL =
  "I explicitly consent to UNLXCK using my health information (injuries, pain, soreness, fatigue, sleep, readiness and bodyweight) to personalise my training and safety guidance.";
export const HEALTH_CONSENT_HELP =
  "This is separate from the Terms and you can withdraw it at any time in Settings. Without it, UNLXCK cannot run the features that depend on health information.";

/** Machine-readable codes the API returns on a blocked request. */
export const COMPLIANCE_ERROR_CODES = {
  dateOfBirthRequired: "date_of_birth_required",
  dateOfBirthInvalid: "date_of_birth_invalid",
  underMinimumAge: "under_minimum_age",
  termsRequired: "terms_acceptance_required",
  healthConsentRequired: "health_data_consent_required",
} as const;

/**
 * Completed years between `dateOfBirth` and `today`, or null if unparseable.
 *
 * Compared on the calendar date only. Using a timestamp difference would drift
 * by a day around leap years and time zones, which matters when someone signs
 * up on their thirteenth birthday.
 */
export function ageInYears(dateOfBirth: string, today: Date = new Date()): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateOfBirth.trim());
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }

  const todayYear = today.getFullYear();
  const todayMonth = today.getMonth() + 1;
  const todayDay = today.getDate();
  if (year > todayYear || (year === todayYear && (month > todayMonth || (month === todayMonth && day > todayDay)))) {
    return null;
  }

  let years = todayYear - year;
  if (todayMonth < month || (todayMonth === month && todayDay < day)) {
    years -= 1;
  }
  return years;
}

/** Signup-form validation message for a date of birth, or null when it passes. */
export function validateDateOfBirth(
  dateOfBirth: string,
  today: Date = new Date(),
): string | null {
  if (!dateOfBirth.trim()) {
    return DATE_OF_BIRTH_REQUIRED_MESSAGE;
  }
  const years = ageInYears(dateOfBirth, today);
  if (years === null) {
    return DATE_OF_BIRTH_INVALID_MESSAGE;
  }
  if (years < MINIMUM_SIGNUP_AGE_YEARS) {
    return UNDER_MINIMUM_AGE_MESSAGE;
  }
  return null;
}

function profileOf(me: MeResponse | null): ProfileRecord | null {
  return me?.profile ?? null;
}

/**
 * True while an athlete still owes a date of birth or a Terms acceptance.
 *
 * Only athletes are gated — admins, coaches and gym owners land on their own
 * workspaces and never pass through athlete onboarding. An unresolved profile is
 * never gated either: that is "not known yet", and blocking on it would strand
 * the loading state behind the gate. Mirrors requiresPrivateTrialAcknowledgement.
 */
export function requiresComplianceAcceptance(me: MeResponse | null): boolean {
  const profile = profileOf(me);
  if (!profile || profile.role !== "athlete") {
    return false;
  }
  return !profile.date_of_birth || !profile.meets_minimum_age || !profile.terms_accepted;
}

/** Whether health-dependent features may run for this athlete right now. */
export function hasHealthDataConsent(me: MeResponse | null): boolean {
  return Boolean(profileOf(me)?.health_consent_granted);
}

/** True once an athlete has consented and then withdrawn — used for Settings copy. */
export function hasWithdrawnHealthConsent(me: MeResponse | null): boolean {
  const profile = profileOf(me);
  if (!profile) {
    return false;
  }
  return Boolean(profile.health_consent_withdrawn_at) && !profile.health_consent_granted;
}

/** Settings summary line for the athlete's current consent state. */
export function healthConsentSummary(me: MeResponse | null): string {
  const profile = profileOf(me);
  if (!profile) {
    return "Unavailable";
  }
  if (profile.health_consent_granted) {
    return `Given (v${profile.health_consent_version ?? HEALTH_CONSENT_VERSION})`;
  }
  if (profile.health_consent_withdrawn_at) {
    return "Withdrawn";
  }
  return "Not given";
}

/** Settings summary line for Terms acceptance. */
export function termsSummary(me: MeResponse | null): string {
  const profile = profileOf(me);
  if (!profile) {
    return "Unavailable";
  }
  if (profile.terms_accepted) {
    return `Accepted (v${profile.terms_version ?? TERMS_VERSION})`;
  }
  return "Not accepted";
}
