"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { listAdminAthletes, listAdminPlans } from "@/lib/api";
import type { AdminAthleteRecord, AdminPlanSummary } from "@/lib/types";

function getPlanDisplayName(plan: { plan_name?: string | null; full_name?: string | null; athlete_email: string }) {
  return plan.plan_name?.trim() || plan.full_name || plan.athlete_email;
}

export default function AdminPage() {
  const { session } = useAppSession();
  const [athletes, setAthletes] = useState<AdminAthleteRecord[]>([]);
  const [plans, setPlans] = useState<AdminPlanSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }
    Promise.all([listAdminAthletes(session.access_token), listAdminPlans(session.access_token)])
      .then(([nextAthletes, nextPlans]) => {
        setAthletes(nextAthletes);
        setPlans(nextPlans);
      })
      .catch((adminError) => {
        setError(adminError instanceof Error ? adminError.message : "Unable to load admin data.");
      });
  }, [session?.access_token]);

  return (
    <RequireAuth adminOnly>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Admin</p>
            <h1>Support dashboard</h1>
            <p className="muted">Theme parity only. This view stays lightweight and support-focused while the athlete experience remains primary.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Records</p>
            <h2 className="plan-summary-title">{athletes.length + plans.length}</h2>
            <p className="muted">Athlete accounts and saved plans visible in support mode.</p>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <div className="admin-grid">
          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Athletes</p>
              <h2>Recent accounts</h2>
            </div>
            <div className="plans-grid">
              {athletes.map((athlete) => (
                <article key={athlete.athlete_id} className="plan-card">
                  <div className="plan-card-header">
                    <div>
                      <h3 className="plan-card-title">{athlete.full_name || athlete.email}</h3>
                      <p className="muted">{athlete.email}</p>
                    </div>
                    <span className="badge">{athlete.plan_count} plans</span>
                  </div>
                  <p className="muted">Created {new Date(athlete.created_at).toLocaleString()}</p>
                </article>
              ))}
            </div>
          </article>

          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Plans</p>
              <h2>Latest generations</h2>
            </div>
            <div className="plans-grid">
              {plans.map((plan) => (
                <article key={plan.plan_id} className="plan-card">
                  <div className="plan-card-header">
                    <div>
                      <Link href={`/plans/${plan.plan_id}`}>
                        <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                      </Link>
                      <p className="muted">{plan.athlete_email}</p>
                    </div>
                    <span className="badge">{plan.status}</span>
                  </div>
                  <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
                </article>
              ))}
            </div>
          </article>
        </div>
      </section>
    </RequireAuth>
  );
}
