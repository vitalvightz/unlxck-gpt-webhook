"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteCoachNotesCard,
  AthleteLatestIntakeCard,
  AthleteProfileHero,
  AthleteScheduleCard,
  AthleteSnapshotCard,
} from "@/components/admin-athlete-profile";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { getAdminAthlete } from "@/lib/api";
import type { AdminAthleteRecord } from "@/lib/types";

export default function AdminAthletePage() {
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          </div>

          <div className="athlete-profile-grid">
            <AthleteSnapshotCard athlete={athlete} />
            <AthleteLatestIntakeCard intake={athlete.latest_intake ?? null} />
            {athlete.latest_intake ? <AthleteScheduleCard intake={athlete.latest_intake} /> : null}
            {athlete.latest_intake ? <AthleteCoachNotesCard intake={athlete.latest_intake} /> : null}
          </div>
        </section>
      )}
    </RequireAuth>
  );
}
