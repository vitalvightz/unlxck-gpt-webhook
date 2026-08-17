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

export const TERMS_CONSENT_LEAD = "I accept the";
export const TERMS_LINK_LABEL = "Terms of Use";
export const TERMS_CONSENT_LABEL = `${TERMS_CONSENT_LEAD} ${TERMS_LINK_LABEL}.`;
export const SIGNUP_TERMS_CONSENT_LABEL = TERMS_CONSENT_LABEL;

/**
 * Age-appropriate privacy wording.
 *
 * The ICO's Age Appropriate Design Code expects privacy information "suited to
 * the age of the child", and the children policy asks for simpler explanations
 * at 13-15 and more mature wording at 16-17. The substance is identical in all
 * three bands — same data, same purpose, same right to refuse and withdraw —
 * only the register changes. Shortening it must never mean saying less about
 * what is collected or what declining costs.
 *
 * Keyed on the server-derived `age_band`, with `unknown` falling back to the
 * 13-15 wording: the plainest version is the safe default when we do not yet
 * know who is reading it.
 */
type AgeBand = "unknown" | "under_13" | "13-15" | "16-17" | "adult";

type ConsentCopy = {
  /**
   * Signup wording: short enough to read in full on a phone without scrolling
   * past it. The detail lives one tap away behind the Privacy Notice link that
   * sits beside the checkbox, and again in Settings once the account exists.
   */
  signupHealthConsentLabel: string;
  signupHealthConsentHelp: string;
  /**
   * Full wording, used where there is room to read it and where an athlete goes
   * specifically to understand or change the decision: Settings → Privacy and
   * the consent gate. Not shown at signup.
   */
  healthConsentLabel: string;
  healthConsentHelp: string;
  declineNote: string;
  privacySummary: string;
};

// Identical across bands: it is already as short and plain as it can be, and
// saying it the same way everywhere is what makes it read as a standing promise
// rather than band-specific small print.
const SIGNUP_CONSENT_LABEL =
  "I agree to UNLXCK using my health information to personalise my training.";
const SIGNUP_CONSENT_HELP = "Optional · Change anytime in Settings";

const EARLY_TEEN_COPY: ConsentCopy = {
  // Names the categories inline rather than saying "health data", so an athlete
  // does not have to follow a link to understand what they are agreeing to.
  signupHealthConsentLabel: SIGNUP_CONSENT_LABEL,
  signupHealthConsentHelp: SIGNUP_CONSENT_HELP,
  healthConsentLabel:
    "Yes, UNLXCK can use my health information to plan my training. That means things like injuries, pain, how sore or tired I am, how I slept, and my bodyweight.",
  healthConsentHelp:
    "This is a separate choice from the rules above. You do not have to say yes. If you say yes, we use this information to build your training and to tell you when to stop or take it easier. We do not show it to other users. You can change your mind whenever you want in Settings.",
  declineNote:
    "If you say no, you can still have an account. We just cannot build or change your training plan, because that needs this information.",
  privacySummary:
    "Your health information is used to plan your training and keep you safe. Only you and the UNLXCK team can see it. You can say no, or change your mind later.",
};

const CONSENT_COPY: Record<AgeBand, ConsentCopy> = {
  // A 13-15 reader is the most likely person behind an unresolved band, and the
  // plainest wording is never wrong for an older reader — only the reverse is.
  unknown: EARLY_TEEN_COPY,
  under_13: EARLY_TEEN_COPY,
  "13-15": EARLY_TEEN_COPY,
  "16-17": {
    signupHealthConsentLabel: SIGNUP_CONSENT_LABEL,
    signupHealthConsentHelp: SIGNUP_CONSENT_HELP,
    healthConsentLabel:
      "I consent to UNLXCK using my health information — injuries, pain, soreness, fatigue, sleep, readiness and bodyweight — to personalise my training and safety guidance.",
    healthConsentHelp:
      "This is a separate choice from the Terms and it is optional. We use this information to build and adapt your plan and to restrict training when our safety rules say you should ease off. It is not shared with other users. You can withdraw at any time in Settings.",
    declineNote:
      "You can decline and keep your account. Features that depend on health information — plan generation, check-ins and nutrition targets — will not run until you consent.",
    privacySummary:
      "UNLXCK uses your health information to personalise training and apply safety rules. It is not visible to other users, and your consent is optional and withdrawable.",
  },
  adult: {
    signupHealthConsentLabel: SIGNUP_CONSENT_LABEL,
    signupHealthConsentHelp: SIGNUP_CONSENT_HELP,
    healthConsentLabel:
      "I explicitly consent to UNLXCK using my health information (injuries, pain, soreness, fatigue, sleep, readiness and bodyweight) to personalise my training and safety guidance.",
    healthConsentHelp:
      "This is separate from the Terms and is optional. You can withdraw it at any time in Settings. Without it, UNLXCK cannot run the features that depend on health information.",
    declineNote:
      "Declining does not affect your account. Health-dependent features stay unavailable until consent is given.",
    privacySummary:
      "UNLXCK relies on your explicit consent (UK GDPR Art. 9(2)(a)) to process health data for personalised training and safety features.",
  },
};

/** Consent wording for a band, defaulting to the plainest version. */
export function consentCopyForBand(band: string | null | undefined): ConsentCopy {
  return CONSENT_COPY[(band ?? "unknown") as AgeBand] ?? EARLY_TEEN_COPY;
}

/**
 * The band implied by a date of birth still being typed into the signup form.
 *
 * Signup has no server verdict yet — the profile does not exist — so the form
 * derives the band locally purely to pick which wording to show. Nothing is
 * decided from it: the server re-derives the band from the stored date and owns
 * every downstream consequence.
 */
export function provisionalAgeBand(dateOfBirth: string, today: Date = new Date()): string {
  const years = ageInYears(dateOfBirth, today);
  if (years === null) {
    return "unknown";
  }
  if (years < MINIMUM_SIGNUP_AGE_YEARS) {
    return "under_13";
  }
  if (years < 16) {
    return "13-15";
  }
  if (years < ADULT_AGE_YEARS) {
    return "16-17";
  }
  return "adult";
}

// Adult wording kept as the module-level default for callers with no band.
export const HEALTH_CONSENT_LABEL = CONSENT_COPY.adult.healthConsentLabel;
export const HEALTH_CONSENT_HELP = CONSENT_COPY.adult.healthConsentHelp;

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

/**
 * Why signup cannot proceed yet, or null when it can.
 *
 * The mandatory/optional split lives here rather than inside the form so it is
 * one testable rule instead of a condition duplicated between a disabled button
 * and a submit handler. Health-data consent is deliberately absent: making it a
 * condition of getting an account would make it not freely given (UK GDPR
 * Art. 7(4)) and invalidate the Article 9(2)(a) basis it establishes.
 *
 * Client-side courtesy only — the backend and a Postgres trigger both reject an
 * under-13 signup, and the server stamps every consent record.
 */
export function signupConsentBlockReason(
  input: { dateOfBirth: string; acceptedTerms: boolean },
  today: Date = new Date(),
): string | null {
  const dateOfBirthError = validateDateOfBirth(input.dateOfBirth, today);
  if (dateOfBirthError) {
    return dateOfBirthError;
  }
  if (!input.acceptedTerms) {
    return TERMS_REQUIRED_MESSAGE;
  }
  return null;
}

export const TERMS_REQUIRED_MESSAGE = "Accept the Terms of Use to create an account.";

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
