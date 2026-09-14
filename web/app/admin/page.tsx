"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { AdminFeedbackPanel } from "@/components/admin-feedback-panel";
import { formatAppDate, formatAppDateTime } from "@/lib/date-format";
import {
  approveAdminAthlete,
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
import { useTranslations as useAppTranslations } from "next-intl";

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
    const appText = useAppTranslations("AppText");
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
  const [approvingAthleteId, setApprovingAthleteId] = useState<string | null>(null);
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

    const loadDirectory = async () => {
      const loadErrors: string[] = [];

      try {
        try {
          const athletesResult = await listAdminAthletes(token, {
            q: searchNeedle,
            limit: DIRECTORY_PAGE_SIZE,
            offset: athletesOffset,
          });
          if (!active) return;
          setAthletes(athletesResult);
          setAthletesHasMore(athletesResult.length === DIRECTORY_PAGE_SIZE);
        } catch (athletesError) {
          if (!active) return;
          loadErrors.push(getErrorMessage(athletesError, "Unable to load athlete accounts."));
        }

        try {
          const plansResult = await listAdminPlans(token, {
            q: searchNeedle,
            limit: DIRECTORY_PAGE_SIZE,
            offset: plansOffset,
          });
          if (!active) return;
          setPlans(plansResult);
          setPlansHasMore(plansResult.length === DIRECTORY_PAGE_SIZE);
        } catch (plansError) {
          if (!active) return;
          loadErrors.push(getErrorMessage(plansError, "Unable to load plan history."));
        }

        setError(loadErrors.length ? loadErrors.join(" ") : null);
      } catch (adminError) {
        if (!active) return;
        setError(adminError instanceof Error ? adminError.message : "Unable to load admin data.");
      } finally {
        if (active) {
          setIsDirectoryLoading(false);
        }
      }
    };

    void loadDirectory();

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
    let jobLoadInFlight = false;

    const loadJobs = async (isInitial: boolean) => {
      if (jobLoadInFlight) return;
      jobLoadInFlight = true;
      if (isInitial) {
        setIsJobsLoading(true);
      }

      try {
        try {
          const activeResult = await listAdminActiveGenerationJobs(token);
          if (!active) return;
          setActiveJobs(activeResult);
          setActiveWarning(null);
        } catch (activeError) {
          if (!active) return;
          // On a transient poll failure keep the last good snapshot rather
          // than blanking the live monitor; only clear it on first load.
          if (isInitial) setActiveJobs([]);
          setActiveWarning(getErrorMessage(activeError, "Unable to load active generation jobs."));
        }

        try {
          const triageResult = await listAdminTriageGenerationJobs(token);
          if (!active) return;
          setTriageJobs(triageResult);
          setTriageWarning(null);
        } catch (triageError) {
          if (!active) return;
          if (isInitial) setTriageJobs([]);
          setTriageWarning(getErrorMessage(triageError, "Unable to load suspended triage jobs."));
        }

        try {
          const reviewPlansResult = await listAdminReviewPlans(token);
          if (!active) return;
          setReviewPlans(reviewPlansResult);
          setReviewPlansWarning(null);
        } catch (reviewPlansError) {
          if (!active) return;
          if (isInitial) setReviewPlans([]);
          setReviewPlansWarning(getErrorMessage(reviewPlansError, "Unable to load held/review plans."));
        }

        try {
          const reviewsResult = await listAdminReviews(token, "pending");
          if (!active) return;
          setAttentionReviews(reviewsResult);
          setAttentionWarning(null);
        } catch (reviewsError) {
          if (!active) return;
          if (isInitial) setAttentionReviews([]);
          setAttentionWarning(getErrorMessage(reviewsError, "Unable to load the athlete attention queue."));
        }

        setLastCheckedAt(new Date().toISOString());
      } finally {
        jobLoadInFlight = false;
        if (active && isInitial) {
          setIsJobsLoading(false);
        }
      }
    };

    void loadJobs(true);
    const timer = setInterval(() => void loadJobs(false), ACTIVE_JOBS_POLL_INTERVAL_MS);

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

  async function handleApproveAthlete(athleteId: string) {
    if (!session?.access_token || approvingAthleteId) return;
    setApprovingAthleteId(athleteId);
    setError(null);
    setMessage(null);
    try {
      const approved = await approveAdminAthlete(session.access_token, athleteId);
      setAthletes((current) =>
        current.map((athlete) => athlete.athlete_id === athleteId ? approved : athlete),
      );
      setMessage(`${approved.full_name || approved.email} approved.`);
    } catch (approveError) {
      setError(approveError instanceof Error ? approveError.message : "Failed to approve account.");
    } finally {
      setApprovingAthleteId(null);
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
      setError(deleteError instanceof Error ? deleteError.message : appText("text_6ba78c22f62b"));
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
            <p className="kicker">{appText("text_c1c224b03cd9")}</p>
            <h1>{appText("text_eefe09120c62")}</h1>
            <p className="muted">{appText("text_aa142be234b2")}</p>
            <div className="admin-priority-rail" role="region" aria-label={appText("text_fe3d5f57225d")}>
              <span className="admin-priority-label">{adminActionLabel}</span>
              <span>{lastCheckedLabel}</span>
            </div>
          </div>
          <div className="admin-summary-grid" aria-label={appText("text_0e553cdb4574")}>
            <article className="status-card admin-summary-card" data-tone={activeJobs.length > 0 ? "active" : "neutral"}>
              <p className="status-label">{appText("text_6ee8d88ca388")}</p>
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : activeJobs.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? appText("text_ce9d8576e3c1")
                  : `${activeAthleteCount} athlete${activeAthleteCount === 1 ? "" : "s"} in progress.`}
              </p>
            </article>
            <article className="status-card admin-summary-card" data-tone={triageJobs.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">{appText("text_7ac2fc7dd4db")}</p>
              <h2 className="plan-summary-title">{isJobsLoading ? "-" : triageJobs.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? appText("text_48ccb3331068")
                  : attentionReviews.length > 0
                    ? appText("text_99c3a2ad6bdf")
                    : appText("text_490210e197cb")}
              </p>
            </article>
            <article className="status-card admin-summary-card" data-tone={attentionReviews.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">{appText("text_c1ebc7817870")}</p>
              <h2 className="plan-summary-title">
                {isJobsLoading
                  ? "-"
                  : reviewPlans.length > 0
                    ? reviewPlans.length
                    : isDirectoryLoading
                      ? "-"
                      : plans.length}
              </h2>
              <p className="muted">{isJobsLoading ? appText("text_48ccb3331068") : appText("text_99c3a2ad6bdf")}</p>
            </article>
            <article className="status-card admin-summary-card" data-tone="neutral">
              <p className="status-label">{appText("text_39822ba817e8")}</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : athletes.length}</h2>
              <p className="muted">{searchNeedle ? appText("text_f074b0653624") : appText("text_a065830a1fda")}</p>
            </article>
            <article className="status-card admin-summary-card" data-tone={reviewPlans.length > 0 ? "danger" : "neutral"}>
              <p className="status-label">{appText("text_dfe8b2f0de26")}</p>
              <h2 className="plan-summary-title">{isDirectoryLoading ? "-" : plans.length}</h2>
              <p className="muted">
                {isJobsLoading
                  ? appText("text_48ccb3331068")
                  : searchNeedle
                    ? appText("text_f074b0653624")
                    : reviewPlans.length > 0
                      ? `${reviewPlans.length} held for decision.`
                      : appText("text_5520412c3acd")}
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
                  {appText("text_9a4fca4d2609")}{profileWarning.requestId}
                </span>
              ) : null}
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={handleRetry}
              disabled={isLoading}
            >
              {isLoading ? appText("text_84a657bcf3d9") : appText("text_942087cc2d41")}
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
              {isLoading ? appText("text_84a657bcf3d9") : appText("text_d8b8392e2c54")}
            </button>
          </div>
        ) : null}

        {message ? <div className="success-banner">{message}</div> : null}

        <div className="admin-toolbar">
          <div className="field admin-search-field">
            <label htmlFor="adminSearch">{appText("text_3b9c38abb843")}</label>
            <input
              id="adminSearch"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={appText("text_ceac7db32c33")}
            />
          </div>
          <button
            type="button"
            className="ghost-button admin-refresh-button"
            onClick={handleRetry}
            disabled={isLoading}
          >
            {isLoading ? appText("text_69d2daed978a") : appText("text_0e9161011702")}
          </button>
          <button
            type="button"
            className="ghost-button admin-backfill-button"
            onClick={() => void handleBackfillStructuredPlans()}
            disabled={backfillPending}
            title={appText("text_480a1db80d35")}
          >
            {backfillPending ? appText("text_70ce293d99de") : appText("text_e35b8924799e")}
          </button>
        </div>

        {token ? <AdminFeedbackPanel token={token} reloadKey={reloadKey} /> : null}

        <article className="list-card admin-active-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">{appText("text_6b91d0fe2435")}</p>
              <h2>{appText("text_873479fff5d0")}</h2>
              <p className="muted admin-panel-subtext">{lastCheckedLabel}</p>
            </div>
            <span className="badge">
              {isJobsLoading
                ? appText("text_0dfe1d63c9d8")
                : searchNeedle
                  ? `${filteredActiveJobs.length}/${activeJobs.length} active`
                  : `${activeJobs.length} active`}
            </span>
          </div>

          {!isJobsLoading ? (
            <div className="admin-active-summary" aria-label={appText("text_98a9847e197c")}>
              <span>{appText("text_f4ccae29e1bb")}{activeJobStates.running}</span>
              <span>{appText("text_661ff40a07e0")}{activeJobStates.queued}</span>
              <span>{appText("text_40c9e59c5e15")}{activeJobStates.stale}</span>
            </div>
          ) : null}

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">{appText("text_33f3c644be99")}</p>
            </div>
          ) : activeDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{activeDisplayWarning}</p>
              <p className="muted">{appText("text_b545cc83b4fb")}</p>
            </div>
          ) : activeProfileError && activeJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">{appText("text_e732c55e73b7")}</p>
            </div>
          ) : activeJobs.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">{appText("text_ab0171ca0494")}</p>
              <h3 className="form-section-title">{appText("text_cbcc62bf9b3e")}</h3>
              <p className="muted">{appText("text_0252b6587367")}</p>
            </div>
          ) : filteredActiveJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">{appText("text_aa6872336698")}</p>
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
                      <p className="muted">{job.athlete_email || job.athlete_id || appText("text_708bc3861e4b")}</p>
                      <ProfileUnavailableNote unavailable={job.profile_unavailable} />
                    </div>
                    <span className="badge">{getJobStatusLabel(job)}</span>
                  </div>
                  <div className="admin-active-progress" aria-label={`${getJobStatusLabel(job)} progress`}>
                    <span style={{ width: `${getActiveJobProgress(job)}%` }} />
                  </div>
                  <div className="admin-job-meta">
                    <span>{appText("text_d70b9e24bca2")}{formatDateTime(job.created_at)}</span>
                    <span>{appText("text_ecbc89cd37a0")}{formatDateTime(job.started_at)}</span>
                    <span>{appText("text_9df89427a7c8")}{formatDateTime(job.heartbeat_at)}</span>
                    <span>{appText("text_0e570ca6fabe")}{formatJobSource(job.source)}</span>
                  </div>
                  <div className="admin-job-summary">
                    <ProfileRefreshWarningBanner job={job} />
                    {job.is_stale ? <p className="error-text">{job.stale_reason || appText("text_fc6ce88b89a0")}</p> : null}
                    <p className="muted">{appText("text_f65bea824e6f")}{job.request_payload_summary?.fight_date ? formatAppDate(job.request_payload_summary.fight_date) : appText("text_4895f73177ab")}</p>
                    <p className="muted">{appText("text_9a5649a42cb2")}{job.request_payload_summary?.fight_format || appText("text_4895f73177ab")}</p>
                    <p className="muted">{appText("text_d5c7aa27cc62")}{joinOrDash(job.request_payload_summary?.goals)}</p>
                  </div>
                  <div className="plan-card-actions">
                    {job.athlete_id ? (
                      <Link href={`/admin/athletes/${job.athlete_id}`} className="ghost-button">
                        {appText("text_06f0029eb16e")}</Link>
                    ) : null}
                    {job.plan_id ? (
                      <Link href={`/plans/${job.plan_id}`} className="ghost-button">
                        {appText("text_9e70b18d5255")}</Link>
                    ) : null}
                    <button
                      type="button"
                      className="ghost-button danger-button"
                      onClick={() => void handleCancelGenerationJob(job)}
                      disabled={cancellingJobId !== null}
                    >
                      {cancellingJobId === job.job_id ? appText("text_7b26131098bb") : appText("text_12ad4ee6d948")}
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
              <p className="kicker">{appText("text_2e894e6185b9")}</p>
              <h2>{appText("text_3a62ddc41ae5")}</h2>
            </div>
            <span className="badge">{isJobsLoading ? appText("text_0dfe1d63c9d8") : `${triageJobs.length} open`}</span>
          </div>

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">{appText("text_1c6cd18bb32b")}</p>
            </div>
          ) : triageDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{triageDisplayWarning}</p>
              <p className="muted">{appText("text_a9223657b71b")}</p>
            </div>
          ) : triageProfileError && triageJobs.length === 0 ? (
            <div className="support-panel">
              <p className="muted">{appText("text_87123667aaba")}</p>
            </div>
          ) : triageJobs.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">{appText("text_83b12c2216ef")}</p>
              <h3 className="form-section-title">{appText("text_be46e7890b1b")}</h3>
              <p className="muted">{appText("text_cb5807426976")}</p>
            </div>
          ) : (
            <div className="plans-grid admin-queue-grid">
              {triageJobs.map((job) => (
                <article key={job.job_id} className="plan-card admin-triage-card">
                  <div className="plan-card-header">
                    <div>
                      <h3 className="plan-card-title">{getJobDisplayName(job)}</h3>
                      <p className="muted">{job.athlete_email || job.athlete_id || appText("text_708bc3861e4b")}</p>
                      <ProfileUnavailableNote unavailable={job.profile_unavailable} />
                    </div>
                    <span className="badge">{appText("text_17d48234f771")}</span>
                  </div>
                  <p className="muted">
                    {job.stage2_status || "triage_blocked"} {appText("text_a0840a28194f")}</p>
                  <div className="admin-job-meta">
                    <span>{appText("text_d70b9e24bca2")}{formatDateTime(job.created_at)}</span>
                    <span>{appText("text_0e570ca6fabe")}{job.source || "unknown"}</span>
                    <span>{appText("text_ad617a0fdd57")}{job.job_id}</span>
                  </div>
                  <div className="admin-job-summary">
                    <ProfileRefreshWarningBanner job={job} />
                    <p className="muted">{appText("text_f65bea824e6f")}{job.request_payload_summary.fight_date ? formatAppDate(job.request_payload_summary.fight_date) : appText("text_4895f73177ab")}</p>
                    <p className="muted">{appText("text_d5c7aa27cc62")}{joinOrDash(job.request_payload_summary.goals)}</p>
                    <p className="muted">{appText("text_0cfd4ac7baa7")}{joinOrDash(job.request_payload_summary.injuries)}</p>
                  </div>
                  <div className="plan-card-actions">
                    {job.athlete_id ? (
                      <Link href={`/admin/athletes/${job.athlete_id}`} className="ghost-button">
                        {appText("text_06f0029eb16e")}</Link>
                    ) : null}
                    <button
                      type="button"
                      className="cta"
                      onClick={() => void handleApproveAndResumeJob(job.job_id)}
                      disabled={resumingJobId !== null}
                    >
                      {resumingJobId === job.job_id ? appText("text_cee0e61bdf8c") : appText("text_e2a9cd45af93")}
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
              <p className="kicker">{appText("text_2223250bbc7b")}</p>
              <h2>{appText("text_b2ecf6c9c84e")}</h2>
            </div>
            <span className="badge">{isJobsLoading ? appText("text_0dfe1d63c9d8") : `${reviewPlans.length} held`}</span>
          </div>

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">{appText("text_bee03cdbc79e")}</p>
            </div>
          ) : reviewPlansDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{reviewPlansDisplayWarning}</p>
              <p className="muted">{appText("text_894794ec6839")}</p>
            </div>
          ) : reviewPlansProfileError && reviewPlans.length === 0 ? (
            <div className="support-panel">
              <p className="muted">{appText("text_05e05f824500")}</p>
            </div>
          ) : reviewPlans.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">{appText("text_83b12c2216ef")}</p>
              <h3 className="form-section-title">{appText("text_7f159ddf9942")}</h3>
              <p className="muted">{appText("text_69bbe846bd2a")}</p>
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
                      <p className="muted">{plan.athlete_email || plan.athlete_id || appText("text_708bc3861e4b")}</p>
                      <ProfileUnavailableNote unavailable={plan.profile_unavailable} />
                    </div>
                    <span className="badge">{plan.status}</span>
                  </div>
                  <div className="admin-job-meta">
                    <span>{appText("text_d70b9e24bca2")}{formatDateTime(plan.created_at)}</span>
                    <span>{appText("text_fa8ed0bdabdd")}{plan.plan_id}</span>
                  </div>
                  <div className="plan-card-actions">
                    {plan.athlete_id ? (
                      <Link href={`/admin/athletes/${plan.athlete_id}`} className="ghost-button">
                        {appText("text_06f0029eb16e")}</Link>
                    ) : null}
                    <Link href={`/plans/${plan.plan_id}`} className="cta">
                      {appText("text_71146ca693e0")}</Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </article>

        <article className="list-card admin-attention-panel">
          <div className="form-section-header">
            <div>
              <p className="kicker">{appText("text_2ace7fa7443d")}</p>
              <h2>{appText("text_c1ebc7817870")}</h2>
            </div>
            <span className="badge">{isJobsLoading ? appText("text_0dfe1d63c9d8") : `${attentionReviews.length} open`}</span>
          </div>

          {isJobsLoading ? (
            <div className="support-panel">
              <p className="muted">{appText("text_bee79974b1c1")}</p>
            </div>
          ) : attentionDisplayWarning ? (
            <div className="support-panel">
              <p className="error-text">{attentionDisplayWarning}</p>
            </div>
          ) : attentionProfileError && attentionReviews.length === 0 ? (
            <div className="support-panel">
              <p className="muted">{appText("text_130e269cbd6f")}</p>
            </div>
          ) : attentionReviews.length === 0 ? (
            <div className="support-panel support-panel-success">
              <p className="kicker">{appText("text_83b12c2216ef")}</p>
              <h3 className="form-section-title">{appText("text_282b990744bf")}</h3>
              <p className="muted">
                {appText("text_204323f0e5e9")}</p>
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
                    <span className="badge">{review.injury_flag_id ? appText("text_a3c3593a208d") : appText("text_aff0766a5290")}</span>
                  </div>
                  <p className="muted">{review.reason}</p>
                  <div className="admin-job-meta">
                    <span>{appText("text_2f1978c6166e")}{formatDateTime(review.created_at)}</span>
                  </div>
                  <div className="plan-card-actions">
                    <Link href={`/admin/athletes/${review.athlete_id}`} className="ghost-button">
                      {appText("text_06f0029eb16e")}</Link>
                    <button
                      type="button"
                      className="cta"
                      onClick={() => void handleResolveReview(review.id)}
                      disabled={resolvingReviewId !== null}
                    >
                      {resolvingReviewId === review.id ? appText("text_0660108e0971") : appText("text_d6d8eeddd835")}
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
              <p className="kicker">{appText("text_39822ba817e8")}</p>
              <h2>{searchNeedle ? appText("text_1afdc8471e56") : appText("text_0ed9feb354ec")}</h2>
            </div>

            {isDirectoryLoading ? (
              <div className="support-panel">
                <p className="muted">{appText("text_08197549f43a")}</p>
              </div>
            ) : athletes.length === 0 && searchNeedle ? (
              <div className="support-panel">
                <p className="muted">{appText("text_9da02817a9d1")}</p>
              </div>
            ) : athletes.length === 0 && athletesOffset > 0 ? (
              <div className="support-panel">
                <p className="muted">{appText("text_0f4d4e53fcc8")}</p>
              </div>
            ) : athletes.length === 0 ? (
              <EmptyState
                eyebrow={appText("text_3cdb3123b86a")}
                title={appText("text_463678ca125d")}
                description={appText("text_53d160f2a574")}
                example={appText("text_24fdb99caa1c")}
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
                        <span className="badge">
                          {athlete.access_status === "pending"
                            ? appText("text_9928dd82f38f")
                            : `${athlete.plan_count} plan${athlete.plan_count === 1 ? "" : "s"}`}
                        </span>
                      </div>
                      <p className="muted">{appText("text_d70b9e24bca2")}{formatDateTime(athlete.created_at)}</p>
                      <div className="plan-card-actions">
                        {athlete.access_status === "pending" ? (
                          <button
                            type="button"
                            className="cta"
                            onClick={() => void handleApproveAthlete(athlete.athlete_id)}
                            disabled={approvingAthleteId !== null}
                          >
                            {approvingAthleteId === athlete.athlete_id ? appText("text_e99dcb0a97a2") : appText("text_3c04b868ea53")}
                          </button>
                        ) : null}
                        <Link href={`/admin/athletes/${athlete.athlete_id}`} className="ghost-button">
                          {appText("text_d4788f256f73")}</Link>
                      </div>
                    </article>
                  ))}
                </div>
                <div className="admin-pager" aria-label={appText("text_1e564ae877d1")}>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToAthletesPage(-1)}
                    disabled={isDirectoryLoading || athletesOffset === 0}
                  >
                    {appText("text_a57b08a480b8")}</button>
                  <span className="muted">{appText("text_0a30a815d67d")}{athletesPage}</span>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToAthletesPage(1)}
                    disabled={isDirectoryLoading || !athletesHasMore}
                  >
                    {appText("text_1ff57a29d7c9")}</button>
                </div>
              </>
            )}
          </article>

          <article className="list-card">
            <div className="form-section-header">
              <div>
                <p className="kicker">{appText("text_dfe8b2f0de26")}</p>
                <h2>{searchNeedle ? appText("text_dd36083a5c53") : appText("text_7f55bd53ad7d")}</h2>
              </div>
              {archivedPlanIds.length ? (
                <span className="badge">{archivedPlanIds.length} {appText("text_dd9e881230eb")}</span>
              ) : null}
            </div>

            {isDirectoryLoading ? (
              <div className="support-panel">
                <p className="muted">{appText("text_387dfae0da1c")}</p>
              </div>
            ) : plans.length === 0 && searchNeedle ? (
              <div className="support-panel">
                <p className="muted">{appText("text_73bab59294e0")}</p>
              </div>
            ) : plans.length === 0 && plansOffset > 0 ? (
              <div className="support-panel">
                <p className="muted">{appText("text_218a4c74d949")}</p>
              </div>
            ) : plans.length === 0 ? (
              <EmptyState
                eyebrow={appText("text_09af61b7dc6a")}
                title={appText("text_3ee77563f2fc")}
                description={appText("text_6a8123650372")}
                example={appText("text_c1bea7251e80")}
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
                        aria-label={appText("text_cf81d197adbb")}
                      />
                      <span className="muted">
                        {selectedArchivedCount > 0
                          ? appText("text_62ee2852ec4e", { count: selectedArchivedCount })
                          : appText("text_ef276ee1d896", { count: archivedPlanIds.length })}
                      </span>
                    </label>
                    <button
                      type="button"
                      className="ghost-button danger-button"
                      onClick={() => void handleBulkDeleteArchivedPlans()}
                      disabled={selectedArchivedCount === 0 || bulkDeletingPlans}
                    >
                      {bulkDeletingPlans
                        ? appText("text_685ecb984ac2")
                        : selectedArchivedCount
                          ? appText("text_ba8345b330fa", { count: selectedArchivedCount })
                          : appText("text_b6d1e0fbd54f")}
                    </button>
                  </div>
                ) : null}
                <div className="plans-grid">
                  {plans.map((plan) => (
                    <article key={plan.plan_id} className="plan-card">
                      <div className="plan-card-header">
                        <div className="admin-plan-title-row">
                          {isArchivedPlan(plan) ? (
                            <label className="admin-athlete-plan-select" aria-label={appText("text_cbe2f0672d5f", { name: getPlanDisplayName(plan) })}>
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
                      <p className="muted">{appText("text_d70b9e24bca2")}{formatDateTime(plan.created_at)}</p>
                      <div className="plan-card-actions">
                        <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
                          {appText("text_9e70b18d5255")}</Link>
                      </div>
                    </article>
                  ))}
                </div>
                <div className="admin-pager" aria-label={appText("text_dc11f2307b6e")}>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToPlansPage(-1)}
                    disabled={isDirectoryLoading || plansOffset === 0}
                  >
                    {appText("text_a57b08a480b8")}</button>
                  <span className="muted">{appText("text_0a30a815d67d")}{plansPage}</span>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => goToPlansPage(1)}
                    disabled={isDirectoryLoading || !plansHasMore}
                  >
                    {appText("text_1ff57a29d7c9")}</button>
                </div>
              </>
            )}
          </article>
        </div>
      </section>
    </RequireAuth>
  );
}
