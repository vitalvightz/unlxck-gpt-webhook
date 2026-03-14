"use client";

import { useEffect, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanViewer } from "@/components/plan-viewer";
import { getPlan } from "@/lib/api";
import type { PlanDetail } from "@/lib/types";

export function PlanDetailScreen({ planId }: { planId: string }) {
  const { session } = useAppSession();
  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }
    getPlan(session.access_token, planId)
      .then(setPlan)
      .catch((planError) => {
        setError(planError instanceof Error ? planError.message : "Unable to load plan.");
      });
  }, [planId, session?.access_token]);

  return (
    <RequireAuth>
      {error ? (
        <section className="panel loading-card">
          <p className="kicker">Plan Detail</p>
          <div className="error-banner">{error}</div>
        </section>
      ) : null}
      {plan ? (
        <PlanViewer plan={plan} />
      ) : (
        <section className="panel loading-card">
          <p className="kicker">Plan Detail</p>
          <h1>Loading plan</h1>
          <p className="muted">Restoring the saved output and athlete-safe view now.</p>
        </section>
      )}
    </RequireAuth>
  );
}
