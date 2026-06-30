"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { formatAppDate, formatAppDateTime } from "@/lib/date-format";
import {
  approveAndResumeGenerationFromJob,
  backfillStructuredPlans,
  bulkPermanentlyDeleteArchivedPlans,
  cancelAdminGenerationJob,
  listAdminActiveGenerationJobs,
  listAdminAthletes,
  listAdminPlans,
  listAdminReviewPlans,
  listAdminReviews,
  listAdminTriageGenerationJobs,
  resolveAdminReview,
} from "@/lib/api";
import {
  PROFILE_REFRESH_FAILED_BANNER_BODY,
  PROFILE_REFRESH_FAILED_BANNER_TITLE,
  hasProfileRefreshFailedWarning,
} from "@/lib/profile-refresh-warning";
import {
  PROFILE_UNAVAILABLE_ROW_LABEL,
  isProfileServiceUnavailableMessage,
  nonProfileSectionError,
  summarizeProfileWarning,
} from "@/lib/admin-profile-warning";
import type {
  AdminAthleteRecord,
  AdminGenerationJobDiagnostic,
  AdminPlanSummary,
  AdminReviewRecord,
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
  return Number.isNaN(date.getTime()) ? "Not recorded" : formatAppDateTime(value);
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

function isArchivedPlan(plan: AdminPlanSummary): boolean {
  return (plan.status || "").trim().toLowerCase() === "archived";
}

function ProfileUnavailableNote({ unavailable }: { unavailable?: boolean }) {
  if (!unavailable) {
    return null;
  }
  return <p className="muted admin-profile-unavailable-note">{PROFILE_UNAVAILABLE_ROW_LABEL}</p>;
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
  const [reviewPlans, setReviewPlans] = useState<AdminPlanSummary[]>([]);
  const [reviewPlansWarning, setReviewPlansWarning] = useState<string | null>(null);
  const [attentionReviews, setAttentionReviews] = useState<AdminReviewRecord[]>([]);
  const [attentionWarning, setAttentionWarning] = useState<string | null>(null);
  const [resolvingReviewId, setResolvingReviewId] = useState<string | null>(null);
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
  const [cancellingJobId, setCancellingJobId] = useState<string | null>(null);
  const [selectedArchivedPlanIds, setSelectedArchivedPlanIds] = useState<string[]>([]);
  const [bulkDeletingPlans, setBulkDeletingPlans] = useState(false);

  useEffect(() => {
    setSelectedArchivedPlanIds([]);
  }, [plansOffset, searchNeedle]);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [backfillPending, setBackfillPending] = useState(false);

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

  const archivedPlanIds = useMemo(
    () => plans.filter(isArchivedPlan).map((plan) => plan.plan_id),
    [plans],
  );
  const archivedPlanIdSet = useMemo(() => new Set(archivedPlanIds), [archivedPlanIds]);
  const selectedArchivedIds = useMemo(
    () => selectedArchivedPlanIds.filter((planId) => archivedPlanIdSet.has(planId)),
    [archivedPlanIdSet, selectedArchivedPlanIds],
  );
  const selectedArchivedCount = selectedArchivedIds.length;
  const allArchivedPlansSelected =
    archivedPlanIds.length > 0 && selectedArchivedCount === archivedPlanIds.length;

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
        listAdminReviewPlans(token),
        listAdminReviews(token, "pending"),
      ])
        .then(([activeResult, triageResult, reviewPlansResult, reviewsResult]) => {
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

          if (reviewPlansResult.status === "fulfilled") {
            setReviewPlans(reviewPlansResult.value);
            setReviewPlansWarning(null);
          } else {
            if (isInitial) setReviewPlans([]);
            setReviewPlansWarning(getErrorMessage(reviewPlansResult.reason, "Unable to load held/review plans."));
          }

          if (reviewsResult.status === "fulfilled") {
            setAttentionReviews(reviewsResult.value);
            setAttentionWarning(null);
          } else {
            if (isInitial) setAttentionReviews([]);
            setAttentionWarning(getErrorMessage(reviewsResult.reason, "Unable to load the athlete attention queue."));
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

  async function handleResolveReview(reviewId: string) {
    if (!session?.access_token || resolvingReviewId) return;
    setResolvingReviewId(reviewId);
    setError(null);
    setMessage(null);
    try {
      await resolveAdminReview(session.access_token, reviewId, {
        status: "resolved",
        resolution_notes: "reviewed from admin dashboard",
      });
      setAttentionReviews((reviews) => reviews.filter((review) => review.id !== reviewId));
      setMessage("Review resolved.");
    } catch (resolveError) {
      setError(resolveError instanceof Error ? resolveError.message : "Failed to resolve review.");
    } finally {
      setResolvingReviewId(null);
    }
  }

  async function handleBackfillStructuredPlans() {
    if (!session?.access_token || backfillPending) return;
    setBackfillPending(true);
    setError(null);
    setMessage(null);
    try {
      const result = await backfillStructuredPlans(session.access_token);
      setMessage(
        result.queued > 0
          ? `Queued ${result.queued} plan${result.queued === 1 ? "" : "s"} for structured-card backfill. Cards appear as each conversion finishes.`
          : "No plans need a structured-card backfill — every displayable plan already has one.",
      );
    } catch (backfillError) {
      setError(
        backfillError instanceof Error
          ? backfillError.message
          : "Failed to queue the structured-card backfill.",
      );
    } finally {
      setBackfillPending(false);
    }
  }

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

  async function handleCancelGenerationJob(job: AdminGenerationJobDiagnostic) {
    if (!session?.access_token || cancellingJobId) return;
    const confirmed = window.confirm(
      `Cancel generation for ${getJobDisplayName(job)}? This stops the active job so cleanup can continue.`,
    );
    if (!confirmed) return;
    setCancellingJobId(job.job_id);
    setError(null);
    setMessage(null);
    try {
      await cancelAdminGenerationJob(session.access_token, job.job_id);
      setActiveJobs((jobs) => jobs.filter((item) => item.job_id !== job.job_id));
      setMessage("Generation cancelled. You can archive or delete the related plan now.");
      setReloadKey((value) => value + 1);
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "Failed to cancel generation.");
    } finally {
      setCancellingJobId(null);
    }
  }

  function toggleArchivedPlan(planId: string) {
    setMessage(null);
    setError(null);
    setSelectedArchivedPlanIds((current) =>
      current.includes(planId) ? current.filter((id) => id !== planId) : [...current, planId],
    );
  }

  function toggleAllArchivedPlans() {
    setMessage(null);
    setError(null);
    setSelectedArchivedPlanIds(allArchivedPlansSelected ? [] : [...archivedPlanIds]);
  }

  async function handleBulkDeleteArchivedPlans() {
    if (!session?.access_token || selectedArchivedCount === 0 || bulkDeletingPlans) return;
    const confirmed = window.confirm(
      `Permanently delete ${selectedArchivedCount} archived plan${selectedArchivedCount === 1 ? "" : "s"}? This cannot be undone.`,
    );
    if (!confirmed) return;
    setBulkDeletingPlans(true);
    setError(null);
    setMessage(null);
    try {
      const result = await bulkPermanentlyDeleteArchivedPlans(session.access_token, selectedArchivedIds);
      const deleted = new Set(result.deleted);
      setPlans((current) => current.filter((plan) => !deleted.has(plan.plan_id)));
      setSelectedArchivedPlanIds((current) => current.filter((planId) => !deleted.has(planId)));
      setMessage(
        `Deleted ${result.deleted_count} archived plan${result.deleted_count === 1 ? "" : "s"}.` +
          (result.skipped_count ? ` ${result.skipped_count} skipped.` : ""),
      );
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete archived plans.");
    } finally {
      setBulkDeletingPlans(false);
    }
  }

  // Collapse every profile-service signal across the dashboard into a single
  // compact banner instead of repeating a giant error block per section. The
  // queues themselves stay rendered with whatever athlete detail is available.
  const rowsDegraded =
    activeJobs.some((job) => job.profile_unavailable) ||
    triageJobs.some((job) => job.profile_unavailable) ||
    reviewPlans.some((plan) => plan.profile_unavailable);
  const profileWarning = summarizeProfileWarning({
    sectionErrors: [error, activeWarning, triageWarning, reviewPlansWarning, attentionWarning],
    rowsDegraded,
  });

  // Hide profile-service errors from per-section blocks (the compact banner
  // covers them) while still surfacing genuine, unrelated queue failures.
  const directoryDisplayError = nonProfileSectionError(error);
  const activeDisplayWarning = nonProfileSectionError(activeWarning);
  const triageDisplayWarning = nonProfileSectionError(triageWarning);
  const reviewPlansDisplayWarning = nonProfileSectionError(reviewPlansWarning);
  const attentionDisplayWarning = nonProfileSectionError(attentionWarning);
  const activeProfileError = isProfileServiceUnavailableMessage(activeWarning);
  const triageProfileError = isProfileServiceUnavailableMessage(triageWarning);
  const hasQueueWarning = Boolean(triageWarning || reviewPlansWarning || attentionWarning);
  const adminActionCount = triageJobs.length + reviewPlans.length + attentionReviews.length;
  const adminActionLabel = isJobsLoading
    ? "Scanning live queues"
    : hasQueueWarning
      ? "Queue status unavailable"
      : adminActionCount > 0
        ? `${adminActionCount} admin decision${adminActionCount === 1 ? "" : "s"} open`
        : "Queues clear";
  const reviewPlansProfileError = isProfileServiceUnavailableMessage(reviewPlansWarning);
  const attentionProfileError = isProfileServiceUnavailableMessage(attentionWarning);

  return (
    <RequireAuth adminOnly>
      <section className="panel admin-dashboard-panel">
        <div className="section-heading admin-dashboard-heading">
          <div className="admin-dashboard-copy">
            <p className="kicker">Admin</p>
            <h1>Fight camp control room</h1>
            <p className="muted">Live generation queues, athlete risk signals, and plan-review decisions in one operator view.</p>
            <div className="admin-priority-rail" role="region" aria-label="Admin priority status">
              <span className="admin-priority-label">{adminActionLabel}</span>
              <span>{lastCheckedLabel}</span>
            </div>
          </div>
          <div className="admin-summary-grid" aria-label="Admin dashboard summary">
            <article className="status-card admin-summary-card" data-tone={activeJobs.length > 0 ? "active" : "neutral"}>
              <p className="status-label">Generating now</p>
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : activeJobs.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? "Checking jobs."
                  : `${activeAthleteCount} athlete${activeAthleteCount === 1 ? "" : "s"} in progress.`}
              </p>
            </article>
            <article className="status-card admin-summary-card" data-tone={triageJobs.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">Triage queue</p>
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : triageJobs.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? "Checking reviews."
                  : attentionReviews.length > 0
                    ? "Athlete flags open."
                    : "No flags open."}
              </p>
            </article>
            <article className="status-card admin-summary-card" data-tone={attentionReviews.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">Needs attention</p>
              <h2 className="plan-summary-title">
                {isJobsLoading
                  ? "-"
                  : reviewPlans.length > 0
                    ? reviewPlans.length
                    : isDirectoryLoading
                      ? "-"
                      : plans.length}
              </h2>
              <p className="muted">{isJobsLoading ? "Checking reviews." : "Athlete flags open."}</p>
            </article>
            <article className="status-card admin-summary-card" data-tone="neutral">
              <p className="status-label">Athletes</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : athletes.length}</h2>
              <p className="muted">{searchNeedle ? "Matches on this page." : "Accounts on this page."}</p>
            </article>
            <article className="status-card admin-summary-card" data-tone={reviewPlans.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">Plans</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : plans.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? "Checking reviews."
                  : searchNeedle
                    ? "Matches on this page."
                    : reviewPlans.length > 0
                      ? `${reviewPlans.length} held for decision.`
                      : "Generations on this page."}
              </p>
            </article>
          </div>
        </div>

        {profileWarning.show ? (
          <div className="warning-banner admin-profile-warning-banner" role="status">
            <div className="admin-profile-warning-copy">
              <strong>{profileWarning.title}</strong>
              <span>{profileWarning.body}</span>
              {profileWarning.requestId ? (
                <span className="muted admin-profile-warning-request">
                  Latest request id: {profileWarning.requestId}
                </span>
              ) : null}
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={handleRetry}
              disabled={isLoading}
            >
              {isLoading ? "Retrying..." : "Retry"}
            </button>
          </div>
        ) : null}

        {directoryDisplayError ? (
          <div className="error-banner" role="alert">
            <span>{directoryDisplayError}</span>
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
          <button
            type="button"
            className="ghost-button admin-backfill-button"
            onClick={() => void handleBackfillStructuredPlans()}
            disabled={backfillPending}
            title="Re-run structured-card conversion for legacy plans that still fall back to plain text"
          >
            {backfillPending ? "Backfilling..." : "Backfill structured cards"}
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
          ) : activeDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{activeDisplayWarning}</p>
              <p className="muted">Triage, athlete, and plan history can still be reviewed while this feed retries.</p>
            </div>
          ) : activeProfileError && activeJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">Live generation details are limited while the profile service recovers. See the notice above.</p>
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
                      <ProfileUnavailableNote unavailable={job.profile_unavailable} />
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
                    <p className="muted">Fight date: {job.request_payload_summary?.fight_date ? formatAppDate(job.request_payload_summary.fight_date) : "Not set"}</p>
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
                    <button
                      type="button"
                      className="ghost-button danger-button"
                      onClick={() => void handleCancelGenerationJob(job)}
                      disabled={cancellingJobId !== null}
                    >
                      {cancellingJobId === job.job_id ? "Cancelling..." : "Cancel generation"}
                    </button>
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
          ) : triageDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{triageDisplayWarning}</p>
              <p className="muted">Athlete accounts and plan history can still be reviewed while the queue retries.</p>
            </div>
          ) : triageProfileError && triageJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">Triage details are limited while the profile service recovers. See the notice above.</p>
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
                      <ProfileUnavailableNote unavailable={job.profile_unavailable} />
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
                    <p className="muted">Fight date: {job.request_payload_summary.fight_date ? formatAppDate(job.request_payload_summary.fight_date) : "Not set"}</p>
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

        <article className="list-card admin-review-plans-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">Held &amp; review plans</p>
              <h2>Plans awaiting an admin decision</h2>
            </div>
            <span className="badge">{isJobsLoading ? "Checking" : `${reviewPlans.length} held`}</span>
          </div>

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">Loading held and review plans...</p>
            </div>
          ) : reviewPlansDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{reviewPlansDisplayWarning}</p>
              <p className="muted">Live jobs, triage, and athlete records can still be reviewed while this queue retries.</p>
            </div>
          ) : reviewPlansProfileError && reviewPlans.length === 0 ? (
            <div className="support-panel">
              <p className="muted">Held plan details are limited while the profile service recovers. See the notice above.</p>
            </div>
          ) : reviewPlans.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">Clear</p>
              <h3 className="form-section-title">No plans are held for review.</h3>
              <p className="muted">Held, blocked, and review-required plans appear here so they stay visible even when athlete details are unavailable.</p>
            </div>
          ) : (
            <div className="plans-grid admin-queue-grid">
              {reviewPlans.map((plan) => (
                <article key={plan.plan_id} className="plan-card admin-triage-card">
                  <div className="plan-card-header">
                    <div>
                      <Link href={`/plans/${plan.plan_id}`}>
                        <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                      </Link>
                      <p className="muted">{plan.athlete_email || plan.athlete_id || "No athlete email"}</p>
                      <ProfileUnavailableNote unavailable={plan.profile_unavailable} />
                    </div>
                    <span className="badge">{plan.status}</span>
                  </div>
                  <div className="admin-job-meta">
                    <span>Created {formatDateTime(plan.created_at)}</span>
                    <span>Plan {plan.plan_id}</span>
                  </div>
                  <div className="plan-card-actions">
                    {plan.athlete_id ? (
                      <Link href={`/admin/athletes/${plan.athlete_id}`} className="ghost-button">
                        Open athlete
                      </Link>
                    ) : null}
                    <Link href={`/plans/${plan.plan_id}`} className="cta">
                      Review plan
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="list-card admin-attention-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">Athlete attention queue</p>
              <h2>Needs attention</h2>
            </div>
            <span className="badge">{isJobsLoading ? "Checking" : `${attentionReviews.length} open`}</span>
          </div>

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">Loading the attention queue...</p>
            </div>
          ) : attentionDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{attentionDisplayWarning}</p>
            </div>
          ) : attentionProfileError && attentionReviews.length === 0 ? (
            <div className="support-panel">
              <p className="muted">Attention queue details are limited while the profile service recovers. See the notice above.</p>
            </div>
          ) : attentionReviews.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">Clear</p>
              <h3 className="form-section-title">No athletes are flagged for review.</h3>
              <p className="muted">
                Injury reports, sustained high fatigue, and repeated missed sessions land here automatically from daily check-ins and session logs.
              </p>
            </div>
          ) : (
            <div className="plans-grid admin-queue-grid">
              {attentionReviews.map((review) => (
                <article key={review.id} className="plan-card admin-triage-card">
                  <div className="plan-card-header">
                    <div>
                      <h3 className="plan-card-title">{review.athlete_name || review.athlete_email || review.athlete_id}</h3>
                      <p className="muted">{review.athlete_email || review.athlete_id}</p>
                    </div>
                    <span className="badge">{review.injury_flag_id ? "Injury flag" : "Review"}</span>
                  </div>
                  <p className="muted">{review.reason}</p>
                  <div className="admin-job-meta">
                    <span>Flagged {formatDateTime(review.created_at)}</span>
                  </div>
                  <div className="plan-card-actions">
                    <Link href={`/admin/athletes/${review.athlete_id}`} className="ghost-button">
                      Open athlete
                    </Link>
                    <button
                      type="button"
                      className="cta"
                      onClick={() => void handleResolveReview(review.id)}
                      disabled={resolvingReviewId !== null}
                    >
                      {resolvingReviewId === review.id ? "Resolving..." : "Mark resolved"}
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
              <div>
                <p className="kicker">Plans</p>
                <h2>{searchNeedle ? "Matching generations" : "Latest generations"}</h2>
              </div>
              {archivedPlanIds.length ? (
                <span className="badge">{archivedPlanIds.length} archived</span>
              ) : null}
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
                {archivedPlanIds.length ? (
                  <div className="admin-athlete-plan-bulkbar admin-plan-cleanup-bar">
                    <label className="admin-athlete-plan-select">
                      <input
                        type="checkbox"
                        checked={allArchivedPlansSelected}
                        onChange={toggleAllArchivedPlans}
                        disabled={bulkDeletingPlans}
                        aria-label="Select archived plans on this page"
                      />
                      <span className="muted">
                        {selectedArchivedCount > 0
                          ? `${selectedArchivedCount} archived selected`
                          : `Select archived (${archivedPlanIds.length})`}
                      </span>
                    </label>
                    <button
                      type="button"
                      className="ghost-button danger-button"
                      onClick={() => void handleBulkDeleteArchivedPlans()}
                      disabled={selectedArchivedCount === 0 || bulkDeletingPlans}
                    >
                      {bulkDeletingPlans
                        ? "Deleting..."
                        : `Delete archived${selectedArchivedCount ? ` (${selectedArchivedCount})` : ""}`}
                    </button>
                  </div>
                ) : null}
                <div className="plans-grid">
                  {plans.map((plan) => (
                    <article key={plan.plan_id} className="plan-card">
                      <div className="plan-card-header">
                        <div className="admin-plan-title-row">
                          {isArchivedPlan(plan) ? (
                            <label className="admin-athlete-plan-select" aria-label={`Select ${getPlanDisplayName(plan)}`}>
                              <input
                                type="checkbox"
                                checked={selectedArchivedIds.includes(plan.plan_id)}
                                onChange={() => toggleArchivedPlan(plan.plan_id)}
                                disabled={bulkDeletingPlans}
                              />
                            </label>
                          ) : null}
                          <div>
                            <Link href={`/plans/${plan.plan_id}`}>
                              <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                            </Link>
                            <p className="muted">{plan.athlete_email}</p>
                          </div>
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
