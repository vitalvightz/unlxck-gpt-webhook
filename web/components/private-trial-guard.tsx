"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAppSession } from "@/components/auth-provider";
import { requiresPrivateTrialAcknowledgement } from "@/lib/private-trial";

/**
 * Keeps the intake routes behind the trial briefing.
 *
 * The landing resolver already sends a fresh sign-up to `/private-trial`, but
 * onboarding is also reachable by direct URL, by a bookmark, and by the Quick
 * Build link. Without this, "acknowledge before continuing" would hold only for
 * testers who happened to arrive the expected way.
 *
 * Children render throughout: this redirects rather than blanking the page, so
 * a tester who has acknowledged sees no flash of a gate they already passed.
 */
export function RequirePrivateTrialAck({ children }: Readonly<{ children: React.ReactNode }>) {
  const router = useRouter();
  const { isMeHydrated, me } = useAppSession();
  // Wait for the profile before judging: an unhydrated `me` is "not known yet",
  // not "not acknowledged", and redirecting on it would bounce every athlete
  // through the gate on every cold load.
  const mustAcknowledge = isMeHydrated && requiresPrivateTrialAcknowledgement(me);

  useEffect(() => {
    if (mustAcknowledge) {
      router.replace("/private-trial");
    }
  }, [mustAcknowledge, router]);

  return <>{children}</>;
}
