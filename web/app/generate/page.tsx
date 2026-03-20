"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { ApiError, generatePlan, listPlans } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";
import type { PlanSummary } from "@/lib/types";

const PLAN_RECOVERY_WINDOW_MS = 5 * 60 * 1000;

function isTimeoutLike(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  const candidates = [error.message, error.cause instanceof Error ? error.cause.message : ""]
    .join(" ")
    .toLowerCase();

  return [
    "timeout",
    "timed out",
    "networkerror",
    "failed to fetch",
    "unable to reach the server",
    "router_external_target_error",
    "external target",
    "connection",
  ].some((token) => candidates.includes(token));
}

function isRecoverableGenerateError(error: unknown): boolean {
  return (error instanceof ApiError && error.status === 502) || isTimeoutLike(error);
}

function pickRecoveredPlan(plans: PlanSummary[]): PlanSummary | null {
  const now = Date.now();

  return (
    [...plans]
      .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
      .find((plan) => now - new Date(plan.created_at).getTime() <= PLAN_RECOVERY_WINDOW_MS) ?? null
  );
}

async function recoverRecentlyCreatedPlan(token: string): Promise<PlanSummary | null> {
  const plans = await listPlans(token);
  return pickRecoveredPlan(plans);
}

export default function GeneratePage() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

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
    setStatusMessage(null);

    void (async () => {
      try {
        const plan = await generatePlan(session.access_token, payload);
        console.info("[generate-page] generation:success", {
          planId: plan.plan_id,
          status: plan.status,
          stage2Status: plan.admin_outputs?.stage2_status ?? null,
        });
        await refreshMe();
        console.info("[generate-page] refreshMe:success redirecting_to_plan", {
          planId: plan.plan_id,
        });
        router.replace(`/plans/${plan.plan_id}`);
      } catch (generationError) {
        console.error("[generate-page] generation:failed", {
          error:
            generationError instanceof Error
              ? {
                  name: generationError.name,
                  message: generationError.message,
                  stack: generationError.stack,
                  cause:
                    generationError.cause instanceof Error
                      ? {
                          name: generationError.cause.name,
                          message: generationError.cause.message,
                        }
                      : generationError.cause,
                }
              : generationError,
        });

        const rawMessage =
          generationError instanceof Error ? generationError.message : "Unable to generate your plan.";

        const requestIdMatch = rawMessage.match(/request id: ([a-zA-Z0-9_-]+)/i);
        if (requestIdMatch) {
          console.error("[generate-page] generation:request_id", {
            requestId: requestIdMatch[1],
          });
        }

        if (isRecoverableGenerateError(generationError)) {
          try {
            setStatusMessage("Generation is still syncing after a gateway timeout. Checking for your saved plan now.");
            const recoveredPlan = await recoverRecentlyCreatedPlan(session.access_token);
            if (recoveredPlan) {
              console.info("[generate-page] generation:recovered", {
                planId: recoveredPlan.plan_id,
                status: recoveredPlan.status,
                createdAt: recoveredPlan.created_at,
              });
              await refreshMe();
              router.replace(`/plans/${recoveredPlan.plan_id}?recovered=1`);
              return;
            }
          } catch (recoveryError) {
            console.error("[generate-page] recovery:failed", {
              error:
                recoveryError instanceof Error
                  ? {
                      name: recoveryError.name,
                      message: recoveryError.message,
                      stack: recoveryError.stack,
                    }
                  : recoveryError,
            });
          }
        }

        setStatusMessage(null);
        setError("Generation request failed before a saved plan could be confirmed.");
      }
    })();
  }, [me, refreshMe, router, session?.access_token, started]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen error={error} statusMessage={statusMessage} />
    </RequireAuth>
  );
}
