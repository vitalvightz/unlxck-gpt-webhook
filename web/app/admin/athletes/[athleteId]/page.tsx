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
  getAdminAthleteGenerationJobs,
  generateAdminAthletePlanFromLatestIntake,
  getAdminAthlete,
  getAdminAthleteNutritionCurrent,
  retryGenerationJob,
  updateAdminAthleteNutritionCurrent,
  updateAdminAthleteLatestIntake,
} from "@/lib/api";
import { loadAdminAthleteProfileData } from "@/lib/admin-athlete-profile-loader";
import { useGenerationController } from "@/lib/generation-controller";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import type { AdminAthleteRecord, AdminGenerationJobDiagnostic, NutritionWorkspaceState, NutritionWorkspaceUpdateRequest } from "@/lib/types";

function humanizeEnumValue(value: string | null | undefined, fallback: string): string {
  if (!value?.trim()) {
    return fallback;
  }
  return value
    .trim()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function joinOrDash(values: string[] | null | undefined): string {
  const joined = Array.isArray(values)
    ? values.filter((v) => v?.trim()).join(", ")
    : "";
  return joined || "—";
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
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [nutritionLoadWarning, setNutritionLoadWarning] = useState<string | null>(null);
  const [jobsLoadWarning, setJobsLoadWarning] = useState<string | null>(null);
  const [isSavingIntake, setIsSavingIntake] = useState(false);
  const [intakeDraft, setIntakeDraft] = useState<{
    key_goals: string[];
    weak_areas: string[];
  } | null>(null);

  const handleRetry = useCallback(() => {
    setLoadError(null);
    setReloadKey((value) => value + 1);
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
      if (!session?.access_token || !athleteId) {
        throw new Error("Session or athlete context is missing.");
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
    setIsReloading(true);
    loadAdminAthleteProfileData({
      getAdminAthlete: () => getAdminAthlete(session.access_token, athleteId),
      getAdminAthleteNutritionCurrent: () => getAdminAthleteNutritionCurrent(session.access_token, athleteId),
      getAdminAthleteGenerationJobs: () => getAdminAthleteGenerationJobs(session.access_token, athleteId),
    })
      .then((profileData) => {
        if (!active) return;
        setAthlete(profileData.athlete);
        setNutrition(profileData.nutrition);
        setJobs(profileData.jobs);
        setNutritionLoadWarning(profileData.nutritionWarning);
        setJobsLoadWarning(profileData.jobsWarning);
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
                Focus cap exceeded. This camp allows {latestIntakeFocusValidation?.maxSelections} total focus picks. Current intake has {(intakeDraft.key_goals.length + intakeDraft.weak_areas.length)}.
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
                {(intakeDraft.key_goals.length + intakeDraft.weak_areas.length)} / {draftFocusValidation?.maxSelections ?? latestIntakeFocusValidation?.maxSelections ?? 0} selected
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
          <article className="step-card">
            <div className="form-section-header">
              <p className="kicker">Admin debugging</p>
              <h2 className="form-section-title">Generation diagnostics</h2>
            </div>
            {jobsLoadWarning ? <p className="error-text">{jobsLoadWarning}</p> : null}
            {!jobs.length ? <p className="muted">No generation jobs found.</p> : jobs.map((job) => (
              <div key={job.job_id} className="review-detail-row" style={{ display: "block", marginBottom: "1rem" }}>
                <p><strong>{job.status.toUpperCase()}</strong> · {job.job_id}</p>
                <p className="muted">source {job.source} · created {job.created_at}</p>
                <p className="muted">started {job.started_at || "—"} · heartbeat {job.heartbeat_at || "—"} · completed {job.completed_at || "—"}</p>
                <p className="muted">client request {job.client_request_id || "—"}</p>
                {job.retry_of ? <p className="muted">retry of {job.retry_of}</p> : null}
                {job.plan_id ? <p><Link href={`/plans/${job.plan_id}`}>Open plan</Link></p> : null}
                {job.error ? <p className="error-text">Error: {job.error}</p> : null}
                {job.is_stale ? <p className="error-text">Stale warning: {job.stale_reason || "Job appears stale."}</p> : null}
                <p className="muted">
                  Payload: {job.request_payload_summary.athlete_name || "—"} · {job.request_payload_summary.fight_date || "—"} · {job.request_payload_summary.phase || "—"} · {job.request_payload_summary.fight_format || "—"} · fatigue {job.request_payload_summary.fatigue_level || "—"}
                </p>
                <p className="muted">Goals: {joinOrDash(job.request_payload_summary.goals)}</p>
                <p className="muted">Weaknesses: {joinOrDash(job.request_payload_summary.weaknesses)}</p>
                <p className="muted">Injuries: {joinOrDash(job.request_payload_summary.injuries)}</p>
                <p className="muted">Training availability: {job.request_payload_summary.training_availability || "—"}</p>
                {job.status === "failed" ? (
                  <button type="button" className="ghost-button" onClick={() => void handleRetryJob(job.job_id)} disabled={retryingJobId === job.job_id}>
                    {retryingJobId === job.job_id ? "Retrying..." : "Retry"}
                  </button>
                ) : null}
              </div>
            ))}
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
