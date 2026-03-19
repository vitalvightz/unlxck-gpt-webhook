"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { generatePlan } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

export default function GeneratePage() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    console.info("[generate-page] effect:entered", {
      hasSessionToken: Boolean(session?.access_token),
      hasMe: Boolean(me),
      started,
    });

    if (!session?.access_token || !me || started) {
      return;
    }

    const payload = hydratePlanRequest(me);

    console.info("[generate-page] payload:hydrated", {
      hasFightDate: Boolean(payload.fight_date),
      technicalStyleCount: payload.athlete.technical_style.length,
      fullName: payload.athlete.full_name,
      weeklyTrainingFrequency: payload.weekly_training_frequency,
      trainingAvailabilityCount: payload.training_availability.length,
      hardSparringDaysCount: payload.hard_sparring_days.length,
      injuriesPresent: Boolean(payload.injuries),
    });

    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      console.warn("[generate-page] redirect:onboarding_incomplete_payload");
      router.replace("/onboarding");
      return;
    }

    console.info("[generate-page] generation:start");
    setStarted(true);

    generatePlan(session.access_token, payload)
      .then(async (plan) => {
        console.info("[generate-page] generation:success", {
          planId: plan.plan_id,
        });
        await refreshMe();
        console.info("[generate-page] refreshMe:success redirecting_to_plan", {
          planId: plan.plan_id,
        });
        router.replace(`/plans/${plan.plan_id}`);
      })
      .catch((generationError) => {
        const message =
          generationError instanceof Error ? generationError.message : "Unable to generate your plan.";

        console.error("[generate-page] generation:failed", {
          error:
            generationError instanceof Error
              ? {
                  name: generationError.name,
                  message: generationError.message,
                  stack: generationError.stack,
                }
              : generationError,
        });

        const requestIdMatch = message.match(/request id: ([a-zA-Z0-9_-]+)/i);
        if (requestIdMatch) {
          console.error("[generate-page] generation:request_id", {
            requestId: requestIdMatch[1],
          });
        }

        setError(message);
      });
  }, [me, refreshMe, router, session?.access_token, started]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen error={error} />
    </RequireAuth>
  );
}
