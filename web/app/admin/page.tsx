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
import {
  PROFILE_REFRESH_FAILED_BANNER_BODY,
  PROFILE_REFRESH_FAILED_BANNER_TITLE,
  hasProfileRefreshFailedWarning,
} from "@/lib/profile-refresh-warning";
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

function countActiveJobStates(jobs: AdminGenerationJobDiagnostic[]) {
  return jobs.reduce(
    (counts, job) => {
      if (job.is_stale) {
        counts.stale += 1;
      } else if (job.status === "running") {
        counts.running += 1;
      } else {
        counts.queued += 1;
      }
      return counts;
    },
    { queued: 0, running: 0, stale: 0 },
  );
}

function ProfileRefreshWarningBanner({ job }: { job: AdminGenerationJobDiagnostic }) {
  if (!hasProfileRefreshFailedWarning(job)) {
    return null;
  }

  return (
    <div className="admin-profile-refresh-warning" role="alert">
      <strong>{PROFILE_REFRESH_FAILED_BANNER_TITLE}</strong>
      <p>{PROFILE_REFRESH_FAILED_BANNER_BODY}</p>
    </div>
  );
}

const DIRECTORY_PAGE_SIZE = 20;
const ACTIVE_JOBS_POLL_INTERVAL_MS = 8000;
const SEARCH_DEBOUNCE_MS = 300;

export default function AdminPage() {
  const { isReady, isMeHydrated, session, me } = useAppSession();
  const [athletes, setAthletes] = useState<AdminAthleteRecord[]>([]);
  const [plans, setPlans] = useState<AdminPlanSummary[]>([]);
  const [activeJobs, setActiveJobs] = useState<AdminGenerationJobDiagnostic[]>([]);
  const [triageJobs, setTriageJobs] = useState<AdminGenerationJobDiagnostic[]>([]);
  const [isDirectoryLoading, setIsDirectoryLoading] = useState(true);
  const [isJobsLoading, setIsJobsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeWarning, setActiveWarning] = useState<string | null>(null);
  const [triageWarning, setTriageWarning] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchNeedle, setSearchNeedle] = useState("");
  const [athletesOffset, setAthletesOffset] = useState(0);
  const [plansOffset, setPlansOffset] = useState(0);
  const [athletesHasMore, setAthletesHasMore] = useState(false);
  const [plansHasMore, setPlansHasMore] = useState(false);
  const [resumingJobId, setResumingJobId] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);

  const token = session?.access_token;
  const isAdminReady =
    isReady && isMeHydrated && Boolean(token) && me?.profile?.role === "admin";
  const isLoading = isDirectoryLoading || isJobsLoading;

  const handleRetry = useCallback(() => {
    setMessage(null);
    setReloadKey((value) => value + 1);
  }, []);

  // Debounce the raw search box into the value we send to the server so that
  // each keystroke does not fire a paginated query against the API. Resetting
  // the page offsets in the same batched update (rather than a separate effect
  // keyed on searchNeedle) keeps a search change to a single directory fetch:
  // splitting them would fire one request with the stale offset and another at
  // page 1, racing each other for which result lands last.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearchNeedle(searchQuery.trim().toLowerCase());
      setAthletesOffset(0);
      setPlansOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [searchQuery]);

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
        job.request_payload_summary?.athlete_name,
        job.request_payload_summary?.fight_date,
        job.request_payload_summary?.fight_format,
        job.request_payload_summary?.goals,
        job.request_payload_summary?.injuries,
      ).includes(searchNeedle),
    );
  }, [activeJobs, searchNeedle]);

  const activeAthleteCount = useMemo(
    () => new Set(activeJobs.map((job) => job.athlete_id).filter(Boolean)).size,
    [activeJobs],
  );

  const activeJobStates = useMemo(() => countActiveJobStates(activeJobs), [activeJobs]);

  const triageAthleteCount = useMemo(
    () => new Set(triageJobs.map((job) => job.athlete_id).filter(Boolean)).size,
    [triageJobs],
  );

  const lastCheckedLabel = lastCheckedAt
    ? `Live jobs checked ${formatDateTime(lastCheckedAt)}`
    : isJobsLoading
      ? "Checking live generation jobs"
      : "Not checked yet";

  // Directory data (athletes + plans). Filtering and pagination happen on the
  // server so the dashboard scales past a few dozen records: the search term
  // and page offsets are query parameters, not client-side array work.
  useEffect(() => {
    if (!isAdminReady || !token) {
      if (isReady && isMeHydrated) {
        setIsDirectoryLoading(false);
      }
      return;
    }

    let active = true;
    setIsDirectoryLoading(true);
    setError(null);
    Promise.allSettled([
      listAdminAthletes(token, { q: searchNeedle, limit: DIRECTORY_PAGE_SIZE, offset: athletesOffset }),
      listAdminPlans(token, { q: searchNeedle, limit: DIRECTORY_PAGE_SIZE, offset: plansOffset }),
    ])
      .then(([athletesResult, plansResult]) => {
        if (!active) return;
        const loadErrors: string[] = [];

        if (athletesResult.status === "fulfilled") {
          setAthletes(athletesResult.value);
          setAthletesHasMore(athletesResult.value.length === DIRECTORY_PAGE_SIZE);
        } else {
          loadErrors.push(getErrorMessage(athletesResult.reason, "Unable to load athlete accounts."));
        }

        if (plansResult.status === "fulfilled") {
          setPlans(plansResult.value);
          setPlansHasMore(plansResult.value.length === DIRECTORY_PAGE_SIZE);
        } else {
          loadErrors.push(getErrorMessage(plansResult.reason, "Unable to load plan history."));
        }

        setError(loadErrors.length ? loadErrors.join(" ") : null);
      })
      .catch((adminError) => {
        if (!active) return;
        setError(adminError instanceof Error ? adminError.message : "Unable to load admin data.");
      })
      .finally(() => {
        if (active) {
          setIsDirectoryLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [
    isAdminReady,
    isReady,
    isMeHydrated,
    me?.profile.role,
    token,
    searchNeedle,
    athletesOffset,
    plansOffset,
    reloadKey,
  ]);

  // Live generation jobs (active + triage). These are bounded queues that move
  // on their own, so we poll them on a fixed interval instead of reloading the
  // whole dashboard. Athlete and plan directories stay put while jobs refresh.
  useEffect(() => {
    if (!isAdminReady || !token) {
      if (isReady && isMeHydrated) {
        setIsJobsLoading(false);
      }
      return;
    }

    let active = true;

    const loadJobs = (isInitial: boolean) => {
      if (isInitial) {
        setIsJobsLoading(true);
      }
      Promise.allSettled([
        listAdminActiveGenerationJobs(token),
        listAdminTriageGenerationJobs(token),
      ])
        .then(([activeResult, triageResult]) => {
          if (!active) return;

          if (activeResult.status === "fulfilled") {
            setActiveJobs(activeResult.value);
            setActiveWarning(null);
          } else {
            // On a transient poll failure keep the last good snapshot rather
            // than blanking the live monitor; only clear it on first load.
            if (isInitial) setActiveJobs([]);
            setActiveWarning(getErrorMessage(activeResult.reason, "Unable to load active generation jobs."));
          }

          if (triageResult.status === "fulfilled") {
            setTriageJobs(triageResult.value);
            setTriageWarning(null);
          } else {
            if (isInitial) setTriageJobs([]);
            setTriageWarning(getErrorMessage(triageResult.reason, "Unable to load suspended triage jobs."));
          }

          setLastCheckedAt(new Date().toISOString());
        })
        .finally(() => {
          if (active && isInitial) {
            setIsJobsLoading(false);
          }
        });
    };

    loadJobs(true);
    const timer = setInterval(() => loadJobs(false), ACTIVE_JOBS_POLL_INTERVAL_MS);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [isAdminReady, isReady, isMeHydrated, me?.profile.role, token, reloadKey]);

  const athletesPage = Math.floor(athletesOffset / DIRECTORY_PAGE_SIZE) + 1;
  const plansPage = Math.floor(plansOffset / DIRECTORY_PAGE_SIZE) + 1;

  const goToAthletesPage = useCallback((delta: number) => {
    setAthletesOffset((value) => Math.max(0, value + delta * DIRECTORY_PAGE_SIZE));
  }, []);

  const goToPlansPage = useCallback((delta: number) => {
    setPlansOffset((value) => Math.max(0, value + delta * DIRECTORY_PAGE_SIZE));
  }, []);

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
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : activeJobs.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? "Checking jobs."
                  : `${activeAthleteCount} athlete${activeAthleteCount === 1 ? "" : "s"} in progress.`}
              </p>
            </article>
            <article className="status-card">
              <p className="status-label">Triage queue</p>
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : triageJobs.length}</h2>
              <p className="muted">{isJobsLoading ? "Checking jobs." : `${triageAthleteCount} athlete${triageAthleteCount === 1 ? "" : "s"} waiting.`}</p>
            </article>
            <article className="status-card">
              <p className="status-label">Athletes</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : athletes.length}</h2>
              <p className="muted">{searchNeedle ? "Matches on this page." : "Accounts on this page."}</p>
            </article>
            <article className="status-card">
              <p className="status-label">Plans</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : plans.length}</h2>
              <p className="muted">{searchNeedle ? "Matches on this page." : "Generations on this page."}</p>
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
              placeholder="Name, email, username, status"
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
              <p className="muted admin-panel-subtext">{lastCheckedLabel}</p>
            </div>
            <span className="badge">
              {isJobsLoading
                ? "Checking"
                : searchNeedle
                  ? `${filteredActiveJobs.length}/${activeJobs.length} active`
                  : `${activeJobs.length} active`}
            </span>
          </div>

          {!isJobsLoading ? (
            <div className="admin-active-summary" aria-label="Active generation states">
              <span>Running {activeJobStates.running}</span>
              <span>Queued {activeJobStates.queued}</span>
              <span>Stale {activeJobStates.stale}</span>
            </div>
          ) : null}

          {isJobsLoading ? (
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
                    <ProfileRefreshWarningBanner job={job} />
                    {job.is_stale ? <p className="error-text">{job.stale_reason || "This generation has stopped heartbeating."}</p> : null}
                    <p className="muted">Fight date: {job.request_payload_summary?.fight_date || "Not set"}</p>
                    <p className="muted">Format: {job.request_payload_summary?.fight_format || "Not set"}</p>
                    <p className="muted">Goals: {joinOrDash(job.request_payload_summary?.goals)}</p>
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
            <span className="badge">{isJobsLoading ? "Checking" : `${triageJobs.length} open`}</span>
          </div>

          {isJobsLoading ? (
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
                    <ProfileRefreshWarningBanner job={job} />
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

            {isDirectoryLoading ? (
              <div className="support-panel">
                <p className="muted">Loading athlete accounts...</p>
              </div>
            ) : athletes.length === 0 && searchNeedle ? (
              <div className="support-panel">
                <p className="muted">No athlete accounts match this search.</p>
              </div>
            ) : athletes.length === 0 && athletesOffset > 0 ? (
              <div className="support-panel">
                <p className="muted">No more athlete accounts on this page.</p>
              </div>
            ) : athletes.length === 0 ? (
              <EmptyState
                eyebrow="Athlete accounts"
                title="No athletes yet."
                description="Athlete accounts appear here once someone signs up to the beta."
                example="Each row will show the athlete's name, email, saved plan count, and a link into their profile for support."
                primaryAction={{ label: "Open signup page", href: "/signup" }}
              />
            ) : (
              <>
                <div className="plans-grid">
                  {athletes.map((athlete) => (
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
                <div className="admin-pager" aria-label="Athlete pagination">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToAthletesPage(-1)}
                    disabled={isDirectoryLoading || athletesOffset === 0}
                  >
                    Previous
                  </button>
                  <span className="muted">Page {athletesPage}</span>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToAthletesPage(1)}
                    disabled={isDirectoryLoading || !athletesHasMore}
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </article>

          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Plans</p>
              <h2>{searchNeedle ? "Matching generations" : "Latest generations"}</h2>
            </div>

            {isDirectoryLoading ? (
              <div className="support-panel">
                <p className="muted">Loading plan history...</p>
              </div>
            ) : plans.length === 0 && searchNeedle ? (
              <div className="support-panel">
                <p className="muted">No plan history matches this search.</p>
              </div>
            ) : plans.length === 0 && plansOffset > 0 ? (
              <div className="support-panel">
                <p className="muted">No more plans on this page.</p>
              </div>
            ) : plans.length === 0 ? (
              <EmptyState
                eyebrow="Plan history"
                title="No plans generated yet."
                description="Generated fight camps appear here once athletes start creating them."
                example="Each row will show plan name, athlete email, status, creation time, and a quick open link."
                primaryAction={{ label: "Open Demo Plan", href: "/demo-plan" }}
              />
            ) : (
              <>
                <div className="plans-grid">
                  {plans.map((plan) => (
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
                <div className="admin-pager" aria-label="Plan pagination">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToPlansPage(-1)}
                    disabled={isDirectoryLoading || plansOffset === 0}
                  >
                    Previous
                  </button>
                  <span className="muted">Page {plansPage}</span>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToPlansPage(1)}
                    disabled={isDirectoryLoading || !plansHasMore}
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </article>
        </div>
      </section>
    </RequireAuth>
  );
}
