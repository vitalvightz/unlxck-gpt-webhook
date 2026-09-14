"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanViewer } from "@/components/plan-viewer";
import { ApiError, getPlan } from "@/lib/api";
import type { PlanDetail } from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";


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
    const appText = useAppTranslations("AppText");
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
              <p className="loading-eyebrow">{appText("text_3d999d388e9b")}</p>
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
    const appText = useAppTranslations("AppText");
  const { me, session, refreshMe } = useAppSession();
  const searchParams = useSearchParams();

  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }

    setError(null);

    let cancelled = false;
    const token = session.access_token;

    const loadPlan = async () => {
      for (let attempt = 1; attempt <= PLAN_LOAD_MAX_ATTEMPTS; attempt += 1) {
        try {
          const loaded = await getPlan(token, planId);
          if (!cancelled) {
            setPlan(loaded);
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
            <p className="loading-eyebrow">{appText("text_a7070b5dac29")}</p>
            <div className="loading-status-strip">
              {appText("text_c8ed85c0c102")}</div>
          </article>
        </section>
      ) : null}

      {protectedTriage ? (
        <section className="panel loading-card loading-shell loading-phase-finalizing athlete-motion-slot athlete-motion-status">
          <article className="status-card loading-context-panel loading-context-panel-compact">
            <p className="loading-eyebrow">{appText("text_f57b6f4ebfb6")}</p>
            <div className="loading-status-strip">
              {isAdminViewer
                ? appText("text_cc3313a53e21")
                : appText("text_e59b1291f675")}
              {isAdminViewer && showResumeFailureHint
                ? appText("text_d8d211bc96b4")
                : ""}
            </div>

            {isAdminViewer && resolvedPlanId ? (
              <a className="button button-secondary" href={`#admin-review-${resolvedPlanId}`}>
                {appText("text_2d2985d13079")}</a>
            ) : null}
          </article>
        </section>
      ) : null}

      {error ? (
        <PlanDetailStateCard
          phase="failed"
          eyebrow={appText("text_32ff80227550")}
          title={appText("text_e0f9a30ff968")}
          copy={appText("text_e4881350c774")}
          railTitle={appText("text_bf8076e9df1d")}
          railCopy={appText("text_b44d07570988")}
          error={error}
        />
      ) : plan ? (
        <PlanViewer
          plan={plan}
          accessToken={session?.access_token ?? null}
          viewerRole={me?.profile.role ?? "athlete"}
          viewerProfileId={me?.profile.athlete_id ?? null}
          onPlanUpdated={setPlan}
          onPlanDeleted={refreshMe}
        />
      ) : (
        <PlanDetailStateCard
          phase="finalizing"
          eyebrow={appText("text_32ff80227550")}
          title={appText("text_dad2d711221d")}
          copy={appText("text_2fd5ed9e4bbe")}
          railTitle={appText("text_5fb3b2eaedcc")}
          railCopy={appText("text_22a692ac0006")}
          statusMessage={appText("text_28221e00d198")}
        />
      )}
    </RequireAuth>
  );
}
