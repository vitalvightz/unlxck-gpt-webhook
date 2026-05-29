"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import {
  approveAndResumeGenerationFromJob,
  listAdminActiveGenerationJobs,
  listAdminAthletes,
  listAdminPlans,
  listAdminTriageGenerationJobs,
} from "@/lib/api";
import type {
  AdminAthleteRecord,
  AdminGenerationJobDiagnostic,
  AdminPlanSummary,
} from "@/lib/types";

function getPlanDisplayName(plan: { plan_name?: string | null; full_name?: string | null; athlete_email: string }) {
  return plan.plan_name?.trim() || plan.full_name || plan.athlete_email;
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function normalizeForSearch(...parts: unknown[]): string {
  return parts
    .flatMap((part) => (Array.isArray(part) ? part : [part]))
    .filter((part): part is string | number => typeof part === "string" || typeof part === "number")
    .join(" ")
    .toLowerCase();
}

function joinOrDash(values: string[] | null | undefined): string {
  const joined = Array.isArray(values)
    ? values.filter((value) => value?.trim()).join(", ")
    : "";
  return joined || "None logged";
}

function getJobDisplayName(job: AdminGenerationJobDiagnostic): string {
  return (
    job.athlete_full_name?.trim() ||
    job.request_payload_summary.athlete_name?.trim() ||
    job.athlete_email?.trim() ||
    "Unassigned athlete"
  );
}

function formatJobSource(source?: string | null): string {
  const label = (source || "").trim().replace(/_/g, " ");
  return label || "unknown source";
}

function getJobStatusLabel(job: AdminGenerationJobDiagnostic): string {
  if (job.is_stale) {
    return "Stale";
  }
  return job.status === "queued" ? "Queued" : "Running";
}

function getActiveJobProgress(job: AdminGenerationJobDiagnostic): number {
  if (job.is_stale) {
    return 88;
  }
  return job.status === "running" ? 64 : 28;
}

export default function AdminPage() {
  const { isReady, isMeHydrated, session, me } = useAppSession();
  const [athletes, setAthletes] = useState<AdminAthleteRecord[]>([]);
  const [plans, setPlans] = useState<AdminPlanSummary[]>([]);
  const [activeJobs, setActiveJobs] = useState<AdminGenerationJobDiagnostic[]>([]);
  const [triageJobs, setTriageJobs] = useState<AdminGenerationJobDiagnostic[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeWarning, setActiveWarning] = useState<string | null>(null);
  const [triageWarning, setTriageWarning] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [resumingJobId, setResumingJobId] = useState<string | null>(null);

  const isAdminReady =
    isReady && isMeHydrated && Boolean(session?.access_token) && me?.profile?.role === "admin";

  const handleRetry = useCallback(() => {
    setMessage(null);
    setReloadKey((value) => value + 1);
  }, []);

  const searchNeedle = searchQuery.trim().toLowerCase();
  const filteredAthletes = useMemo(() => {
    if (!searchNeedle) return athletes;
    return athletes.filter((athlete) =>
      normalizeForSearch(
        athlete.full_name,
        athlete.email,
        athlete.role,
        athlete.professional_status,
        athlete.record,
        athlete.technical_style,
        athlete.tactical_style,
      ).includes(searchNeedle),
    );
  }, [athletes, searchNeedle]);

  const filteredPlans = useMemo(() => {
    if (!searchNeedle) return plans;
    return plans.filter((plan) =>
      normalizeForSearch(
        getPlanDisplayName(plan),
        plan.athlete_email,
        plan.full_name,
        plan.status,
        plan.fight_date,
        plan.technical_style,
      ).includes(searchNeedle),
    );
  }, [plans, searchNeedle]);

  const filteredActiveJobs = useMemo(() => {
    if (!searchNeedle) return activeJobs;
    return activeJobs.filter((job) =>
      normalizeForSearch(
        getJobDisplayName(job),
        job.athlete_email,
        job.athlete_id,
        job.status,
        job.source,
        job.stage2_status,
        job.request_payload_summary.athlete_name,
        job.request_payload_summary.fight_date,
        job.request_payload_summary.fight_format,
        job.request_payload_summary.goals,
        job.request_payload_summary.injuries,
      ).includes(searchNeedle),
    );
  }, [activeJobs, searchNeedle]);

  const activeAthleteCount = useMemo(
    () => new Set(activeJobs.map((job) => job.athlete_id).filter(Boolean)).size,
    [activeJobs],
  );

  const triageAthleteCount = useMemo(
    () => new Set(triageJobs.map((job) => job.athlete_id).filter(Boolean)).size,
    [triageJobs],
  );

  useEffect(() => {
    if (!isAdminReady || !session?.access_token) {
      if (isReady && isMeHydrated) {
        setIsLoading(false);
      }
      return;
    }

    let active = true;
    setIsLoading(true);
    setError(null);
    setActiveWarning(null);
    setTriageWarning(null);
    Promise.allSettled([
      listAdminAthletes(session.access_token),
      listAdminPlans(session.access_token),
      listAdminActiveGenerationJobs(session.access_token),
      listAdminTriageGenerationJobs(session.access_token),
    ])
      .then(([athletesResult, plansResult, activeResult, triageResult]) => {
        if (!active) return;
        const loadErrors: string[] = [];

        if (athletesResult.status === "fulfilled") {
          setAthletes(athletesResult.value);
        } else {
          loadErrors.push(getErrorMessage(athletesResult.reason, "Unable to load athlete accounts."));
        }

        if (plansResult.status === "fulfilled") {
          setPlans(plansResult.value);
        } else {
          loadErrors.push(getErrorMessage(plansResult.reason, "Unable to load plan history."));
        }

        if (activeResult.status === "fulfilled") {
          setActiveJobs(activeResult.value);
        } else {
          setActiveJobs([]);
          setActiveWarning(getErrorMessage(activeResult.reason, "Unable to load active generation jobs."));
        }

        if (triageResult.status === "fulfilled") {
          setTriageJobs(triageResult.value);
        } else {
          setTriageJobs([]);
          setTriageWarning(getErrorMessage(triageResult.reason, "Unable to load suspended triage jobs."));
        }

        setError(loadErrors.length ? loadErrors.join(" ") : null);
      })
      .catch((adminError) => {
        if (!active) return;
        setError(adminError instanceof Error ? adminError.message : "Unable to load admin data.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isAdminReady, isReady, isMeHydrated, me?.profile.role, session?.access_token, reloadKey]);

  async function handleApproveAndResumeJob(jobId: string) {
    if (!session?.access_token || resumingJobId) return;
    setResumingJobId(jobId);
    setError(null);
    setMessage(null);
    try {
      await approveAndResumeGenerationFromJob(
        session.access_token,
        jobId,
        { reason: "admin reviewed and approved from dashboard" },
      );
      setMessage("Resume queued. The triage item will leave the queue after refresh.");
      setReloadKey((value) => value + 1);
    } catch (resumeError) {
      setError(resumeError instanceof Error ? resumeError.message : "Failed to approve and resume generation.");
    } finally {
      setResumingJobId(null);
    }
  }

  return (
    <RequireAuth adminOnly>
      <section className="panel admin-dashboard-panel">
        <div className="section-heading admin-dashboard-heading">
          <div>
            <p className="kicker">Admin</p>
            <h1>Support dashboard</h1>
            <p className="muted">Review suspended triage generations, open athlete records, and audit recent plan output from one workspace.</p>
          </div>
          <div className="admin-summary-grid" aria-label="Admin dashboard summary">
            <article className="status-card">
              <p className="status-label">Generating now</p>
              <h2 className="plan-summary-title">{isLoading ? "-" : activeJobs.length}</h2>
              <p className="muted">
                {isLoading
                  ? "Checking jobs."
                  : `${activeAthleteCount} athlete${activeAthleteCount === 1 ? "" : "s"} in progress.`}
              </p>
            </article>
            <article className="status-card">
              <p className="status-label">Triage queue</p>
              <h2 className="plan-summary-title">{isLoading ? "-" : triageJobs.length}</h2>
              <p className="muted">{isLoading ? "Checking jobs." : `${triageAthleteCount} athlete${triageAthleteCount === 1 ? "" : "s"} waiting.`}</p>
            </article>
            <article className="status-card">
              <p className="status-label">Athletes</p>
              <h2 className="plan-summary-title">{isLoading ? "-" : athletes.length}</h2>
              <p className="muted">Accounts visible in support mode.</p>
            </article>
            <article className="status-card">
              <p className="status-label">Plans</p>
              <h2 className="plan-summary-title">{isLoading ? "-" : plans.length}</h2>
              <p className="muted">Generated plans and review states.</p>
            </article>
          </div>
        </div>

        {error ? (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="ghost-button"
              onClick={handleRetry}
              disabled={isLoading}
            >
              {isLoading ? "Retrying..." : "Try again"}
            </button>
          </div>
        ) : null}

        {message ? <div className="success-banner">{message}</div> : null}

        <div className="admin-toolbar">
          <div className="field admin-search-field">
            <label htmlFor="adminSearch">Search support records</label>
            <input
              id="adminSearch"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Name, email, status, style, fight date"
            />
          </div>
          <button
            type="button"
            className="ghost-button admin-refresh-button"
            onClick={handleRetry}
            disabled={isLoading}
          >
            {isLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        <article className="list-card admin-active-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">Live generation monitor</p>
              <h2>Plans currently being generated</h2>
            </div>
            <span className="badge">
              {isLoading
                ? "Checking"
                : searchNeedle
                  ? `${filteredActiveJobs.length}/${activeJobs.length} active`
                  : `${activeJobs.length} active`}
            </span>
          </div>

          {isLoading ? (
            <div className="support-panel">
              <p className="muted">Loading active generation jobs...</p>
            </div>
          ) : activeWarning ? (
            <div className="support-panel">
              <p className="error-text">{activeWarning}</p>
              <p className="muted">Triage, athlete, and plan history can still be reviewed while this feed retries.</p>
            </div>
          ) : activeJobs.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">Idle</p>
              <h3 className="form-section-title">No plans are generating right now.</h3>
              <p className="muted">Queued and running jobs will appear here with athlete, timing, and plan context.</p>
            </div>
          ) : filteredActiveJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">No active generation jobs match this search.</p>
            </div>
          ) : (
            <div className="admin-active-list">
              {filteredActiveJobs.map((job) => (
                <article
                  key={job.job_id}
                  className={`admin-active-row ${job.is_stale ? "admin-active-row-stale" : ""}`.trim()}
                >
                  <div className="admin-active-row-main">
                    <div>
                      <h3 className="plan-card-title">{getJobDisplayName(job)}</h3>
                      <p className="muted">{job.athlete_email || job.athlete_id || "No athlete email"}</p>
                    </div>
                    <span className="badge">{getJobStatusLabel(job)}</span>
                  </div>
                  <div className="admin-active-progress" aria-label={`${getJobStatusLabel(job)} progress`}>
                    <span style={{ width: `${getActiveJobProgress(job)}%` }} />
                  </div>
                  <div className="admin-job-meta">
                    <span>Created {formatDateTime(job.created_at)}</span>
                    <span>Started {formatDateTime(job.started_at)}</span>
                    <span>Heartbeat {formatDateTime(job.heartbeat_at)}</span>
                    <span>Source {formatJobSource(job.source)}</span>
                  </div>
                  <div className="admin-job-summary">
                    {job.is_stale ? <p className="error-text">{job.stale_reason || "This generation has stopped heartbeating."}</p> : null}
                    <p className="muted">Fight date: {job.request_payload_summary.fight_date || "Not set"}</p>
                    <p className="muted">Format: {job.request_payload_summary.fight_format || "Not set"}</p>
                    <p className="muted">Goals: {joinOrDash(job.request_payload_summary.goals)}</p>
                  </div>
                  <div className="plan-card-actions">
                    {job.athlete_id ? (
                      <Link href={`/admin/athletes/${job.athlete_id}`} className="ghost-button">
                        Open athlete
                      </Link>
                    ) : null}
                    {job.plan_id ? (
                      <Link href={`/plans/${job.plan_id}`} className="ghost-button">
                        Open plan
                      </Link>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="list-card admin-triage-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">Triage resume queue</p>
              <h2>Suspended generations</h2>
            </div>
            <span className="badge">{isLoading ? "Checking" : `${triageJobs.length} open`}</span>
          </div>

          {isLoading ? (
            <div className="support-panel">
              <p className="muted">Loading protected triage jobs...</p>
            </div>
          ) : triageWarning ? (
            <div className="support-panel">
              <p className="error-text">{triageWarning}</p>
              <p className="muted">Athlete accounts and plan history can still be reviewed while the queue retries.</p>
            </div>
          ) : triageJobs.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">Clear</p>
              <h3 className="form-section-title">No suspended triage generations need approval.</h3>
              <p className="muted">New protected triage outcomes will appear here even when no plan row was created.</p>
            </div>
          ) : (
            <div className="plans-grid admin-queue-grid">
              {triageJobs.map((job) => (
                <article key={job.job_id} className="plan-card admin-triage-card">
                  <div className="plan-card-header">
                    <div>
                      <h3 className="plan-card-title">{getJobDisplayName(job)}</h3>
                      <p className="muted">{job.athlete_email || job.athlete_id || "No athlete email"}</p>
                    </div>
                    <span className="badge">Needs resume</span>
                  </div>
                  <p className="muted">
                    {job.stage2_status || "triage_blocked"} - no plan row was created, so this item is anchored to the generation job.
                  </p>
                  <div className="admin-job-meta">
                    <span>Created {formatDateTime(job.created_at)}</span>
                    <span>Source {job.source || "unknown"}</span>
                    <span>Job {job.job_id}</span>
                  </div>
                  <div className="admin-job-summary">
                    <p className="muted">Fight date: {job.request_payload_summary.fight_date || "Not set"}</p>
                    <p className="muted">Goals: {joinOrDash(job.request_payload_summary.goals)}</p>
                    <p className="muted">Injuries: {joinOrDash(job.request_payload_summary.injuries)}</p>
                  </div>
                  <div className="plan-card-actions">
                    {job.athlete_id ? (
                      <Link href={`/admin/athletes/${job.athlete_id}`} className="ghost-button">
                        Open athlete
                      </Link>
                    ) : null}
                    <button
                      type="button"
                      className="cta"
                      onClick={() => void handleApproveAndResumeJob(job.job_id)}
                      disabled={resumingJobId !== null}
                    >
                      {resumingJobId === job.job_id ? "Approving..." : "Approve & Resume"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <div className="admin-grid">
          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Athletes</p>
              <h2>{searchNeedle ? "Matching accounts" : "Recent accounts"}</h2>
            </div>

            {isLoading ? (
              <div className="support-panel">
                <p className="muted">Loading athlete accounts...</p>
              </div>
            ) : athletes.length === 0 ? (
              <EmptyState
                eyebrow="Athlete accounts"
                title="No athletes yet."
                description="Athlete accounts appear here once someone signs up to the beta."
                example="Each row will show the athlete's name, email, saved plan count, and a link into their profile for support."
                primaryAction={{ label: "Open signup page", href: "/signup" }}
              />
            ) : filteredAthletes.length === 0 ? (
              <div className="support-panel">
                <p className="muted">No athlete accounts match this search.</p>
              </div>
            ) : (
              <div className="plans-grid">
                {filteredAthletes.map((athlete) => (
                  <article key={athlete.athlete_id} className="plan-card">
                    <div className="plan-card-header">
                      <div>
                        <Link href={`/admin/athletes/${athlete.athlete_id}`}>
                          <h3 className="plan-card-title">{athlete.full_name || athlete.email}</h3>
                        </Link>
                        <p className="muted">{athlete.email}</p>
                      </div>
                      <span className="badge">{athlete.plan_count} plan{athlete.plan_count === 1 ? "" : "s"}</span>
                    </div>
                    <p className="muted">Created {formatDateTime(athlete.created_at)}</p>
                    <div className="plan-card-actions">
                      <Link href={`/admin/athletes/${athlete.athlete_id}`} className="ghost-button">
                        View profile
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>

          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Plans</p>
              <h2>{searchNeedle ? "Matching generations" : "Latest generations"}</h2>
            </div>

            {isLoading ? (
              <div className="support-panel">
                <p className="muted">Loading plan history...</p>
              </div>
            ) : plans.length === 0 ? (
              <EmptyState
                eyebrow="Plan history"
                title="No plans generated yet."
                description="Generated fight camps appear here once athletes start creating them."
                example="Each row will show plan name, athlete email, status, creation time, and a quick open link."
                primaryAction={{ label: "Open Demo Plan", href: "/demo-plan" }}
              />
            ) : filteredPlans.length === 0 ? (
              <div className="support-panel">
                <p className="muted">No plan history matches this search.</p>
              </div>
            ) : (
              <div className="plans-grid">
                {filteredPlans.map((plan) => (
                  <article key={plan.plan_id} className="plan-card">
                    <div className="plan-card-header">
                      <div>
                        <Link href={`/plans/${plan.plan_id}`}>
                          <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                        </Link>
                        <p className="muted">{plan.athlete_email}</p>
                      </div>
                      <span className="badge">{plan.status}</span>
                    </div>
                    <p className="muted">Created {formatDateTime(plan.created_at)}</p>
                    <div className="plan-card-actions">
                      <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
                        Open plan
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>
    </RequireAuth>
  );
}
