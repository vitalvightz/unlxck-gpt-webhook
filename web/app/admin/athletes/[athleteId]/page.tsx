"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

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
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="kicker">Athlete Profile</p>
              <h1>{athlete.full_name || athlete.email}</h1>
              <p className="muted">{athlete.email}</p>
            </div>
            <div className="status-card">
              <p className="status-label">Plans</p>
              <h2 className="plan-summary-title">{athlete.plan_count}</h2>
              <p className="muted">Total saved plans for this athlete.</p>
            </div>
          </div>

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
          </div>

          <div className="plan-detail-layout">
            <aside className="plan-summary-stack">
              <section className="plan-summary-card">
                <div className="plan-summary-header">
                  <p className="kicker">Account</p>
                  <h2 className="plan-summary-title">Details</h2>
                </div>
                <div className="plan-meta-grid">
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Role</p>
                    <p className="plan-meta-value">{athlete.role}</p>
                  </article>
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Timezone</p>
                    <p className="plan-meta-value">{athlete.athlete_timezone || "Not set"}</p>
                  </article>
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Member since</p>
                    <p className="plan-meta-value">{new Date(athlete.created_at).toLocaleDateString()}</p>
                  </article>
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Last updated</p>
                    <p className="plan-meta-value">{new Date(athlete.updated_at).toLocaleDateString()}</p>
                  </article>
                  {athlete.latest_plan_created_at ? (
                    <article className="plan-meta-item">
                      <p className="plan-meta-label">Latest plan</p>
                      <p className="plan-meta-value">{new Date(athlete.latest_plan_created_at).toLocaleDateString()}</p>
                    </article>
                  ) : null}
                </div>
              </section>
            </aside>

            <section className="plan-text-panel">
              <div className="plan-summary-card">
                <div className="plan-summary-header">
                  <p className="kicker">Fighter profile</p>
                  <h2 className="plan-summary-title">Combat background</h2>
                </div>
                <div className="plan-meta-grid">
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Technical style</p>
                    <p className="plan-meta-value">{athlete.technical_style.length ? athlete.technical_style.join(", ") : "Not set"}</p>
                  </article>
                </div>
              </div>
            </section>
          </div>
        </section>
      )}
    </RequireAuth>
  );
}
