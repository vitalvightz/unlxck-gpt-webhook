"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { createGenerationJob, getGenerationJob, ApiError } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

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

    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      console.warn("[generate-page] redirect:onboarding_incomplete_payload");
      router.replace("/onboarding");
      return;
    }

    setStarted(true);
    setError(null);
    setStatusMessage("Submitting your generation request and creating a background job.");

    void (async () => {
      try {
        const job = await createGenerationJob(session.access_token, payload);
        console.info("[generate-page] generation-job:created", job);
        setStatusMessage("Your job is queued. We’ll keep checking until the saved plan is ready.");

        const startedAt = Date.now();
        while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
          const currentJob = await getGenerationJob(session.access_token, job.job_id);
          console.info("[generate-page] generation-job:polled", currentJob);

          if (currentJob.status === "queued") {
            setStatusMessage("Your plan request is queued. Stage 1 and Stage 2 will start shortly.");
          } else if (currentJob.status === "running") {
            setStatusMessage("Stage 1 generation and Stage 2 finalization are running in the background.");
          } else if (currentJob.status === "failed") {
            throw new Error(currentJob.error || "Plan generation failed.");
          } else if (
            currentJob.status === "completed" ||
            currentJob.status === "review_required"
          ) {
            const planId = currentJob.plan_id || currentJob.latest_plan_id;
            if (!planId) {
              throw new Error("Generation finished, but no saved plan was returned.");
            }

            setStatusMessage("Your plan is ready. Opening the saved plan now.");
            void refreshMe().catch((refreshError) => {
              console.warn("[generate-page] refreshMe:failed_after_generation", refreshError);
            });
            const search = new URLSearchParams();
            if (currentJob.status === "review_required") {
              search.set("review_required", "1");
            }
            router.replace(`/plans/${encodeURIComponent(planId)}${search.toString() ? `?${search.toString()}` : ""}`);
            return;
          }

          await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
        }

        throw new Error("Plan generation is taking longer than expected. Please check back in a moment.");
      } catch (generationError) {
        console.error("[generate-page] generation:failed", generationError);
        if (generationError instanceof ApiError) {
          setError(generationError.message);
        } else if (generationError instanceof Error) {
          setError(generationError.message);
        } else {
          setError("Unable to generate your plan.");
        }
        setStatusMessage(null);
      }
    })();
  }, [me, refreshMe, router, session?.access_token, started]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen error={error} statusMessage={statusMessage} />
    </RequireAuth>
  );
}
