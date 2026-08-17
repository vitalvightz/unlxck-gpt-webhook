import test from "node:test";
import assert from "node:assert/strict";

import { getAuthenticatedLandingHref } from "@/lib/auth-routing";
import {
  HEALTH_CONSENT_VERSION,
  MINIMUM_SIGNUP_AGE_YEARS,
  TERMS_VERSION,
  UNDER_MINIMUM_AGE_MESSAGE,
  ageInYears,
  hasHealthDataConsent,
  hasWithdrawnHealthConsent,
  healthConsentSummary,
  requiresComplianceAcceptance,
  termsSummary,
  validateDateOfBirth,
} from "@/lib/compliance";
import type { MeResponse, ProfileRecord, UserRole } from "@/lib/types";

const TODAY = new Date(2026, 7, 17); // 17 August 2026, local time.

function dobForAge(years: number): string {
  const year = TODAY.getFullYear() - years;
  const month = String(TODAY.getMonth() + 1).padStart(2, "0");
  const day = String(TODAY.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function meFixture(profile: Partial<ProfileRecord> & { role?: UserRole } = {}): MeResponse {
  return {
    profile: {
      role: "athlete" as UserRole,
      date_of_birth: "1996-05-04",
      meets_minimum_age: true,
      is_minor: false,
      terms_accepted: true,
      terms_version: TERMS_VERSION,
      health_consent_granted: true,
      health_consent_version: HEALTH_CONSENT_VERSION,
      ...profile,
    },
    latest_plan: null,
  } as unknown as MeResponse;
}

test("age is counted in completed years", () => {
  assert.equal(ageInYears("2013-08-18", TODAY), 12);
  assert.equal(ageInYears("2013-08-17", TODAY), 13);
  assert.equal(ageInYears("2008-01-01", TODAY), 18);
});

test("a malformed or impossible date has no age", () => {
  assert.equal(ageInYears("not-a-date", TODAY), null);
  assert.equal(ageInYears("2026-02-30", TODAY), null);
  assert.equal(ageInYears("2027-01-01", TODAY), null);
});

test("under-13 is rejected on the signup form", () => {
  assert.equal(validateDateOfBirth(dobForAge(12), TODAY), UNDER_MINIMUM_AGE_MESSAGE);
  assert.equal(validateDateOfBirth(dobForAge(0), TODAY), UNDER_MINIMUM_AGE_MESSAGE);
});

test("13 and over passes the signup form check", () => {
  assert.equal(validateDateOfBirth(dobForAge(MINIMUM_SIGNUP_AGE_YEARS), TODAY), null);
  assert.equal(validateDateOfBirth(dobForAge(17), TODAY), null);
  assert.equal(validateDateOfBirth(dobForAge(30), TODAY), null);
});

test("a blank or unparseable date of birth is refused", () => {
  assert.notEqual(validateDateOfBirth("", TODAY), null);
  assert.notEqual(validateDateOfBirth("   ", TODAY), null);
  assert.notEqual(validateDateOfBirth("04/05/1996", TODAY), null);
});

test("an athlete without a date of birth or Terms is gated", () => {
  assert.equal(requiresComplianceAcceptance(meFixture({ date_of_birth: null })), true);
  assert.equal(requiresComplianceAcceptance(meFixture({ terms_accepted: false })), true);
  assert.equal(requiresComplianceAcceptance(meFixture({ meets_minimum_age: false })), true);
});

test("a fully accepted athlete is not gated", () => {
  assert.equal(requiresComplianceAcceptance(meFixture()), false);
});

test("non-athletes and an unresolved profile are never gated", () => {
  // Admins have their own workspace; an unhydrated profile is "not known yet".
  assert.equal(requiresComplianceAcceptance(meFixture({ role: "admin" })), false);
  assert.equal(requiresComplianceAcceptance(null), false);
});

test("the landing resolver sends an unaccepted athlete to the consent gate", () => {
  assert.equal(getAuthenticatedLandingHref(meFixture({ terms_accepted: false })), "/consent");
});

test("consent comes before the private-trial briefing", () => {
  const unbriefed = meFixture({ terms_accepted: false, private_trial_ack_at: null });
  assert.equal(getAuthenticatedLandingHref(unbriefed), "/consent");

  const accepted = meFixture({ private_trial_ack_at: null });
  assert.equal(getAuthenticatedLandingHref(accepted), "/private-trial");
});

test("an accepted, briefed athlete still lands in their workspace", () => {
  const ready = meFixture({ private_trial_ack_at: "2026-08-01T00:00:00+00:00" });
  assert.equal(getAuthenticatedLandingHref(ready), "/onboarding");
});

test("health consent is read from the server verdict, not recomputed", () => {
  assert.equal(hasHealthDataConsent(meFixture()), true);
  assert.equal(hasHealthDataConsent(meFixture({ health_consent_granted: false })), false);
});

test("a withdrawn consent is distinguishable from one never given", () => {
  const withdrawn = meFixture({
    health_consent_granted: false,
    health_consent_withdrawn_at: "2026-08-10T00:00:00+00:00",
  });
  const neverGiven = meFixture({
    health_consent_granted: false,
    health_consent_at: null,
    health_consent_withdrawn_at: null,
  });

  assert.equal(hasWithdrawnHealthConsent(withdrawn), true);
  assert.equal(hasWithdrawnHealthConsent(neverGiven), false);
  assert.equal(healthConsentSummary(withdrawn), "Withdrawn");
  assert.equal(healthConsentSummary(neverGiven), "Not given");
});

test("settings summaries state the recorded version, not a generic phrase", () => {
  // Replaces the old, inaccurate "Account required data only" wording.
  assert.equal(healthConsentSummary(meFixture()), `Given (v${HEALTH_CONSENT_VERSION})`);
  assert.equal(termsSummary(meFixture()), `Accepted (v${TERMS_VERSION})`);
  assert.equal(termsSummary(meFixture({ terms_accepted: false })), "Not accepted");
});
