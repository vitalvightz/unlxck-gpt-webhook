"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { createGenerationJob, getActiveGenerationJob } from "@/lib/api";
import { useGenerationController } from "@/lib/generation-controller";
import { resolveMatchingPayloadGenerationAction } from "@/lib/generation-status-guards";
import { hydratePlanRequest } from "@/lib/onboarding";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

const STORAGE_KEY = "unlxck:pending-generation:self";
const COMPLETED_GENERATION_KEY = "unlxck:completed-generation:self";
const ALLOWED_PLAN_SOURCES = new Set(["quick_build", "self_serve"]);

function resolvePlanSource(me: ReturnType<typeof useAppSession>["me"]): string {
  const draft = me?.profile.onboarding_draft as { plan_source?: unknown } | null | undefined;
  const candidate = typeof draft?.plan_source === "string" ? draft.plan_source.trim() : "";
  return ALLOWED_PLAN_SOURCES.has(candidate) ? candidate : "self_serve";
}

function hashPayload(payload: unknown): string {
  return JSON.stringify(payload);
}

function getCompletedGeneration(): { planId: string | null; payloadHash: string | null } | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(COMPLETED_GENERATION_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as { payloadHash?: unknown; planId?: unknown };
    const planId = typeof parsed.planId === "string" && parsed.planId.trim() ? parsed.planId : null;
    const payloadHash = typeof parsed.payloadHash === "string" ? parsed.payloadHash : null;
    if (!planId && !payloadHash) {
      return null;
    }
    return { planId, payloadHash };
  } catch {
    return null;
  }
}

export default function GeneratePage() {
  const router = useRouter();
  const { me, session } = useAppSession();
  const autoStartRef = useRef(false);
  const [forceAlreadyGenerated, setForceAlreadyGenerated] = useState(false);
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
      return createGenerationJob(session.access_token, payload, clientRequestId, resolvePlanSource(me));
    },
    onComplete: ({ planId, status, recovered, requiresAdminResume, stage2Status }) => {
      if (payload && typeof window !== "undefined") {
        window.localStorage.setItem(
          COMPLETED_GENERATION_KEY,
          JSON.stringify({ payloadHash: hashPayload(payload), planId, completedAt: new Date().toISOString() }),
        );
      }
      const search = new URLSearchParams();
      if (status === "review_required") {
        search.set("review_required", "1");
      }
      if (recovered) {
        search.set("recovered", "1");
      }
      if (requiresAdminResume) {
        search.set("protected_triage", "1");
        if (stage2Status) {
          search.set("stage2_status", stage2Status);
        }
      }
      const nextPath = `/plans/${planId}${search.toString() ? `?${search.toString()}` : ""}`;
      router.replace(nextPath);
    },
  });

  useEffect(() => {
    if (!session?.access_token || !payload || autoStartRef.current || controller.hasPendingGeneration) {
      return;
    }
    const matchingPayloadAction = resolveMatchingPayloadGenerationAction(
      hashPayload(payload),
      getCompletedGeneration(),
    );
    if (matchingPayloadAction.type === "redirect") {
      router.replace(`/plans/${matchingPayloadAction.planId}`);
      return;
    }
    if (matchingPayloadAction.type === "already_generated") {
      setForceAlreadyGenerated(true);
      return;
    }

    if ((!payload.fight_date && !payload.no_scheduled_fight) || !payload.athlete.technical_style.length) {
      router.replace("/onboarding");
      return;
    }
    if (performanceFocusValidation?.isOverCap) {
      router.replace("/onboarding?issue=focus-cap&step=performance");
      return;
    }

    autoStartRef.current = true;
    let cancelled = false;
    const activeToken = session.access_token;

    void (async () => {
      try {
        const activeJob = await getActiveGenerationJob(activeToken);
        if (cancelled) return;

        if (activeJob) {
          if (cancelled) return;
          await controller.startGeneration({
            clientRequestId: activeJob.client_request_id,
            recovered: true,
            existingJob: activeJob,
          });
          return;
        }
      } catch {
        if (cancelled) return;
        // Fall through to normal create flow if active lookup is unavailable.
      }

      if (cancelled) return;
      await controller.startGeneration();
    })();

    return () => {
      cancelled = true;
    };
  }, [controller, payload, performanceFocusValidation?.isOverCap, router, session?.access_token]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen
        phase={forceAlreadyGenerated ? "already_generated" : controller.phase}
        error={controller.error}
        statusMessage={controller.statusMessage}
        startedAtMs={controller.startedAtMs}
        milestones={controller.milestones}
        intake={payload}
        onRetry={() => {
          void controller.retryGeneration();
        }}
        canRetry={controller.canRetry}
        onOpenPlanHistory={() => router.push("/plans")}
        onReturnToWorkspace={() => router.push("/")}
        onRefreshStatus={() => router.refresh()}
        onRefineIntake={() => router.push("/onboarding")}
      />
    </RequireAuth>
  );
}
