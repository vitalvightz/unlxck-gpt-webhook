"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteProfileHero,
  AthleteProfileOverviewCard,
} from "@/components/admin-athlete-profile";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { generateAdminAthletePlanFromLatestIntake, getAdminAthlete } from "@/lib/api";
import { useGenerationController } from "@/lib/generation-controller";
import type { AdminAthleteRecord } from "@/lib/types";

export default function AdminAthletePage() {
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  const controller = useGenerationController({
    token: session?.access_token ?? null,
    storageKey: athleteId ? `unlxck:pending-generation:admin:${athleteId}` : null,
    createJob: async (clientRequestId) => {
      if (!session?.access_token || !athleteId) {
        throw new Error("Session or athlete context is missing.");
      }
      return generateAdminAthletePlanFromLatestIntake(session.access_token, athleteId, clientRequestId);
    },
    onComplete: ({ planId, status, recovered }) => {
      const search = new URLSearchParams();
      if (status === "review_required") {
        search.set("review_required", "1");
      }
      if (recovered) {
        search.set("recovered", "1");
      }
      window.location.replace(`/plans/${planId}${search.toString() ? `?${search.toString()}` : ""}`);
    },
  });

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

  useEffect(() => {
    if (controller.error) {
      setError(controller.error);
    }
  }, [controller.error]);

  async function handleGenerateNewPlan() {
    if (!athlete?.latest_intake || !athleteId || controller.isGenerating) {
      return;
    }
    setError(null);
    await controller.startGeneration();
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
              className="cta"
              onClick={handleGenerateNewPlan}
              disabled={!athlete.latest_intake || controller.isGenerating}
            >
              {controller.isGenerating ? "Generating..." : "Generate new plan"}
            </button>
          </div>
          {controller.statusMessage ? <p className="muted">{controller.statusMessage}</p> : null}
          {!athlete.latest_intake ? (
            <p className="muted">Generate is available after this athlete has at least one saved intake.</p>
          ) : null}

          <AthleteProfileOverviewCard athlete={athlete} />
        </section>
      )}
    </RequireAuth>
  );
}
