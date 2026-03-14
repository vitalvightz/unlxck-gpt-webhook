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
              <p className="muted">We are turning your saved onboarding into a fight camp plan right now.</p>
              {error ? <div className="error-banner">{error}</div> : <div className="success-banner">This can take a few seconds.</div>}
            </article>
          </div>
          <aside className="step-aside">
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Current action</p>
                <h2 className="form-section-title">Generation flow</h2>
              </div>
              <ul className="summary-list">
                <li>Load the latest saved onboarding draft.</li>
                <li>Generate a fight camp through the current Python planner.</li>
                <li>Save the result and open the plan detail screen automatically.</li>
              </ul>
            </div>
          </aside>
        </div>
      </section>
    </RequireAuth>
  );
}
