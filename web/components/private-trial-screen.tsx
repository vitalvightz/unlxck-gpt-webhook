"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PrivateTrialGuide } from "@/components/private-trial-guide";
import { updateMe } from "@/lib/api";
import { getAthleteWorkspaceHref } from "@/lib/auth-routing";
import { PRIVATE_TRIAL_ACKNOWLEDGE_LABEL, requiresPrivateTrialAcknowledgement } from "@/lib/private-trial";

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

  async function acknowledge() {
    if (isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await updateMe(token, { private_trial_acknowledged: true });
      // Refresh before navigating: the landing resolver reads the
      // acknowledgement off `me`, and a stale profile would bounce the tester
      // straight back to this screen.
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
      <p className="kicker">Private trial</p>
      <PrivateTrialGuide headingId={headingId} />
      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
      <div className="private-trial-actions">
        {isPending ? (
          <button type="button" className="cta" onClick={() => void acknowledge()} disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : PRIVATE_TRIAL_ACKNOWLEDGE_LABEL}
          </button>
        ) : (
          <button type="button" className="cta" onClick={() => router.replace(continueHref)}>
            CONTINUE
          </button>
        )}
      </div>
      <p className="private-trial-settings-note muted">
        You can read this again at any time in Settings under Private Trial Guide.
      </p>
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
