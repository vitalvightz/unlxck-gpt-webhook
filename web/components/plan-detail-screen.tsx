"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanViewer } from "@/components/plan-viewer";
import { ApiError, getActivePlan, getPlan } from "@/lib/api";
import type { PlanDetail } from "@/lib/types";

// Right after generation completes the app redirects straight to
// `/plans/{planId}`, but the saved plan row can briefly lag behind the
// completion event (read-after-write replication). That window surfaces as a
// transient 404 — the plan is genuinely there a moment later (it shows up in
// plan history). `getPlan`'s transient retries deliberately ignore 404s, so we
// re-attempt the initial load here before surfacing the alarming "could not
// restore" card.
const PLAN_LOAD_MAX_ATTEMPTS = 5;
const PLAN_LOAD_RETRY_DELAY_MS = 1500;

/**
 * Whether a failed plan load should be retried instead of surfaced. Only the
 * read-after-write 404 window is retried; genuine errors (403, malformed
 * responses, exhausted gateway/network retries) are shown immediately.
 */
export function shouldRetryPlanLoad(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

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
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [activePlanError, setActivePlanError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    setError(null);
    setActivePlanId(null);
    setActivePlanError(null);

    let cancelled = false;
    const token = session.access_token;

    const loadPlan = async () => {
      for (let attempt = 1; attempt <= PLAN_LOAD_MAX_ATTEMPTS; attempt += 1) {
        try {
          const loaded = await getPlan(token, planId);
          let resolvedActivePlanId: string | null = null;
          try {
            const activePlan = await getActivePlan(token);
            resolvedActivePlanId = activePlan.plan_id;
          } catch (activeError) {
            if (!cancelled && !(activeError instanceof ApiError && activeError.status === 404)) {
              setActivePlanError("Unable to confirm which saved plan is active.");
            }
          }
          if (!cancelled) {
            setPlan(loaded);
            setActivePlanId(resolvedActivePlanId);
          }
          return;
        } catch (planError) {
          if (cancelled) {
            return;
          }
          if (attempt === PLAN_LOAD_MAX_ATTEMPTS || !shouldRetryPlanLoad(planError)) {
            setError(planError instanceof Error ? planError.message : "Unable to load plan.");
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, PLAN_LOAD_RETRY_DELAY_MS));
        }
      }
    };

    void loadPlan();

    return () => {
      cancelled = true;
    };
  }, [planId, session?.access_token]);

  const recovered = searchParams.get("recovered") === "1";
  const protectedTriage = searchParams.get("protected_triage") === "1";
  const stage2Status = (searchParams.get("stage2_status") || "").trim().toLowerCase();
  const showResumeFailureHint = stage2Status === "triage_resume_approved";
  const resolvedPlanId = plan?.plan_id || planId;
  const isAdminViewer = me?.profile.role === "admin";

  return (
    <RequireAuth>
      {recovered ? (
        <section className="panel loading-card loading-shell loading-phase-finalizing athlete-motion-slot athlete-motion-status">
          <article className="status-card loading-context-panel loading-context-panel-compact">
            <p className="loading-eyebrow">Plan synced</p>
            <div className="loading-status-strip">
              Plan was restored after a timeout and synced back into your workspace.
            </div>
          </article>
        </section>
      ) : null}

      {protectedTriage ? (
        <section className="panel loading-card loading-shell loading-phase-finalizing athlete-motion-slot athlete-motion-status">
          <article className="status-card loading-context-panel loading-context-panel-compact">
            <p className="loading-eyebrow">Protected triage plan restored</p>
            <div className="loading-status-strip">
              {isAdminViewer
                ? "Use Admin Review → Resume Generation."
                : "This plan is protected and still requires review before release."}
              {isAdminViewer && showResumeFailureHint
                ? " Previous resume failed or did not complete. Submit a new resume request."
                : ""}
            </div>

            {isAdminViewer && resolvedPlanId ? (
              <a className="button button-secondary" href={`#admin-review-${resolvedPlanId}`}>
                Open Admin Review
              </a>
            ) : null}
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
          activePlanId={activePlanId}
          activePlanError={activePlanError}
          onActivePlanChanged={setActivePlanId}
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
