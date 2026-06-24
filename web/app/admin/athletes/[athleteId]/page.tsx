"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteProfileHero,
  AthleteProfileOverviewCard,
} from "@/components/admin-athlete-profile";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import {
  approveAndResumeGenerationFromJob,
  bulkPermanentlyDeleteArchivedPlans,
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
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete the selected plans.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <article className="step-card admin-athlete-plan-access">
      <div className="form-section-header">
        <div>
          <p className="kicker">Athlete plans</p>
          <h2 className="form-section-title">Saved plan history</h2>
        </div>
        <span className="badge">{plans.length} plan{plans.length === 1 ? "" : "s"}</span>
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
              aria-label="Select all archived plans"
            />
            <span className="muted">
              {selectedCount > 0 ? `${selectedCount} selected` : `Select archived (${archivedIds.length})`}
            </span>
          </label>
          <button
            type="button"
            className="ghost-button danger-button"
            onClick={() => void handleBulkDelete()}
            disabled={selectedCount === 0 || isDeleting || !accessToken}
          >
            {isDeleting ? "Deleting..." : `Delete selected${selectedCount ? ` (${selectedCount})` : ""}`}
          </button>
        </div>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
      {message ? <p className="success-banner">{message}</p> : null}
      {plans.length === 0 ? (
        <p className="muted">No saved plans were found for this athlete.</p>
      ) : (
        <div className="admin-athlete-plan-list">
          {plans.map((plan) => {
            const archived = isArchivedPlan(plan);
            return (
              <div key={plan.plan_id} className="admin-athlete-plan-item">
                {archived ? (
                  <label className="admin-athlete-plan-select" aria-label={`Select ${getPlanDisplayName(plan)}`}>
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
                    <small>{formatDateTime(plan.created_at)} - fight date {plan.fight_date ? formatAppDate(plan.fight_date) : "not set"}</small>
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
  retryingJobId,
  resumingJobId,
  onRetry,
  onApproveAndResume,
}: {
  job: AdminGenerationJobDiagnostic;
  retryingJobId: string | null;
  resumingJobId: string | null;
  onRetry: (jobId: string) => void;
  onApproveAndResume: (jobId: string) => void;
}) {
  const summary = job.request_payload_summary ?? {};
  const showProfileRefreshWarning = hasProfileRefreshFailedWarning(job);

  return (
    <article className="admin-diagnostic-card">
      <div className="admin-diagnostic-card-header">
        <div>
          <p className="kicker">Job {job.job_id}</p>
          <h3 className="review-card-title">{statusLabel(job.status)}</h3>
        </div>
        <div className="admin-diagnostic-badges">
          <span className="badge">{job.source || "unknown source"}</span>
          {job.stage2_status ? <span className="badge">{statusLabel(job.stage2_status)}</span> : null}
          {job.is_stale ? <span className="badge admin-diagnostic-badge-warning">Stale</span> : null}
        </div>
      </div>

      <div className="admin-diagnostic-meta-grid" aria-label="Generation job timeline">
        <DiagnosticMetaItem label="Created" value={formatDateTime(job.created_at)} />
        <DiagnosticMetaItem label="Started" value={formatDateTime(job.started_at)} />
        <DiagnosticMetaItem label="Heartbeat" value={formatDateTime(job.heartbeat_at)} />
        <DiagnosticMetaItem label="Completed" value={formatDateTime(job.completed_at)} />
      </div>

      <div className="admin-diagnostic-section">
        <p className="admin-diagnostic-section-title">Request summary</p>
        <div className="admin-diagnostic-summary-grid">
          <DiagnosticMetaItem label="Athlete" value={summary.athlete_name} />
          <DiagnosticMetaItem label="Fight date" value={summary.fight_date ? formatAppDate(summary.fight_date) : summary.fight_date} />
          <DiagnosticMetaItem label="Phase" value={humanizeEnumValue(summary.phase, "-")} />
          <DiagnosticMetaItem label="Format" value={humanizeEnumValue(summary.fight_format, "-")} />
          <DiagnosticMetaItem label="Fatigue" value={humanizeEnumValue(summary.fatigue_level, "-")} />
          <DiagnosticMetaItem label="Availability" value={humanizeEnumValue(summary.training_availability, "-")} />
        </div>
      </div>

      <div className="admin-diagnostic-pill-groups">
        <div>
          <p className="review-detail-label">Goals</p>
          <p className="review-detail-value">{formatListOrDash(summary.goals)}</p>
        </div>
        <div>
          <p className="review-detail-label">Weaknesses</p>
          <p className="review-detail-value">{formatListOrDash(summary.weaknesses)}</p>
        </div>
        <div>
          <p className="review-detail-label">Injuries</p>
          <p className="review-detail-value">{formatListOrDash(summary.injuries)}</p>
        </div>
      </div>

      <div className="admin-diagnostic-technical">
        <DiagnosticMetaItem label="Client request" value={job.client_request_id} />
        {job.retry_of ? <DiagnosticMetaItem label="Retry of" value={job.retry_of} /> : null}
      </div>

      {job.requires_admin_resume && !job.plan_id ? (
        <div className="admin-diagnostic-alert">
          Protected triage: no plan row was created. Approve and resume to create a plan if Stage 2 succeeds.
        </div>
      ) : null}
      {showProfileRefreshWarning ? (
        <div className="admin-profile-refresh-warning" role="alert">
          <strong>{PROFILE_REFRESH_FAILED_BANNER_TITLE}</strong>
          <p>{PROFILE_REFRESH_FAILED_BANNER_BODY}</p>
        </div>
      ) : null}
      {job.error ? <div className="error-banner" role="alert">Error: {job.error}</div> : null}
      {job.is_stale ? (
        <div className="error-banner" role="alert">Stale warning: {job.stale_reason || "Job appears stale."}</div>
      ) : null}

      <div className="plan-summary-actions">
        {job.plan_id ? (
          <Link href={`/plans/${job.plan_id}`} className="ghost-button">
            Open plan
          </Link>
        ) : null}
        {job.status === "failed" ? (
          <button type="button" className="ghost-button" onClick={() => onRetry(job.job_id)} disabled={retryingJobId === job.job_id}>
            {retryingJobId === job.job_id ? "Retrying..." : "Retry job"}
          </button>
        ) : null}
        {job.requires_admin_resume && !job.plan_id ? (
          <button
            type="button"
            className="cta"
            onClick={() => onApproveAndResume(job.job_id)}
            disabled={resumingJobId === job.job_id}
          >
            {resumingJobId === job.job_id ? "Approving..." : "Approve & Resume"}
          </button>
        ) : null}
      </div>
    </article>
  );
}

export default function AdminAthletePage() {
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
          <p className="kicker">Athlete Profile</p>
          <div className="error-banner" role="alert">{loadError}</div>
          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
            <button
              type="button"
              className="cta"
              onClick={handleRetry}
              disabled={isReloading}
            >
              {isReloading ? "Retrying..." : "Try again"}
            </button>
          </div>
        </section>
      ) : !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <h1>Loading profile</h1>
          <p className="muted">Fetching athlete record now.</p>
        </section>
      ) : (
        <section className="panel athlete-profile-panel">
          <AthleteProfileHero athlete={athlete} />

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
            <button
              type="button"
              className="cta"
              onClick={handleGenerateNewPlan}
              disabled={!athlete.latest_intake || controller.isGenerating || Boolean(latestIntakeFocusError)}
            >
              {controller.isGenerating ? "Generating..." : "Generate new plan"}
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
                {isReloading ? "Retrying..." : "Try again"}
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
                <h2 className="form-section-title">Resolve intake issues</h2>
                <p className="muted">This saved intake needs a small update before a new plan can be generated.</p>
              </div>
              <p className="error-text">
                Focus cap exceeded. This camp allows {latestIntakeFocusValidation?.cap?.maxSelections} total focus picks. Current intake has {draftFocusValidation?.totalSelections ?? 0}.
              </p>
              <p><strong>Key goals</strong></p>
              <div className="athlete-profile-inline-pills">
                {intakeDraft.key_goals.map((goal) => <button key={goal} type="button" className="athlete-profile-pill athlete-profile-pill-compact" onClick={() => setIntakeDraft((c) => c ? { ...c, key_goals: c.key_goals.filter((g) => g !== goal) } : c)}>{goal} ✕</button>)}
              </div>
              <p><strong>Weak areas</strong></p>
              <div className="athlete-profile-inline-pills">
                {intakeDraft.weak_areas.map((area) => <button key={area} type="button" className="athlete-profile-pill athlete-profile-pill-compact athlete-profile-pill-warning" onClick={() => setIntakeDraft((c) => c ? { ...c, weak_areas: c.weak_areas.filter((g) => g !== area) } : c)}>{area} ✕</button>)}
              </div>
              <p className={draftFocusValidation?.isOverCap ? "error-text" : "muted"}>
                {draftFocusValidation?.totalSelections ?? 0} / {draftFocusValidation?.cap?.maxSelections ?? latestIntakeFocusValidation?.cap?.maxSelections ?? 0} selected
              </p>
              <div className="plan-summary-actions">
                <button type="button" className="ghost-button" onClick={() => setIntakeDraft({ key_goals: athlete.latest_intake?.key_goals ?? [], weak_areas: athlete.latest_intake?.weak_areas ?? [] })}>Cancel changes</button>
                <button type="button" className="ghost-button" disabled={Boolean(draftFocusValidation?.isOverCap) || isSavingIntake} onClick={() => void handleSaveIntake(false)}>Save updated intake</button>
                <button type="button" className="cta" disabled={Boolean(draftFocusValidation?.isOverCap) || isSavingIntake || controller.isGenerating} onClick={() => void handleSaveIntake(true)}>Save and generate</button>
              </div>
            </article>
          ) : null}
          {!athlete.latest_intake ? (
            <p className="muted">Generate is available after this athlete has at least one saved intake.</p>
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
                <p className="kicker">Generation diagnosis</p>
                <h2 className="form-section-title">Recent generation jobs</h2>
              </div>
              <span className="badge">{jobs.length} job{jobs.length === 1 ? "" : "s"}</span>
            </div>
            {jobsLoadWarning ? <p className="error-text">{jobsLoadWarning}</p> : null}
            {resumeError ? <p className="error-text">{resumeError}</p> : null}
            {!jobs.length ? (
              <p className="muted">No generation jobs found.</p>
            ) : (
              <div className="admin-diagnostic-list">
                {jobs.map((job) => (
                  <GenerationDiagnosticCard
                    key={job.job_id}
                    job={job}
                    retryingJobId={retryingJobId}
                    resumingJobId={resumingJobId}
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
                  <p className="kicker">Nutrition summary</p>
                  <h2 className="form-section-title">Current weight and readiness</h2>
                </div>
                <div className="review-detail-list nutrition-review-list">
                  {[
                    ["Foundation", humanizeEnumValue(nutrition.derived.foundation_status, "Unknown")],
                    ["Days until fight", nutrition.derived.days_until_fight != null ? String(nutrition.derived.days_until_fight) : "Not set"],
                    ["Current phase", nutrition.derived.current_phase_effective || "Not derived yet"],
                    ["Weight cut", `${nutrition.derived.weight_cut_pct.toFixed(1)}%`],
                    [
                      "Readiness flags",
                      nutrition.derived.readiness_flags.length
                        ? nutrition.derived.readiness_flags.map((flag) => humanizeEnumValue(flag, flag)).join(", ")
                        : "Baseline",
                    ],
                  ].map(([label, value]) => (
                    <div key={label} className="review-detail-row">
                      <p className="review-detail-label">{label}</p>
                      <p className="review-detail-value">{value}</p>
                    </div>
                  ))}
                </div>
              </article>

              <aside className="step-aside athlete-motion-slot athlete-motion-rail">
                <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Coach controls</p>
                  <h2 className="form-section-title">Admin-only overrides</h2>
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
                        <span className="checkbox-card-title">Coach override enabled</span>
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
                        <span className="checkbox-card-title">Athlete override enabled</span>
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
                        <span className="checkbox-card-title">Fight week manual mode</span>
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
                        <span className="checkbox-card-title">Water cut locked to manual</span>
                      </span>
                    </label>
                    <div className="field">
                      <label htmlFor="coachCalorieFloor">Minimum calories</label>
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
                      <label htmlFor="coachProteinFloor">Protein floor (g/kg)</label>
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
                        {isSavingControls ? "Saving..." : "Save coach controls"}
                      </button>
                    </div>
                  </div>
                </div>
              </aside>
            </div>
          ) : nutritionLoadWarning ? (
            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Coach controls</p>
                <h2 className="form-section-title">Admin-only overrides</h2>
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
