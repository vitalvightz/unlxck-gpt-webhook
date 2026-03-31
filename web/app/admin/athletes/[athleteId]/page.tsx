"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteCoachNotesCard,
  AthleteLatestIntakeCard,
  AthleteLatestIntakeStatus,
  AthleteProfileHero,
  AthleteScheduleCard,
  AthleteSnapshotCard,
} from "@/components/admin-athlete-profile";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { ApiError, generateAdminAthletePlanFromLatestIntake, getAdminAthlete, getGenerationJob } from "@/lib/api";
import type { AdminAthleteRecord } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

export default function AdminAthletePage() {
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationMessage, setGenerationMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token || !athleteId) {
      return;
    }

    getAdminAthlete(session.access_token, athleteId)
      .then(setAthlete)
      .catch((athleteError) => {
        setError(athleteError instanceof Error ? athleteError.message : "Unable to load athlete profile.");
      });
  }, [athleteId, session?.access_token]);

  async function handleGenerateNewPlan() {
    if (!session?.access_token || !athleteId || isGenerating) {
      return;
    }
    setIsGenerating(true);
    setError(null);
    setGenerationMessage("Submitting a new generation job using the athlete's latest saved intake.");
    try {
      const job = await generateAdminAthletePlanFromLatestIntake(session.access_token, athleteId);
      const startedAt = Date.now();

      while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
        const currentJob = await getGenerationJob(session.access_token, job.job_id);
        if (currentJob.status === "queued") {
          setGenerationMessage("Job queued. Stage 1 and Stage 2 will start shortly.");
        } else if (currentJob.status === "running") {
          setGenerationMessage("Generating plan now (Stage 1 + Stage 2).");
        } else if (currentJob.status === "failed") {
          throw new Error(currentJob.error || "Plan generation failed.");
        } else if (currentJob.status === "completed" || currentJob.status === "review_required") {
          const planId = currentJob.plan_id || currentJob.latest_plan_id;
          if (!planId) {
            throw new Error("Generation completed but no plan ID was returned.");
          }
          window.location.replace(`/plans/${planId}${currentJob.status === "review_required" ? "?review_required=1" : ""}`);
          return;
        }

        await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
      }
      throw new Error("Plan generation is taking longer than expected. Please try again in a moment.");
    } catch (generationError) {
      if (generationError instanceof ApiError || generationError instanceof Error) {
        setError(generationError.message);
      } else {
        setError("Unable to generate a new plan from the latest intake.");
      }
      setGenerationMessage(null);
      setIsGenerating(false);
    }
  }

  return (
    <RequireAuth adminOnly>
      {error ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <div className="error-banner">{error}</div>
          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
          </div>
        </section>
      ) : !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <h1>Loading profile</h1>
          <p className="muted">Fetching athlete record now.</p>
        </section>
      ) : (
        <section className="panel athlete-profile-panel">
          <AthleteProfileHero athlete={athlete} />

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
            <button
              type="button"
              className="primary-button"
              onClick={handleGenerateNewPlan}
              disabled={!athlete.latest_intake || isGenerating}
            >
              {isGenerating ? "Generating…" : "Generate new plan"}
            </button>
          </div>
          {generationMessage ? <p className="muted">{generationMessage}</p> : null}
          {!athlete.latest_intake ? (
            <p className="muted">Generate is available after this athlete has at least one saved intake.</p>
          ) : null}

          <div className="athlete-profile-grid">
            <AthleteSnapshotCard athlete={athlete} />
            <AthleteLatestIntakeCard intake={athlete.latest_intake ?? null} />
            {!athlete.latest_intake && athlete.plan_count > 0 ? (
              <AthleteLatestIntakeStatus
                planCount={athlete.plan_count}
                latestPlanCreatedAt={athlete.latest_plan_created_at ?? null}
              />
            ) : null}
            {athlete.latest_intake ? <AthleteScheduleCard intake={athlete.latest_intake} /> : null}
            {athlete.latest_intake ? <AthleteCoachNotesCard intake={athlete.latest_intake} /> : null}
          </div>
        </section>
      )}
    </RequireAuth>
  );
}
