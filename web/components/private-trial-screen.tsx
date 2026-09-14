"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PrivateTrialGuide } from "@/components/private-trial-guide";
import { updateMe } from "@/lib/api";
import { getAthleteWorkspaceHref } from "@/lib/auth-routing";
import { PRIVATE_TRIAL_ACKNOWLEDGE_LABEL, requiresPrivateTrialAcknowledgement } from "@/lib/private-trial";
import { useTranslations as useAppTranslations } from "next-intl";


/**
 * The one-time trial briefing, shown after account creation and before
 * onboarding. Testers were reaching intake without ever being told what the
 * trial asks of them, so this sits in the path rather than beside it.
 *
 * The acknowledgement is written to the profile, not to browser storage: a
 * tester who switches phones has still been briefed, and clearing site data
 * does not silently re-open the gate.
 */
function PrivateTrialAcknowledgement() {
    const appText = useAppTranslations("AppText");
  const router = useRouter();
  const { me, session, refreshMe } = useAppSession();
  const headingId = useId();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const token = session?.access_token ?? "";
  const isPending = requiresPrivateTrialAcknowledgement(me);
  const continueHref = getAthleteWorkspaceHref(me);

  // A non-athlete has no trial gate and no athlete workspace to continue into,
  // so send them back to wherever their role belongs instead of stranding them
  // on a screen whose only action does not apply.
  const role = me?.profile.role;
  useEffect(() => {
    if (role && role !== "athlete") {
      router.replace("/");
    }
  }, [role, router]);

  // Defensive fail-safe: once the durable profile marker exists, this route
  // must never render as a gate again. This also protects against stale links,
  // bookmarks, or any future route that accidentally points here.
  useEffect(() => {
    if (me?.profile.role === "athlete" && !isPending) {
      router.replace(continueHref);
    }
  }, [continueHref, isPending, me?.profile.role, router]);

  async function acknowledge() {
    if (isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await updateMe(token, { private_trial_acknowledged: true });
      // Force a fresh /me read before navigating. The auth provider normally
      // reuses the already-hydrated profile for the same access token, which is
      // correct for ordinary navigation but would otherwise leave this newly
      // written acknowledgement stale in client state.
      await refreshMe();
      router.replace(continueHref);
    } catch (acknowledgeError) {
      setError(
        acknowledgeError instanceof Error
          ? acknowledgeError.message
          : "Your confirmation could not be saved. Try again.",
      );
      setIsSubmitting(false);
    }
  }

  return (
    <section className="panel private-trial-panel" aria-labelledby={headingId}>
      <p className="kicker">{appText("text_e70b108ca4a7")}</p>
      <PrivateTrialGuide headingId={headingId} />
      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
      <div className="private-trial-actions">
        {isPending ? (
          <button type="button" className="cta" onClick={() => void acknowledge()} disabled={isSubmitting}>
            {isSubmitting ? appText("text_23e39291d613") : PRIVATE_TRIAL_ACKNOWLEDGE_LABEL}
          </button>
        ) : (
          <button type="button" className="cta" onClick={() => router.replace(continueHref)}>
            {appText("text_628db0c75988")}</button>
        )}
      </div>
      <p className="private-trial-settings-note muted">
        {appText("text_865e59e618fd")}</p>
    </section>
  );
}

export function PrivateTrialScreen() {
  return (
    <RequireAuth>
      <PrivateTrialAcknowledgement />
    </RequireAuth>
  );
}
