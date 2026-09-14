"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { recordCompliance } from "@/lib/api";
import { getAuthenticatedLandingHref } from "@/lib/auth-routing";
import {

  hasHealthDataConsent,
  requiresComplianceAcceptance,
  validateDateOfBirth,
} from "@/lib/compliance";
import { useTranslations as useAppTranslations } from "next-intl";

/**
 * The consent step for an account that does not already have one on record.
 *
 * A signup completed through the current form arrives here already satisfied and
 * passes straight through. It exists for the accounts that predate the consent
 * fields, and for a session that lost its acceptance mid-signup — those athletes
 * would otherwise be stuck against a 403 from the onboarding gate with no way to
 * clear it.
 *
 * Deliberately shaped like the private-trial gate it sits next to: same profile-
 * backed marker, same "redirect once satisfied" fail-safe.
 */
function ComplianceAcceptance() {
    const appText = useAppTranslations("AppText");
  const router = useRouter();
  const { me, session, refreshMe } = useAppSession();
  const headingId = useId();
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [healthDataConsent, setHealthDataConsent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const token = session?.access_token ?? "";
  const role = me?.profile.role;
  const needsDateOfBirth = !me?.profile.date_of_birth || !me?.profile.meets_minimum_age;
  const needsTerms = !me?.profile.terms_accepted;
  const needsHealthConsent = !hasHealthDataConsent(me);
  const isPending = requiresComplianceAcceptance(me);
  const dateOfBirthError = needsDateOfBirth ? validateDateOfBirth(dateOfBirth) : null;
  const canContinue =
    !isSubmitting &&
    !dateOfBirthError &&
    (!needsTerms || acceptedTerms);

  // A non-athlete has no onboarding to gate; send them to their own workspace
  // rather than stranding them on a screen whose only action does not apply.
  useEffect(() => {
    if (role && role !== "athlete") {
      router.replace("/");
    }
  }, [role, router]);

  // Once the durable profile markers exist this route must never gate again —
  // protecting against stale links, bookmarks and a double submit.
  useEffect(() => {
    if (role === "athlete" && !isPending && !needsHealthConsent) {
      router.replace(getAuthenticatedLandingHref(me));
    }
  }, [isPending, me, needsHealthConsent, role, router]);

  async function submit() {
    if (isSubmitting) {
      return;
    }
    if (dateOfBirthError) {
      setError(dateOfBirthError);
      return;
    }
    if (needsTerms && !acceptedTerms) {
      setError("Accept the Terms of Use to continue.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await recordCompliance(token, {
        ...(needsDateOfBirth ? { date_of_birth: dateOfBirth } : {}),
        ...(needsTerms ? { accept_terms: acceptedTerms } : {}),
        // Only sent when ticked. Leaving it unticked must not be recorded as a
        // withdrawal — the athlete has not consented yet, which is a different
        // fact from having consented and changed their mind.
        ...(needsHealthConsent && healthDataConsent ? { health_data_consent: true } : {}),
      });
      await refreshMe();
      router.replace("/onboarding");
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Your details could not be saved. Try again.",
      );
      setIsSubmitting(false);
    }
  }

  return (
    <section className="panel private-trial-panel" aria-labelledby={headingId}>
      <p className="kicker">{appText("text_74e492d5d0df")}</p>
      <h1 id={headingId}>{appText("text_1cfa0bf3357f")}</h1>
      <p className="muted">
        {appText("text_e0196eab4f1d")}</p>

      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}

      {needsDateOfBirth ? (
        <div className="field">
          <label htmlFor="complianceDateOfBirth">{appText("text_eb4c4e239122")}</label>
          <input
            id="complianceDateOfBirth"
            type="date"
            autoComplete="bday"
            value={dateOfBirth}
            onChange={(event) => setDateOfBirth(event.target.value)}
            required
          />
        </div>
      ) : null}

      {needsTerms ? (
        <div className="field auth-consent-field">
          <label className="auth-consent-row" htmlFor="complianceTerms">
            <input
              id="complianceTerms"
              type="checkbox"
              checked={acceptedTerms}
              onChange={(event) => setAcceptedTerms(event.target.checked)}
            />
            <span>
              {appText("text_b84e86ef620c")}{" "}
              <Link href="/terms" className="auth-text-link" target="_blank">
                {appText("text_12a0015fa322")}</Link>
              {appText("text_cdb4ee2aea69")}</span>
          </label>
          <div className="auth-consent-help">
            <Link href="/privacy" className="auth-text-link" target="_blank">
              {appText("text_840b0e9da5da")}</Link>
          </div>
        </div>
      ) : null}

      {needsHealthConsent ? (
        <div className="field auth-consent-field">
          <label className="auth-consent-row" htmlFor="complianceHealthConsent">
            <input
              id="complianceHealthConsent"
              type="checkbox"
              checked={healthDataConsent}
              onChange={(event) => setHealthDataConsent(event.target.checked)}
            />
            <span>{appText("text_03fe73a06efe")}</span>
          </label>
        </div>
      ) : null}

      <div className="private-trial-actions">
        <button type="button" className="cta" onClick={() => void submit()} disabled={!canContinue}>
          {isSubmitting ? appText("text_23e39291d613") : appText("text_628db0c75988")}
        </button>
      </div>
    </section>
  );
}

export function ComplianceGateScreen() {
  return (
    <RequireAuth>
      <ComplianceAcceptance />
    </RequireAuth>
  );
}
