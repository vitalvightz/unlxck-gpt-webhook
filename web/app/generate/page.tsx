"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { createGenerationJob } from "@/lib/api";
import { useGenerationController } from "@/lib/generation-controller";
import { hydratePlanRequest } from "@/lib/onboarding";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

const STORAGE_KEY = "unlxck:pending-generation:self";

export default function GeneratePage() {
  const router = useRouter();
  const { me, session } = useAppSession();
  const autoStartRef = useRef(false);
  const payload = me ? hydratePlanRequest(me) : null;
  const performanceFocusValidation = payload
    ? validatePerformanceFocusSelections(
      payload.fight_date,
      {
        keyGoals: payload.key_goals,
        weakAreas: payload.weak_areas,
      },
      {
        timeZone: payload.athlete.athlete_timezone,
      },
    )
    : null;

  const controller = useGenerationController({
    token: session?.access_token ?? null,
    storageKey: STORAGE_KEY,
    createJob: async (clientRequestId) => {
      if (!session?.access_token || !payload) {
        throw new Error("Session or intake payload is missing.");
      }
      return createGenerationJob(session.access_token, payload, clientRequestId);
    },
    onComplete: ({ planId, status, recovered }) => {
      const search = new URLSearchParams();
      if (status === "review_required") {
        search.set("review_required", "1");
      }
      if (recovered) {
        search.set("recovered", "1");
      }
      const nextPath = `/plans/${planId}${search.toString() ? `?${search.toString()}` : ""}`;
      window.location.replace(nextPath);
    },
  });

  useEffect(() => {
    if (!session?.access_token || !payload || autoStartRef.current || controller.hasPendingGeneration) {
      return;
    }

    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      router.replace("/onboarding");
      return;
    }
    if (performanceFocusValidation?.isOverCap) {
      router.replace("/onboarding?issue=focus-cap&step=performance");
      return;
    }

    autoStartRef.current = true;
    void controller.startGeneration();
  }, [controller, payload, performanceFocusValidation?.isOverCap, router, session?.access_token]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen
        phase={controller.phase}
        error={controller.error}
        statusMessage={controller.statusMessage}
      />
    </RequireAuth>
  );
}
