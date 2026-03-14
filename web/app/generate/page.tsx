"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { generatePlan } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";

export default function GeneratePage() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (!session?.access_token || !me || started) {
      return;
    }
    const payload = hydratePlanRequest(me);
    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      router.replace("/onboarding");
      return;
    }

    setStarted(true);
    generatePlan(session.access_token, payload)
      .then(async (plan) => {
        await refreshMe();
        router.replace(`/plans/${plan.plan_id}`);
      })
      .catch((generationError) => {
        setError(generationError instanceof Error ? generationError.message : "Unable to generate your plan.");
      });
  }, [me, refreshMe, router, session?.access_token, started]);

  return (
    <RequireAuth>
      <section className="panel">
        <div className="split-layout">
          <div className="step-main">
            <article className="status-card">
              <p className="status-label">Generating</p>
              <h1>Building your plan</h1>
              <p className="muted">Running Stage 1 generation, Stage 2 finalization, and validation from your saved onboarding.</p>
              {error ? <div className="error-banner">{error}</div> : <div className="success-banner">This can take a little longer while the final validation pass runs.</div>}
            </article>
          </div>
          <aside className="step-aside">
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Current action</p>
                <h2 className="form-section-title">Generation flow</h2>
              </div>
              <ul className="summary-list">
                <li>Load the latest saved onboarding.</li>
                <li>Run the draft planner and Stage 2 automation.</li>
                <li>Save the validated plan and open plan detail.</li>
              </ul>
            </div>
          </aside>
        </div>
      </section>
    </RequireAuth>
  );
}





