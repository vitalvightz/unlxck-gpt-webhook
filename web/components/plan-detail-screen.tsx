"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanViewer } from "@/components/plan-viewer";
import { getPlan } from "@/lib/api";
import type { PlanDetail } from "@/lib/types";

type PlanDetailStateCardProps = {
  phase: "finalizing" | "failed";
  eyebrow: string;
  title: string;
  copy: string;
  railTitle: string;
  railCopy: string;
  statusMessage?: string;
  error?: string | null;
};

function PlanDetailStateCard({
  phase,
  eyebrow,
  title,
  copy,
  railTitle,
  railCopy,
  statusMessage,
  error = null,
}: PlanDetailStateCardProps) {
  return (
    <section className={`panel loading-shell loading-phase-${phase}`}>
      <div className="split-layout">
        <div className="step-main athlete-motion-slot athlete-motion-main">
          <article className="status-card loading-primary-panel loading-context-panel">
            <p className="loading-eyebrow">{eyebrow}</p>
            <h1 className="loading-title">{title}</h1>
            <p className="muted loading-copy">{copy}</p>
            {phase !== "failed" ? (
              <div className="loading-scan-rail" aria-hidden="true">
                <span className="loading-scan-line" />
              </div>
            ) : null}
            {error ? (
              <div className="error-banner">{error}</div>
            ) : (
              <div className="loading-status-strip">{statusMessage}</div>
            )}
          </article>
        </div>
        <aside className="step-aside athlete-motion-slot athlete-motion-rail">
          <div className="support-panel loading-secondary-panel">
            <div className="form-section-header">
              <p className="loading-eyebrow">Workspace state</p>
              <h2 className="form-section-title">{railTitle}</h2>
            </div>
            <p className="muted">{railCopy}</p>
          </div>
        </aside>
      </div>
    </section>
  );
}

export function PlanDetailScreen({ planId }: { planId: string }) {
  const { me, session, refreshMe } = useAppSession();
  const searchParams = useSearchParams();
  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    setError(null);

    getPlan(session.access_token, planId)
      .then(setPlan)
      .catch((planError) => {
        setError(planError instanceof Error ? planError.message : "Unable to load plan.");
      });
  }, [planId, session?.access_token]);

  const recovered = searchParams.get("recovered") === "1";

  return (
    <RequireAuth>
      {recovered ? (
        <section className="panel loading-card loading-shell loading-phase-finalizing athlete-motion-slot athlete-motion-status">
          <article className="status-card loading-context-panel loading-context-panel-compact">
            <p className="loading-eyebrow">Plan synced</p>
            <div className="loading-status-strip">Plan was restored after a timeout and synced back into your workspace.</div>
          </article>
        </section>
      ) : null}
      {error ? (
        <PlanDetailStateCard
          phase="failed"
          eyebrow="Plan detail"
          title="We could not restore this saved plan."
          copy="The workspace could not pull the requested plan state. Review the error below, then retry from history."
          railTitle="Recovery route"
          railCopy="The saved plan itself is not deleted by this error. Returning to plan history and reopening the plan is safe."
          error={error}
        />
      ) : plan ? (
        <PlanViewer
          plan={plan}
          accessToken={session?.access_token ?? null}
          viewerRole={me?.profile.role ?? "athlete"}
          onPlanUpdated={setPlan}
          onPlanDeleted={refreshMe}
        />
      ) : (
        <PlanDetailStateCard
          phase="finalizing"
          eyebrow="Plan detail"
          title="Restoring saved plan."
          copy="We are rebuilding the saved output and athlete-safe view now."
          railTitle="Current action"
          railCopy="Pulling the latest saved version from your workspace before the plan viewer opens."
          statusMessage="Restoring the latest saved plan output now."
        />
      )}
    </RequireAuth>
  );
}
