"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PlanSwitchDialog } from "@/components/plan-switch-dialog";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import {
  AthleteProfileRow,
  canSetActive,
  CurrentCampCard,
  getIntakeSource,
  PlanManageSheet,
  PlanRow,
} from "@/components/plans/plan-dashboard";
import styles from "@/components/plans/plans.module.css";
import { PlanHistoryRowSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { ApiError, getActivePlan, getToday, listPlans, setActivePlan } from "@/lib/api";
import { getOptionLabels, TACTICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { requestXpRefresh } from "@/lib/xp-events";
import { formatPlanStatus, getPlanDisplayName } from "@/lib/plan-format";
import {
  type ActivePlanOverlapAction,
  isActivePlanOverlapError,
  isArchivedPlan,
} from "@/lib/plan-active";
import { getPlanReviewReason, isHeldForAdminReviewPlan } from "@/lib/plan-review";
import type { PlanSummary } from "@/lib/types";

function getArchivedPlans(plans: PlanSummary[]): PlanSummary[] {
  return plans.filter((plan) => isArchivedPlan(plan.status));
}

function HeldPlansReviewNotice({ plans }: { plans: PlanSummary[] }) {
  const visibleHeldPlans = plans.slice(0, 3);
  const remainingCount = Math.max(0, plans.length - visibleHeldPlans.length);

  return (
    <article className="list-card plans-dashboard-card athlete-motion-slot athlete-motion-status">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">Admin review hold</p>
          <h2>{plans.length === 1 ? "A plan is held for review" : `${plans.length} plans are held for review`}</h2>
          <p className="muted">
            These plans are saved, but they are not released to Overview or Today until admin approval clears the hold.
          </p>
        </div>
        <span className="badge">HELD</span>
      </div>

      <div className="plan-history-list plans-history-list">
        {visibleHeldPlans.map((plan) => (
          <div key={plan.plan_id} className="plan-history-row">
            <div className="plan-history-copy">
              <p className="label">{formatPlanStatus(plan.status)}</p>
              <Link href={`/plans/${plan.plan_id}`}>
                <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
              </Link>
              <p className="muted">{getPlanReviewReason(plan)}</p>
            </div>
            <div className="plan-history-meta">
              <Link href={`/plans/${plan.plan_id}?review_required=1`} className="ghost-button">
                Review hold
              </Link>
            </div>
          </div>
        ))}
      </div>

      {remainingCount > 0 ? (
        <p className="muted">
          {remainingCount} more held plan{remainingCount === 1 ? "" : "s"} shown in saved plan history.
        </p>
      ) : null}
    </article>
  );
}

function PlansSyncState() {
  return (
    <article className="list-card plans-sync-card" aria-busy="true">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">Plan sync</p>
          <h2>Loading saved fight camps</h2>
          <p className="muted">
            One moment.
          </p>
        </div>
        <span className="badge status-badge-neutral">Syncing</span>
      </div>
      <div className="plans-sync-grid" aria-hidden="true">
        <div className="plans-sync-line plans-sync-line-short" />
        <div className="plans-sync-line" />
        <div className="plans-sync-line plans-sync-line-mid" />
      </div>
    </article>
  );
}

export default function PlansPage() {
  const t = useTranslations("Workspace");
  const router = useRouter();
  const { showToast } = useToast();
  const { isMeHydrated, me, session } = useAppSession();
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localPlans, setLocalPlans] = useState<PlanSummary[] | null>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [isSettingActivePlanId, setIsSettingActivePlanId] = useState<string | null>(null);
  const [overlapConflictPlan, setOverlapConflictPlan] = useState<PlanSummary | null>(null);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  // The plan whose Manage sheet is open, if any.
  const [managedPlanId, setManagedPlanId] = useState<string | null>(null);
  // The active camp's phase, from the Today command; extra, so never awaited.
  const [activePhase, setActivePhase] = useState<{ planId: string; phase: string } | null>(null);
  const latestTokenRef = useRef(session?.access_token);

  useEffect(() => {
    latestTokenRef.current = session?.access_token;
  }, [session?.access_token]);

  const visiblePlans = useMemo(() => {
    const sourcePlans = localPlans ?? plans;
    return [...sourcePlans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  }, [localPlans, plans]);
  const explicitActivePlan = activePlanId ? visiblePlans.find((plan) => plan.plan_id === activePlanId) ?? null : null;
  const activePlan = explicitActivePlan && canSetActive(explicitActivePlan) ? explicitActivePlan : null;
  const intakeSource = getIntakeSource(me);
  const heldForReviewPlans = visiblePlans.filter(isHeldForAdminReviewPlan);
  const archivedPlans = getArchivedPlans(visiblePlans);
  const otherSavedPlans = visiblePlans.filter((plan) => plan.plan_id !== activePlan?.plan_id && !isArchivedPlan(plan.status));
  const hasPlans = visiblePlans.length > 0;
  const managedPlan = managedPlanId ? visiblePlans.find((plan) => plan.plan_id === managedPlanId) ?? null : null;
  const tacticalStyle = getOptionLabels(TACTICAL_STYLE_OPTIONS, me?.profile?.tactical_style ?? [])[0] ?? null;
  const phase = activePlan && activePhase?.planId === activePlan.plan_id ? activePhase.phase : null;

  const loadPlans = useCallback(async () => {
    const token = session?.access_token;
    if (!token) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextPlans, active] = await Promise.all([
        listPlans(token),
        getActivePlan(token).catch((activeError) => {
          if (activeError instanceof ApiError && activeError.status === 404) {
            return null;
          }
          throw activeError;
        }),
      ]);
      // Ignore results from a request that the current session has moved past.
      if (latestTokenRef.current !== token) {
        return;
      }
      setPlans(nextPlans);
      setActivePlanId(active?.plan_id ?? null);
    } catch (plansError) {
      if (latestTokenRef.current !== token) {
        return;
      }
      const message = plansError instanceof Error ? plansError.message : "";
      setError(message.includes("401") || message.toLowerCase().includes("session")
        ? "Session expired. Sign in again."
        : "Connection issue. Try again in a minute.");
    } finally {
      if (latestTokenRef.current === token) {
        setIsLoading(false);
      }
    }
  }, [session?.access_token]);

  useEffect(() => {
    void loadPlans();
  }, [loadPlans]);

  useEffect(() => {
    if (!archivedPlans.length) {
      setIsArchiveOpen(false);
    }
  }, [archivedPlans.length]);

  useEffect(() => {
    const token = session?.access_token;
    if (!token) return;
    let cancelled = false;
    getToday(token)
      .then((command) => {
        const planId = command.active_plan?.id;
        const rawPhase = command.active_plan?.phase;
        if (!cancelled && planId && rawPhase) {
          setActivePhase({ planId, phase: humanizeIfRawEnum(rawPhase) });
        }
      })
      // The phase is a nicety: without it the card simply leaves it out.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session?.access_token]);

  function handlePlanDeleted(planId: string) {
    setLocalPlans((current) => {
      const source = current ?? plans;
      return source.filter((currentPlan) => currentPlan.plan_id !== planId);
    });
    router.refresh();
  }

  function handlePlanRenamed(updatedPlan: PlanSummary) {
    setLocalPlans((current) => {
      const source = current ?? plans;
      return source.map((currentPlan) => (currentPlan.plan_id === updatedPlan.plan_id ? { ...currentPlan, ...updatedPlan } : currentPlan));
    });
    router.refresh();
  }

  async function activatePlan(plan: PlanSummary, overlapAction?: ActivePlanOverlapAction): Promise<void> {
    const token = session?.access_token;
    if (!token || !canSetActive(plan)) {
      return;
    }
    setIsSettingActivePlanId(plan.plan_id);
    try {
      const active = await setActivePlan(token, plan.plan_id, { overlapAction });
      setActivePlanId(active.plan_id);
      setOverlapConflictPlan(null);
      showToast("Active plan updated.", { tone: "success" });
      await loadPlans();
      requestXpRefresh();
      router.refresh();
    } catch (activeError) {
      if (!overlapAction && isActivePlanOverlapError(activeError)) {
        setOverlapConflictPlan(plan);
        return;
      }
      const message = activeError instanceof Error ? activeError.message : "Unable to set active plan.";
      showToast(message, { tone: "error" });
    } finally {
      setIsSettingActivePlanId(null);
    }
  }

  async function handleSetActive(plan: PlanSummary): Promise<void> {
    await activatePlan(plan);
  }

  async function handleOverlapConfirm(action: ActivePlanOverlapAction): Promise<void> {
    if (!overlapConflictPlan) {
      return;
    }
    await activatePlan(overlapConflictPlan, action);
  }

  const isPlanListLoading = isLoading;
  const isProfileLoading = !isMeHydrated;

  return (
    <RequireAuth>
      <section className={`panel ${styles.page}`}>
        <h1 className={`athlete-motion-slot athlete-motion-header ${styles.pageTitle}`}>{t("planWorkspace")}</h1>

        {error ? (
          <div className="error-banner athlete-motion-slot athlete-motion-status" role="alert">
            <span>{error}</span>
            {error.includes("Session expired") ? null : (
              <button
                type="button"
                className="error-banner-retry"
                onClick={() => void loadPlans()}
                disabled={isLoading}
              >
                {isLoading ? t("retrying") : t("retry")}
              </button>
            )}
          </div>
        ) : null}

        {!isLoading && heldForReviewPlans.length > 0 ? (
          <HeldPlansReviewNotice plans={heldForReviewPlans} />
        ) : null}

        <div className="athlete-motion-slot athlete-motion-main">
          {isPlanListLoading ? (
            <PlansSyncState />
          ) : (
            <CurrentCampCard
              plan={activePlan}
              intake={intakeSource}
              tacticalStyle={tacticalStyle}
              phase={phase}
              onManage={() => setManagedPlanId(activePlan?.plan_id ?? null)}
            />
          )}
        </div>

        {isLoading ? (
          <div className={`athlete-motion-slot athlete-motion-main ${styles.section}`} aria-busy="true">
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>{t("previousPlans")}</h2>
              <span className={styles.sectionMeta}>{t("loading")}</span>
            </div>
            <div className="plan-history-list plans-history-list">
              <PlanHistoryRowSkeleton />
              <PlanHistoryRowSkeleton />
            </div>
          </div>
        ) : null}

        {!isLoading && hasPlans ? (
          <div className={`athlete-motion-slot athlete-motion-main ${styles.section}`}>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>{t("previousPlans")}</h2>
              {otherSavedPlans.length ? (
                <span className={styles.sectionMeta}>{t("savedCount", { count: otherSavedPlans.length })}</span>
              ) : null}
            </div>
            {otherSavedPlans.length > 0 ? (
              <ul className={styles.rows}>
                {otherSavedPlans.map((plan) => (
                  <PlanRow
                    key={plan.plan_id}
                    plan={plan}
                    activePlanId={activePlanId}
                    onOpen={() => setManagedPlanId(plan.plan_id)}
                  />
                ))}
              </ul>
            ) : (
              <p className="muted">No other saved plans.</p>
            )}

            {archivedPlans.length ? (
              <>
                <button
                  type="button"
                  className={styles.archiveToggle}
                  onClick={() => setIsArchiveOpen((current) => !current)}
                  aria-expanded={isArchiveOpen}
                  aria-controls="plans-archive"
                >
                  {t("archivedCount", { count: archivedPlans.length })}
                  <span className={styles.toggleChevron} aria-hidden="true" />
                </button>
                {isArchiveOpen ? (
                  <ul id="plans-archive" className={styles.rows} aria-label={t("olderPlans")}>
                    {archivedPlans.map((plan) => (
                      <PlanRow
                        key={plan.plan_id}
                        plan={plan}
                        activePlanId={activePlanId}
                        onOpen={() => setManagedPlanId(plan.plan_id)}
                      />
                    ))}
                  </ul>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}

        <div className={`athlete-motion-slot athlete-motion-main ${styles.section}`}>
          {isProfileLoading ? null : <AthleteProfileRow me={me} />}
        </div>

        {managedPlan ? (
          <PlanManageSheet
            key={managedPlan.plan_id}
            plan={managedPlan}
            activePlanId={activePlanId}
            accessToken={session?.access_token ?? null}
            isSettingActive={isSettingActivePlanId === managedPlan.plan_id}
            onSetActive={handleSetActive}
            onPlanRenamed={handlePlanRenamed}
            onPlanDeleted={handlePlanDeleted}
            onClose={() => setManagedPlanId(null)}
          />
        ) : null}

        {overlapConflictPlan ? (
          <PlanSwitchDialog
            plan={overlapConflictPlan}
            isPending={isSettingActivePlanId === overlapConflictPlan.plan_id}
            onConfirm={handleOverlapConfirm}
            onCancel={() => setOverlapConflictPlan(null)}
          />
        ) : null}
      </section>
    </RequireAuth>
  );
}
