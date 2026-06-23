"use client";

import { useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { createGenerationJob, getActiveGenerationJob } from "@/lib/api";
import { COMPLETED_GENERATION_KEY, parseCompletedGeneration } from "@/lib/completed-generation";
import { useGenerationController } from "@/lib/generation-controller";
import { clearGenerationIntent, hasGenerationIntent } from "@/lib/generation-intent";
import {
  resolveGenerateAutoStartDecision,
  resolveMatchingPayloadGenerationAction,
} from "@/lib/generation-status-guards";
import { hydratePlanRequest } from "@/lib/onboarding";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { stableStringify } from "@/lib/stable-stringify";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

const STORAGE_KEY = "unlxck:pending-generation:self";
const ALLOWED_PLAN_SOURCES = new Set(["quick_build", "self_serve"]);

function resolvePlanSource(me: ReturnType<typeof useAppSession>["me"]): string {
  const draft = me?.profile.onboarding_draft as { plan_source?: unknown } | null | undefined;
  const candidate = typeof draft?.plan_source === "string" ? draft.plan_source.trim() : "";
  return ALLOWED_PLAN_SOURCES.has(candidate) ? candidate : "self_serve";
}

function getCompletedGeneration() {
  if (typeof window === "undefined") {
    return null;
  }
  return parseCompletedGeneration(window.localStorage.getItem(COMPLETED_GENERATION_KEY));
}

export default function GeneratePage() {
  const router = useRouter();
  const { me, session } = useAppSession();
  const autoStartRef = useRef(false);
  // Memoize so a re-render with the same session doesn't rebuild a fresh
  // payload object on every pass (which would churn the start effect below).
  const payload = useMemo(() => (me ? hydratePlanRequest(me) : null), [me]);
  // Canonical hash so re-ordered-but-identical payloads are treated as equal.
  const payloadHash = useMemo(() => stableStringify(payload), [payload]);
  const performanceFocusValidation = useMemo(
    () =>
      payload
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
        : null,
    [payload],
  );

  const controller = useGenerationController({
    token: session?.access_token ?? null,
    storageKey: STORAGE_KEY,
    createJob: async (clientRequestId) => {
      if (!session?.access_token || !payload) {
        throw new Error("We couldn't start generation. Please reload the page and try again.");
      }
      return createGenerationJob(session.access_token, payload, clientRequestId, resolvePlanSource(me));
    },
    recoverActiveJob: async () => {
      if (!session?.access_token) {
        return null;
      }
      return getActiveGenerationJob(session.access_token);
    },
    onComplete: ({ planId, status, recovered, requiresAdminResume, stage2Status }) => {
      const isProtectedTriageOutcome =
        requiresAdminResume === true || (stage2Status || "").toLowerCase() === "triage_blocked";
      if (payload && typeof window !== "undefined" && !isProtectedTriageOutcome && planId) {
        window.localStorage.setItem(
          COMPLETED_GENERATION_KEY,
          JSON.stringify({ payloadHash, planId, completedAt: new Date().toISOString() }),
        );
      }
      // Protected triage outcomes have no plan row. Stay on the generate
      // screen — the controller's `review_paused` phase renders the paused
      // card with admin-review copy and a stopped elapsed timer.
      if (!planId) {
        return;
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
      payloadHash,
      getCompletedGeneration(),
    );
    if (matchingPayloadAction.type === "redirect") {
      // A matching plan already exists — open it. Any stale intent is moot.
      clearGenerationIntent();
      router.replace(`/plans/${matchingPayloadAction.planId}`);
      return;
    }

    if ((!payload.fight_date && !payload.no_scheduled_fight) || !payload.athlete.technical_style.length) {
      clearGenerationIntent();
      router.replace("/onboarding");
      return;
    }
    if (performanceFocusValidation?.isOverCap) {
      clearGenerationIntent();
      router.replace("/onboarding?issue=focus-cap&step=performance");
      return;
    }

    autoStartRef.current = true;
    let cancelled = false;
    const activeToken = session.access_token;

    void (async () => {
      let activeJob: Awaited<ReturnType<typeof getActiveGenerationJob>> = null;
      try {
        activeJob = await getActiveGenerationJob(activeToken);
        if (cancelled) return;
      } catch {
        if (cancelled) return;
        // Active lookup unavailable; fall through to the intent-gated decision.
      }

      const decision = resolveGenerateAutoStartDecision({
        hasActiveJob: Boolean(activeJob),
        hasIntent: hasGenerationIntent(),
      });

      if (decision === "recover" && activeJob) {
        clearGenerationIntent();
        await controller.startGeneration({
          clientRequestId: activeJob.client_request_id,
          recovered: true,
          existingJob: activeJob,
        });
        return;
      }

      if (decision === "redirect") {
        // The page mounted without an explicit request to generate (e.g. a
        // reopened or reloaded tab) and there is nothing to reconnect to. Do
        // not silently start a new build — return the user to the workspace.
        router.replace("/");
        return;
      }

      clearGenerationIntent();
      await controller.startGeneration();
    })();

    return () => {
      cancelled = true;
    };
  }, [controller, payload, payloadHash, performanceFocusValidation?.isOverCap, router, session?.access_token]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen
        phase={controller.phase}
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
