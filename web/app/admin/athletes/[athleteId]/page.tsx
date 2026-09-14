"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteProfileHero,
  AthleteProfileOverviewCard,
} from "@/components/admin-athlete-profile";
import { translateUiText } from "@/i18n/ui-text";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import {
  approveAndResumeGenerationFromJob,
  bulkPermanentlyDeleteArchivedPlans,
  cancelAdminGenerationJob,
  getAdminAthleteGenerationJobs,
  generateAdminAthletePlanFromLatestIntake,
  getAdminAthlete,
  getAdminAthleteNutritionCurrent,
  listAdminPlans,
  retryGenerationJob,
  updateAdminAthleteNutritionCurrent,
  updateAdminAthleteLatestIntake,
} from "@/lib/api";
import { loadAdminAthleteProfileData } from "@/lib/admin-athlete-profile-loader";
import { formatAppDate, formatAppDateTime } from "@/lib/date-format";
import { useGenerationController } from "@/lib/generation-controller";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import {
  PROFILE_REFRESH_FAILED_BANNER_BODY,
  PROFILE_REFRESH_FAILED_BANNER_TITLE,
  hasProfileRefreshFailedWarning,
} from "@/lib/profile-refresh-warning";
import type {

  AdminAthleteRecord,
  AdminGenerationJobDiagnostic,
  AdminPlanSummary,
  NutritionWorkspaceState,
  NutritionWorkspaceUpdateRequest,
} from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";

function humanizeEnumValue(value: string | null | undefined, fallback: string): string {
  if (!value?.trim()) {
    return fallback;
  }
  return value
    .trim()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : formatAppDateTime(value);
}

function formatListOrDash(values: string[] | null | undefined): string {
  const joined = Array.isArray(values)
    ? values.filter((value) => value?.trim()).join(", ")
    : "";
  return joined || "-";
}

function getPlanDisplayName(plan: AdminPlanSummary): string {
  return plan.plan_name?.trim() || plan.full_name || plan.athlete_email || "Untitled plan";
}

function statusLabel(value: string | null | undefined): string {
  return value?.trim() ? humanizeEnumValue(value, value) : "-";
}

function toNutritionUpdateRequest(workspace: NutritionWorkspaceState): NutritionWorkspaceUpdateRequest {
  return {
    nutrition_profile: workspace.nutrition_profile,
    shared_camp_context: workspace.shared_camp_context,
    s_and_c_preferences: workspace.s_and_c_preferences,
    nutrition_readiness: workspace.nutrition_readiness,
    nutrition_monitoring: workspace.nutrition_monitoring,
    nutrition_coach_controls: workspace.nutrition_coach_controls,
  };
}

function isArchivedPlan(plan: AdminPlanSummary): boolean {
  return (plan.status || "").trim().toLowerCase() === "archived";
}

function AthletePlanAccessCard({
  plans,
  warning,
  accessToken,
  onPlansDeleted,
}: {
  plans: AdminPlanSummary[];
  warning: string | null;
  accessToken: string | null;
  onPlansDeleted: (deletedPlanIds: string[]) => void;
}) {
    const appText = useAppTranslations("AppText");
  const archivedIds = plans.filter(isArchivedPlan).map((plan) => plan.plan_id);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Ignore any selections whose plans have left the list (after deletes/reloads)
  // by deriving the effective set from the archived plans currently on screen.
  const archivedIdSet = new Set(archivedIds);
  const selectedArchivedIds = selectedIds.filter((id) => archivedIdSet.has(id));
  const selectedCount = selectedArchivedIds.length;
  const allArchivedSelected = archivedIds.length > 0 && selectedCount === archivedIds.length;

  function toggleSelected(planId: string) {
    setMessage(null);
    setError(null);
    setSelectedIds((current) =>
      current.includes(planId) ? current.filter((id) => id !== planId) : [...current, planId],
    );
  }

  function toggleSelectAll() {
    setMessage(null);
    setError(null);
    setSelectedIds(allArchivedSelected ? [] : [...archivedIds]);
  }

  async function handleBulkDelete() {
    if (!accessToken || selectedCount === 0 || isDeleting) {
      return;
    }
    const confirmed = window.confirm(
      `Permanently delete ${selectedCount} archived plan${selectedCount === 1 ? "" : "s"}? This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setIsDeleting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await bulkPermanentlyDeleteArchivedPlans(accessToken, selectedArchivedIds);
      onPlansDeleted(result.deleted);
      setSelectedIds((current) => current.filter((id) => !result.deleted.includes(id)));
      setMessage(
        `Deleted ${result.deleted_count} plan${result.deleted_count === 1 ? "" : "s"}.` +
          (result.skipped_count ? ` ${result.skipped_count} skipped.` : ""),
      );
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : appText("text_c6e2f69acea3"));
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <article className="step-card admin-athlete-plan-access">
      <div className="form-section-header">
        <div>
          <p className="kicker">{appText("text_5ab748873f5f")}</p>
          <h2 className="form-section-title">{appText("text_bde6b1d26531")}</h2>
        </div>
        <span className="badge">{plans.length} {appText("text_64879f7d6b96")}{plans.length === 1 ? "" : appText("text_043a718774c5")}</span>
      </div>
      {warning ? <p className="error-text">{warning}</p> : null}
      {archivedIds.length ? (
        <div className="admin-athlete-plan-bulkbar">
          <label className="admin-athlete-plan-select">
            <input
              type="checkbox"
              checked={allArchivedSelected}
              onChange={toggleSelectAll}
              disabled={isDeleting}
              aria-label={appText("text_5dcf451bbb87")}
            />
            <span className="muted">
              {selectedCount > 0
                ? appText("text_529aacfdfd2b", { count: selectedCount })
                : appText("text_ef276ee1d896", { count: archivedIds.length })}
            </span>
          </label>
          <button
            type="button"
            className="ghost-button danger-button"
            onClick={() => void handleBulkDelete()}
            disabled={selectedCount === 0 || isDeleting || !accessToken}
          >
            {isDeleting
              ? appText("text_685ecb984ac2")
              : selectedCount
                ? appText("text_a84a0a76c974", { count: selectedCount })
                : appText("text_d2ab5d46fed4")}
          </button>
        </div>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
      {message ? <p className="success-banner">{message}</p> : null}
      {plans.length === 0 ? (
        <p className="muted">{appText("text_a8cde06b86df")}</p>
      ) : (
        <div className="admin-athlete-plan-list">
          {plans.map((plan) => {
            const archived = isArchivedPlan(plan);
            return (
              <div key={plan.plan_id} className="admin-athlete-plan-item">
                {archived ? (
                  <label className="admin-athlete-plan-select" aria-label={appText("text_cbe2f0672d5f", { name: getPlanDisplayName(plan) })}>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(plan.plan_id)}
                      onChange={() => toggleSelected(plan.plan_id)}
                      disabled={isDeleting}
                    />
                  </label>
                ) : (
                  <span className="admin-athlete-plan-select-spacer" aria-hidden="true" />
                )}
                <Link href={`/plans/${plan.plan_id}`} className="admin-athlete-plan-row">
                  <span>
                    <strong>{getPlanDisplayName(plan)}</strong>
                    <small>{formatDateTime(plan.created_at)} {appText("text_3aa9a00c0d74")}{plan.fight_date ? formatAppDate(plan.fight_date) : appText("text_1aef93991721")}</small>
                  </span>
                  <span className="badge">{statusLabel(plan.status)}</span>
                </Link>
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

function DiagnosticMetaItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="admin-diagnostic-meta-item">
      <span>{label}</span>
      <strong>{value?.trim() || "-"}</strong>
    </div>
  );
}

function GenerationDiagnosticCard({
  job,
  cancellingJobId,
  retryingJobId,
  resumingJobId,
  onCancel,
  onRetry,
  onApproveAndResume,
}: {
  job: AdminGenerationJobDiagnostic;
  cancellingJobId: string | null;
  retryingJobId: string | null;
  resumingJobId: string | null;
  onCancel: (job: AdminGenerationJobDiagnostic) => void;
  onRetry: (jobId: string) => void;
  onApproveAndResume: (jobId: string) => void;
}) {
    const appText = useAppTranslations("AppText");
  const summary = job.request_payload_summary ?? {};
  const showProfileRefreshWarning = hasProfileRefreshFailedWarning(job);
  const canCancel = job.status === "queued" || job.status === "running";

  return (
    <article className="admin-diagnostic-card">
      <div className="admin-diagnostic-card-header">
        <div>
          <p className="kicker">{appText("text_ad617a0fdd57")}{job.job_id}</p>
          <h3 className="review-card-title">{statusLabel(job.status)}</h3>
        </div>
        <div className="admin-diagnostic-badges">
          <span className="badge">{job.source || "unknown source"}</span>
          {job.stage2_status ? <span className="badge">{statusLabel(job.stage2_status)}</span> : null}
          {job.is_stale ? <span className="badge admin-diagnostic-badge-warning">{appText("text_40c9e59c5e15")}</span> : null}
        </div>
      </div>

      <div className="admin-diagnostic-meta-grid" aria-label={appText("text_a0b870990832")}>
        <DiagnosticMetaItem label={appText("text_d70b9e24bca2")} value={formatDateTime(job.created_at)} />
        <DiagnosticMetaItem label={appText("text_ecbc89cd37a0")} value={formatDateTime(job.started_at)} />
        <DiagnosticMetaItem label={appText("text_9df89427a7c8")} value={formatDateTime(job.heartbeat_at)} />
        <DiagnosticMetaItem label={appText("text_22a970d2e5b1")} value={formatDateTime(job.completed_at)} />
      </div>

      <div className="admin-diagnostic-section">
        <p className="admin-diagnostic-section-title">{appText("text_84d7e2bb8fbd")}</p>
        <div className="admin-diagnostic-summary-grid">
          <DiagnosticMetaItem label={appText("text_374d1c582c2a")} value={summary.athlete_name} />
          <DiagnosticMetaItem label={appText("text_86a6123f76f8")} value={summary.fight_date ? formatAppDate(summary.fight_date) : summary.fight_date} />
          <DiagnosticMetaItem label={appText("text_46342ec1eec9")} value={humanizeEnumValue(summary.phase, "-")} />
          <DiagnosticMetaItem label={appText("text_2f343666aaa8")} value={humanizeEnumValue(summary.fight_format, "-")} />
          <DiagnosticMetaItem label={appText("text_c83bec1f0284")} value={humanizeEnumValue(summary.fatigue_level, "-")} />
          <DiagnosticMetaItem label={appText("text_12f67f8539c4")} value={humanizeEnumValue(summary.training_availability, "-")} />
        </div>
      </div>

      <div className="admin-diagnostic-pill-groups">
        <div>
          <p className="review-detail-label">{appText("text_116cd3982a9b")}</p>
          <p className="review-detail-value">{formatListOrDash(summary.goals)}</p>
        </div>
        <div>
          <p className="review-detail-label">{appText("text_af393b754ae3")}</p>
          <p className="review-detail-value">{formatListOrDash(summary.weaknesses)}</p>
        </div>
        <div>
          <p className="review-detail-label">{appText("text_7fba05f2e12c")}</p>
          <p className="review-detail-value">{formatListOrDash(summary.injuries)}</p>
        </div>
      </div>

      <div className="admin-diagnostic-technical">
        <DiagnosticMetaItem label={appText("text_4e83876b2568")} value={job.client_request_id} />
        {job.retry_of ? <DiagnosticMetaItem label={appText("text_17d90ce4743f")} value={job.retry_of} /> : null}
      </div>

      {job.requires_admin_resume && !job.plan_id ? (
        <div className="admin-diagnostic-alert">
          {appText("text_9405b9c810fd")}</div>
      ) : null}
      {showProfileRefreshWarning ? (
        <div className="admin-profile-refresh-warning" role="alert">
          <strong>{PROFILE_REFRESH_FAILED_BANNER_TITLE}</strong>
          <p>{PROFILE_REFRESH_FAILED_BANNER_BODY}</p>
        </div>
      ) : null}
      {job.error ? <div className="error-banner" role="alert">{appText("text_617062906764")}{job.error}</div> : null}
      {job.is_stale ? (
        <div className="error-banner" role="alert">{appText("text_d0c8ece8c375")}{job.stale_reason || appText("text_09b4fbb228e8")}</div>
      ) : null}

      <div className="plan-summary-actions">
        {job.plan_id ? (
          <Link href={`/plans/${job.plan_id}`} className="ghost-button">
            {appText("text_9e70b18d5255")}</Link>
        ) : null}
        {job.status === "failed" ? (
          <button type="button" className="ghost-button" onClick={() => onRetry(job.job_id)} disabled={retryingJobId === job.job_id}>
            {retryingJobId === job.job_id ? appText("text_84a657bcf3d9") : appText("text_61d9e1d5480c")}
          </button>
        ) : null}
        {canCancel ? (
          <button
            type="button"
            className="ghost-button danger-button"
            onClick={() => onCancel(job)}
            disabled={cancellingJobId !== null}
          >
            {cancellingJobId === job.job_id ? appText("text_7b26131098bb") : appText("text_12ad4ee6d948")}
          </button>
        ) : null}
        {job.requires_admin_resume && !job.plan_id ? (
          <button
            type="button"
            className="cta"
            onClick={() => onApproveAndResume(job.job_id)}
            disabled={resumingJobId === job.job_id}
          >
            {resumingJobId === job.job_id ? appText("text_cee0e61bdf8c") : appText("text_e2a9cd45af93")}
          </button>
        ) : null}
      </div>
    </article>
  );
}

export default function AdminAthletePage() {
    const appText = useAppTranslations("AppText");
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [nutrition, setNutrition] = useState<NutritionWorkspaceState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSavingControls, setIsSavingControls] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [isReloading, setIsReloading] = useState(false);
  const [jobs, setJobs] = useState<AdminGenerationJobDiagnostic[]>([]);
  const [athletePlans, setAthletePlans] = useState<AdminPlanSummary[]>([]);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [nutritionLoadWarning, setNutritionLoadWarning] = useState<string | null>(null);
  const [jobsLoadWarning, setJobsLoadWarning] = useState<string | null>(null);
  const [plansLoadWarning, setPlansLoadWarning] = useState<string | null>(null);
  const [isSavingIntake, setIsSavingIntake] = useState(false);
  const [intakeDraft, setIntakeDraft] = useState<{
    key_goals: string[];
    weak_areas: string[];
  } | null>(null);

  const handleRetry = useCallback(() => {
    setLoadError(null);
    setReloadKey((value) => value + 1);
  }, []);
  const handlePlansDeleted = useCallback((deletedPlanIds: string[]) => {
    if (!deletedPlanIds.length) {
      return;
    }
    const removed = new Set(deletedPlanIds);
    setAthletePlans((current) => current.filter((plan) => !removed.has(plan.plan_id)));
  }, []);
  const latestIntakeFocusValidation = athlete?.latest_intake
    ? validatePerformanceFocusSelections(
      athlete.latest_intake.fight_date,
      {
        keyGoals: athlete.latest_intake.key_goals ?? [],
        weakAreas: athlete.latest_intake.weak_areas ?? [],
      },
      {
        timeZone: athlete.latest_intake.athlete.athlete_timezone,
      },
    )
    : null;
  const latestIntakeFocusError = latestIntakeFocusValidation?.isOverCap
    ? `Latest saved intake is over the focus cap. ${latestIntakeFocusValidation.errorMessage}`
    : null;
  useEffect(() => {
    if (!athlete?.latest_intake) return;
    setIntakeDraft({
      key_goals: athlete.latest_intake.key_goals ?? [],
      weak_areas: athlete.latest_intake.weak_areas ?? [],
    });
  }, [athlete?.athlete_id, athlete?.latest_intake]);
  const draftFocusValidation = athlete?.latest_intake && intakeDraft
    ? validatePerformanceFocusSelections(
      athlete.latest_intake.fight_date,
      { keyGoals: intakeDraft.key_goals, weakAreas: intakeDraft.weak_areas },
      { timeZone: athlete.latest_intake.athlete.athlete_timezone },
    )
    : null;

  const controller = useGenerationController({
    token: session?.access_token ?? null,
    storageKey: athleteId ? `unlxck:pending-generation:admin:${athleteId}` : null,
    createJob: async (clientRequestId) => {
      if (!session?.access_token) {
        throw new Error("Your session has expired. Please sign in again.");
      }
      if (!athleteId) {
        throw new Error("We couldn't identify this athlete. Go back and try again.");
      }
      return generateAdminAthletePlanFromLatestIntake(session.access_token, athleteId, clientRequestId);
    },
    onComplete: ({ planId, status, recovered }) => {
      const search = new URLSearchParams();
      if (status === "review_required") {
        search.set("review_required", "1");
      }
      if (recovered) {
        search.set("recovered", "1");
      }
      window.location.replace(`/plans/${planId}${search.toString() ? `?${search.toString()}` : ""}`);
    },
  });

  useEffect(() => {
    if (!session?.access_token || !athleteId) {
      return;
    }

    let active = true;
    setLoadError(null);
    setNutritionLoadWarning(null);
    setJobsLoadWarning(null);
    setPlansLoadWarning(null);
    setAthletePlans([]);
    setIsReloading(true);
    loadAdminAthleteProfileData({
      getAdminAthlete: () => getAdminAthlete(session.access_token, athleteId),
      getAdminAthleteNutritionCurrent: () => getAdminAthleteNutritionCurrent(session.access_token, athleteId),
      getAdminAthleteGenerationJobs: () => getAdminAthleteGenerationJobs(session.access_token, athleteId),
      listAdminPlans: () => listAdminPlans(session.access_token),
    })
      .then((profileData) => {
        if (!active) return;
        setAthlete(profileData.athlete);
        setNutrition(profileData.nutrition);
        setJobs(profileData.jobs);
        setAthletePlans(profileData.plans);
        setNutritionLoadWarning(profileData.nutritionWarning);
        setJobsLoadWarning(profileData.jobsWarning);
        setPlansLoadWarning(profileData.plansWarning);
      })
      .catch((athleteError) => {
        if (!active) return;
        setLoadError(athleteError instanceof Error ? athleteError.message : "Unable to load athlete profile.");
      })
      .finally(() => {
        if (active) setIsReloading(false);
      });

    return () => {
      active = false;
    };
  }, [athleteId, session?.access_token, reloadKey]);

  useEffect(() => {
    if (controller.error) {
      setError(controller.error);
    }
  }, [controller.error]);

  async function handleGenerateNewPlan() {
    if (!athlete?.latest_intake || !athleteId || controller.isGenerating) {
      return;
    }
    if (latestIntakeFocusError) {
      setError(latestIntakeFocusError);
      return;
    }
    setError(null);
    await controller.startGeneration();
  }
  async function handleRetryJob(jobId: string) {
    if (!session?.access_token || retryingJobId) return;
    setRetryingJobId(jobId);
    try {
      await retryGenerationJob(session.access_token, jobId);
      handleRetry();
    } finally {
      setRetryingJobId(null);
    }
  }

  async function handleCancelGenerationJob(job: AdminGenerationJobDiagnostic) {
    if (!session?.access_token || cancellingJobId) return;
    const confirmed = window.confirm(
      `Cancel generation for ${job.athlete_full_name || job.athlete_email || job.athlete_id || "this athlete"}?`,
    );
    if (!confirmed) return;
    setCancellingJobId(job.job_id);
    setError(null);
    setMessage(null);
    try {
      await cancelAdminGenerationJob(session.access_token, job.job_id);
      setJobs((current) =>
        current.map((item) =>
          item.job_id === job.job_id
            ? {
              ...item,
              status: "failed",
              error: "Generation cancelled by admin.",
              is_stale: false,
            }
            : item,
        ),
      );
      setMessage("Generation cancelled. Archived plan cleanup is now available.");
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Unable to cancel generation.");
    } finally {
      setCancellingJobId(null);
    }
  }

  const [resumingJobId, setResumingJobId] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);

  async function handleApproveAndResumeJob(jobId: string) {
    if (!session?.access_token || resumingJobId) return;
    setResumingJobId(jobId);
    setResumeError(null);
    try {
      await approveAndResumeGenerationFromJob(
        session.access_token,
        jobId,
        { reason: "admin reviewed and approved" },
      );
      setMessage("Resume queued. The new generation will create a real plan if Stage 2 succeeds.");
      setReloadKey((value) => value + 1);
    } catch (error) {
      setResumeError(error instanceof Error ? error.message : "Failed to start resume generation.");
    } finally {
      setResumingJobId(null);
    }
  }

  async function handleSaveCoachControls() {
    if (!session?.access_token || !athleteId || !nutrition || isSavingControls) {
      return;
    }
    setError(null);
    setMessage(null);
    setIsSavingControls(true);
    try {
      const updated = await updateAdminAthleteNutritionCurrent(
        session.access_token,
        athleteId,
        toNutritionUpdateRequest(nutrition),
      );
      setNutrition(updated);
      setMessage("Coach controls saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save coach controls.");
    } finally {
      setIsSavingControls(false);
    }
  }
  async function handleSaveIntake(andGenerate = false) {
    if (!session?.access_token || !athleteId || !intakeDraft || !athlete?.latest_intake || isSavingIntake) return;
    setIsSavingIntake(true);
    setError(null);
    try {
      const updated = await updateAdminAthleteLatestIntake(session.access_token, athleteId, {
        key_goals: intakeDraft.key_goals,
        weak_areas: intakeDraft.weak_areas,
      });
      setAthlete(updated);
      setMessage("Intake updated.");
      if (andGenerate) {
        await controller.startGeneration();
      }
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save intake updates.");
    } finally {
      setIsSavingIntake(false);
    }
  }

  return (
    <RequireAuth adminOnly>
      {loadError && !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">{appText("text_a121ff101a02")}</p>
          <div className="error-banner" role="alert">{loadError}</div>
          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              {appText("text_d6ac2209460b")}</Link>
            <button
              type="button"
              className="cta"
              onClick={handleRetry}
              disabled={isReloading}
            >
              {isReloading ? appText("text_84a657bcf3d9") : appText("text_d8b8392e2c54")}
            </button>
          </div>
        </section>
      ) : !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">{appText("text_a121ff101a02")}</p>
          <h1>{appText("text_3535ababfaeb")}</h1>
          <p className="muted">{appText("text_1668b1b48750")}</p>
        </section>
      ) : (
        <section className="panel athlete-profile-panel">
          <AthleteProfileHero athlete={athlete} />

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              {appText("text_d6ac2209460b")}</Link>
            <button
              type="button"
              className="cta"
              onClick={handleGenerateNewPlan}
              disabled={!athlete.latest_intake || controller.isGenerating || Boolean(latestIntakeFocusError)}
            >
              {controller.isGenerating ? appText("text_49286f33b674") : appText("text_55e94c4a5913")}
            </button>
          </div>
          {controller.statusMessage ? <p className="muted">{controller.statusMessage}</p> : null}
          {loadError ? (
            <div className="error-banner" role="alert">
              <span>{loadError}</span>
              <button
                type="button"
                className="ghost-button"
                onClick={handleRetry}
                disabled={isReloading}
              >
                {isReloading ? appText("text_84a657bcf3d9") : appText("text_d8b8392e2c54")}
              </button>
            </div>
          ) : null}
          {error ? (
            <div className="error-banner" role="alert">{error}</div>
          ) : null}
          {latestIntakeFocusError ? <p className="error-text">{latestIntakeFocusError}</p> : null}
          {latestIntakeFocusError && intakeDraft && athlete.latest_intake ? (
            <article className="step-card">
              <div className="form-section-header">
                <h2 className="form-section-title">{appText("text_c848a9db901a")}</h2>
                <p className="muted">{appText("text_a97cee832579")}</p>
              </div>
              <p className="error-text">
                {appText("text_79a2581cdfcf")}{latestIntakeFocusValidation?.cap?.maxSelections} {appText("text_f4e69d121184")}{draftFocusValidation?.totalSelections ?? 0}{appText("text_cdb4ee2aea69")}</p>
              <p><strong>{appText("text_5a721e0a4152")}</strong></p>
              <div className="athlete-profile-inline-pills">
                {intakeDraft.key_goals.map((goal) => <button key={goal} type="button" className="athlete-profile-pill athlete-profile-pill-compact" onClick={() => setIntakeDraft((c) => c ? { ...c, key_goals: c.key_goals.filter((g) => g !== goal) } : c)}>{goal} {appText("text_be64f28a8d0a")}</button>)}
              </div>
              <p><strong>{appText("text_ce2cd86d6c71")}</strong></p>
              <div className="athlete-profile-inline-pills">
                {intakeDraft.weak_areas.map((area) => <button key={area} type="button" className="athlete-profile-pill athlete-profile-pill-compact athlete-profile-pill-warning" onClick={() => setIntakeDraft((c) => c ? { ...c, weak_areas: c.weak_areas.filter((g) => g !== area) } : c)}>{area} {appText("text_be64f28a8d0a")}</button>)}
              </div>
              <p className={draftFocusValidation?.isOverCap ? "error-text" : "muted"}>
                {draftFocusValidation?.totalSelections ?? 0} {appText("text_8a5edab28263")}{draftFocusValidation?.cap?.maxSelections ?? latestIntakeFocusValidation?.cap?.maxSelections ?? 0} {appText("text_d7cbbb688b2e")}</p>
              <div className="plan-summary-actions">
                <button type="button" className="ghost-button" onClick={() => setIntakeDraft({ key_goals: athlete.latest_intake?.key_goals ?? [], weak_areas: athlete.latest_intake?.weak_areas ?? [] })}>{appText("text_f0714b3053e2")}</button>
                <button type="button" className="ghost-button" disabled={Boolean(draftFocusValidation?.isOverCap) || isSavingIntake} onClick={() => void handleSaveIntake(false)}>{appText("text_690aba60985f")}</button>
                <button type="button" className="cta" disabled={Boolean(draftFocusValidation?.isOverCap) || isSavingIntake || controller.isGenerating} onClick={() => void handleSaveIntake(true)}>{appText("text_ed7de9a4c494")}</button>
              </div>
            </article>
          ) : null}
          {!athlete.latest_intake ? (
            <p className="muted">{appText("text_c805e08aaeec")}</p>
          ) : null}

          <AthleteProfileOverviewCard athlete={athlete} />
          <AthletePlanAccessCard
            plans={athletePlans}
            warning={plansLoadWarning}
            accessToken={session?.access_token ?? null}
            onPlansDeleted={handlePlansDeleted}
          />
          <article className="step-card">
            <div className="form-section-header">
              <div>
                <p className="kicker">{appText("text_a1b2e1a99d33")}</p>
                <h2 className="form-section-title">{appText("text_f7ab18495077")}</h2>
              </div>
              <span className="badge">{jobs.length} {appText("text_5e8c9902207a")}{jobs.length === 1 ? "" : appText("text_043a718774c5")}</span>
            </div>
            {jobsLoadWarning ? <p className="error-text">{jobsLoadWarning}</p> : null}
            {resumeError ? <p className="error-text">{resumeError}</p> : null}
            {!jobs.length ? (
              <p className="muted">{appText("text_1e6a893b2f6f")}</p>
            ) : (
              <div className="admin-diagnostic-list">
                {jobs.map((job) => (
                  <GenerationDiagnosticCard
                    key={job.job_id}
                    job={job}
                    cancellingJobId={cancellingJobId}
                    retryingJobId={retryingJobId}
                    resumingJobId={resumingJobId}
                    onCancel={(selectedJob) => void handleCancelGenerationJob(selectedJob)}
                    onRetry={(jobId) => void handleRetryJob(jobId)}
                    onApproveAndResume={(jobId) => void handleApproveAndResumeJob(jobId)}
                  />
                ))}
              </div>
            )}
          </article>
          {nutrition ? (
            <div className="split-layout nutrition-admin-split">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_aaaca671ee66")}</p>
                  <h2 className="form-section-title">{appText("text_f4488b15b1d5")}</h2>
                </div>
                <div className="review-detail-list nutrition-review-list">
                  {[
                    [appText("text_df42a4d5d353"), humanizeEnumValue(nutrition.derived.foundation_status, appText("text_b764cdc0eab7"))],
                    [appText("text_78a14d0fe2ba"), nutrition.derived.days_until_fight != null ? String(nutrition.derived.days_until_fight) : appText("text_4895f73177ab")],
                    [appText("text_44c03cecc032"), nutrition.derived.current_phase_effective || appText("text_3bdd1db64207")],
                    [appText("text_567bd1996d3a"), `${nutrition.derived.weight_cut_pct.toFixed(1)}%`],
                    [
                      appText("text_10c9502fffb6"),
                      nutrition.derived.readiness_flags.length
                        ? nutrition.derived.readiness_flags.map((flag) => humanizeEnumValue(flag, flag)).join(", ")
                        : appText("text_cc9ea7f7c64e"),
                    ],
                  ].map(([label, value]) => (
                    <div key={label} className="review-detail-row">
                      <p className="review-detail-label">{label}</p>
                      <p className="review-detail-value">{translateUiText(appText, value)}</p>
                    </div>
                  ))}
                </div>
              </article>

              <aside className="step-aside athlete-motion-slot athlete-motion-rail">
                <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_d50bfbb470c9")}</p>
                  <h2 className="form-section-title">{appText("text_61a0ff51de2a")}</h2>
                </div>
                {nutritionLoadWarning ? <p className="error-text">{nutritionLoadWarning}</p> : null}
                <div className="nutrition-admin-controls">
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.coach_override_enabled}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    coach_override_enabled: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">{appText("text_544a658c62cc")}</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.athlete_override_enabled}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    athlete_override_enabled: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">{appText("text_45fb6dac893a")}</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.fight_week_manual_mode}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    fight_week_manual_mode: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">{appText("text_d93d12d3608f")}</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.water_cut_locked_to_manual}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    water_cut_locked_to_manual: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">{appText("text_7df13111e608")}</span>
                      </span>
                    </label>
                    <div className="field">
                      <label htmlFor="coachCalorieFloor">{appText("text_33d417c624e3")}</label>
                      <input
                        id="coachCalorieFloor"
                        type="number"
                        inputMode="numeric"
                        value={nutrition.nutrition_coach_controls.do_not_reduce_below_calories ?? ""}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    do_not_reduce_below_calories: event.target.value ? Number(event.target.value) : null,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="coachProteinFloor">{appText("text_7d4016c06a8d")}</label>
                      <input
                        id="coachProteinFloor"
                        type="number"
                        step="0.1"
                        inputMode="decimal"
                        value={nutrition.nutrition_coach_controls.protein_floor_g_per_kg ?? ""}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    protein_floor_g_per_kg: event.target.value ? Number(event.target.value) : null,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                    </div>
                    <div className="plan-summary-actions">
                      <button type="button" className="cta" onClick={handleSaveCoachControls} disabled={isSavingControls}>
                        {isSavingControls ? appText("text_dc85af8f2b1d") : appText("text_77974eeca353")}
                      </button>
                    </div>
                  </div>
                </div>
              </aside>
            </div>
          ) : nutritionLoadWarning ? (
            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">{appText("text_d50bfbb470c9")}</p>
                <h2 className="form-section-title">{appText("text_61a0ff51de2a")}</h2>
              </div>
              <p className="error-text">{nutritionLoadWarning}</p>
            </article>
          ) : null}
          {message ? <div className="success-banner">{message}</div> : null}
        </section>
      )}
    </RequireAuth>
  );
}
