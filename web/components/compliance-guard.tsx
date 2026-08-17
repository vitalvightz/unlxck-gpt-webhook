"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAppSession } from "@/components/auth-provider";
import { requiresComplianceAcceptance } from "@/lib/compliance";

/**
 * Keeps the intake routes behind age and Terms acceptance.
 *
 * The backend already refuses to save an onboarding draft without them, so this
 * is not the control — it is what turns that refusal into a screen the athlete
 * can act on instead of an error banner. Mirrors RequirePrivateTrialAck, and
 * runs outside it so the Terms are settled before the trial briefing.
 */
export function RequireComplianceAcceptance({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const { isMeHydrated, me } = useAppSession();
  // An unhydrated `me` is "not known yet", not "not accepted" — redirecting on
  // it would bounce every athlete through the gate on every cold load.
  const mustAccept = isMeHydrated && requiresComplianceAcceptance(me);

  useEffect(() => {
    if (mustAccept) {
      router.replace("/consent");
    }
  }, [mustAccept, router]);

  return <>{children}</>;
}
