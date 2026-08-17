import test from "node:test";
import assert from "node:assert/strict";

import { getAuthenticatedLandingHref } from "@/lib/auth-routing";
import {
  HEALTH_CONSENT_VERSION,
  MINIMUM_SIGNUP_AGE_YEARS,
  TERMS_VERSION,
  UNDER_MINIMUM_AGE_MESSAGE,
  ageInYears,
  consentCopyForBand,
  provisionalAgeBand,
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


test("the provisional band tracks the ICO developmental groups", () => {
  assert.equal(provisionalAgeBand(dobForAge(14), TODAY), "13-15");
  assert.equal(provisionalAgeBand(dobForAge(15), TODAY), "13-15");
  assert.equal(provisionalAgeBand(dobForAge(16), TODAY), "16-17");
  assert.equal(provisionalAgeBand(dobForAge(17), TODAY), "16-17");
  assert.equal(provisionalAgeBand(dobForAge(18), TODAY), "adult");
  assert.equal(provisionalAgeBand(dobForAge(12), TODAY), "under_13");
  assert.equal(provisionalAgeBand("", TODAY), "unknown");
});

test("each age band gets its own consent wording", () => {
  const early = consentCopyForBand("13-15");
  const older = consentCopyForBand("16-17");
  const adult = consentCopyForBand("adult");

  assert.notEqual(early.healthConsentLabel, older.healthConsentLabel);
  assert.notEqual(older.healthConsentLabel, adult.healthConsentLabel);
});

test("an unknown band falls back to the plainest wording", () => {
  // The plainest version is never wrong for an older reader; the reverse is.
  assert.deepEqual(consentCopyForBand("unknown"), consentCopyForBand("13-15"));
  assert.deepEqual(consentCopyForBand(undefined), consentCopyForBand("13-15"));
  assert.deepEqual(consentCopyForBand("nonsense"), consentCopyForBand("13-15"));
});

test("the 13-15 wording is plainer than the adult wording", () => {
  const early = consentCopyForBand("13-15");
  const adult = consentCopyForBand("adult");

  // Legal register that a 13-year-old should not have to decode.
  for (const jargon of ["explicitly consent", "UK GDPR", "Art. 9"]) {
    assert.ok(
      !early.healthConsentLabel.includes(jargon) && !early.healthConsentHelp.includes(jargon),
      `early-teen copy should avoid "${jargon}"`,
    );
  }
  assert.ok(adult.privacySummary.includes("Art. 9(2)(a)"));
});

test("every band still says what is collected, that it is optional, and what declining costs", () => {
  // Simpler wording must never mean saying less about the substance.
  for (const band of ["13-15", "16-17", "adult"]) {
    const copy = consentCopyForBand(band);
    const all = `${copy.healthConsentLabel} ${copy.healthConsentHelp}`.toLowerCase();

    // The categories of data. Matched as concepts, not exact words: the
    // early-teen copy says "how I slept", which names sleep perfectly well and
    // is the plainer phrasing the whole band exists to allow.
    const categories: Array<[string, RegExp]> = [
      ["injuries", /injur/],
      ["sleep", /sleep|slept/],
      ["bodyweight", /bodyweight|body weight/],
      ["soreness or fatigue", /sore|tired|fatigue/],
    ];
    for (const [name, pattern] of categories) {
      assert.ok(pattern.test(all), `${band} copy should name ${name}`);
    }
    // That it is a choice, and reversible.
    assert.ok(
      /do not have to|optional|you can decline/.test(all),
      `${band} copy should say the consent is optional`,
    );
    assert.ok(
      /change your mind|withdraw/.test(all),
      `${band} copy should say it can be withdrawn`,
    );
    // What refusing means.
    assert.ok(copy.declineNote.length > 0, `${band} copy should explain declining`);
  }
});

test("declining health consent never blocks the account in any band", () => {
  for (const band of ["13-15", "16-17", "adult"]) {
    const note = consentCopyForBand(band).declineNote.toLowerCase();
    assert.ok(
      /still have an account|keep your account|does not affect your account/.test(note),
      `${band} decline note should confirm the account survives`,
    );
  }
});
