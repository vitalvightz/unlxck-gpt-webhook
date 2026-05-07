"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanHistoryRowSkeleton, PlansFeaturedSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { deletePlan, listPlans, renamePlan } from "@/lib/api";
import {
  formatPlanFightDate,
  formatPlanStatus,
  formatPlanTimestamp,
  getFeaturedPlanTitle,
  getPlanDisplayName,
  getPlanStyleSummary,
} from "@/lib/plan-format";
import type { PlanSummary } from "@/lib/types";

function getRenameDraftValue(plan: PlanSummary): string {
  return plan.plan_name?.trim() || plan.fight_date || "";
}

function PlanCard({
  plan,
  accessToken,
  onPlanDeleted,
  onPlanRenamed,
  variant = "history",
}: {
  plan: PlanSummary;
  accessToken: string | null;
  onPlanDeleted: (planId: string) => void;
  onPlanRenamed: (updatedPlan: PlanSummary) => void;
  variant?: "featured" | "history";
}) {
  const { showToast } = useToast();
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState(() => getRenameDraftValue(plan));
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const planTitle = getPlanDisplayName(plan);
  const featuredTitle = getFeaturedPlanTitle(plan);
  const fightDateLabel = formatPlanFightDate(plan.fight_date);
  const createdLabel = formatPlanTimestamp(plan.created_at);
  const styleSummary = getPlanStyleSummary(plan);
  const statusLabel = formatPlanStatus(plan.status);
  const isActionPending = pendingAction !== null;
  const renameInputId = `rename-plan-${plan.plan_id}`;

  useEffect(() => {
    if (!isRenaming) {
      setRenameDraft(getRenameDraftValue(plan));
      return;
    }

    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [isRenaming, plan.fight_date, plan.plan_name]);

  useEffect(() => {
    if (!isDeleteConfirmOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && pendingAction !== "delete") {
        setIsDeleteConfirmOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isDeleteConfirmOpen, pendingAction]);

  function handleRenameStart() {
    setMessage(null);
    setError(null);
    setRenameDraft(getRenameDraftValue(plan));
    setIsRenaming(true);
  }

  function handleRenameCancel() {
    if (isActionPending) {
      return;
    }

    setError(null);
    setRenameDraft(getRenameDraftValue(plan));
    setIsRenaming(false);
  }

  async function handleRenameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!accessToken) {
      setError("Session missing. Please sign in again.");
      return;
    }

    const currentName = plan.plan_name?.trim() || "";
    const normalizedName = renameDraft.trim();
    if (!normalizedName) {
      setError("Plan name cannot be empty.");
      return;
    }
    if (normalizedName === currentName) {
      setError(null);
      setIsRenaming(false);
      return;
    }

    setPendingAction("rename");
    setError(null);
    setMessage(null);
    try {
      const updatedPlan = await renamePlan(accessToken, plan.plan_id, normalizedName);
      onPlanRenamed(updatedPlan);
      showToast("Plan renamed.", { tone: "success" });
      setIsRenaming(false);
    } catch (renameError) {
      const errorMessage = renameError instanceof Error ? renameError.message : "Unable to rename this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError("Connection issue - the operation will retry automatically. If it continues to fail, please check your internet connection and try again.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setPendingAction(null);
    }
  }

  function handleDeleteRequest() {
    setMessage(null);
    setError(null);
    setIsDeleteConfirmOpen(true);
  }

  function handleDeleteDismiss() {
    if (pendingAction === "delete") {
      return;
    }

    setIsDeleteConfirmOpen(false);
  }

  async function handleDeleteConfirm() {
    if (!accessToken) {
      setError("Session missing. Please sign in again.");
      return;
    }

    setPendingAction("delete");
    setError(null);
    setMessage(null);
    try {
      await deletePlan(accessToken, plan.plan_id);
      setIsDeleteConfirmOpen(false);
      onPlanDeleted(plan.plan_id);
      showToast(`Deleted ${getPlanDisplayName(plan)}.`, { tone: "success" });
    } catch (deleteError) {
      const errorMessage = deleteError instanceof Error ? deleteError.message : "Unable to delete this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError("Connection issue - the operation will retry automatically. If it continues to fail, please check your internet connection and try again.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setPendingAction(null);
    }
  }

  const actionButtons = (
    <>
      <Link href={`/plans/${plan.plan_id}`} className={variant === "featured" ? "cta plans-featured-primary-action" : "ghost-button"}>
        Open plan
      </Link>
      <button type="button" className="ghost-button" onClick={handleRenameStart} disabled={isActionPending || isRenaming}>
        {pendingAction === "rename" ? "Saving..." : isRenaming ? "Editing name" : "Rename"}
      </button>
      <button type="button" className="ghost-button danger-button" onClick={handleDeleteRequest} disabled={isActionPending || isRenaming}>
        {pendingAction === "delete" ? "Deleting..." : "Delete"}
      </button>
    </>
  );

  const inlineRenameForm = isRenaming ? (
    <form className="plan-inline-rename" onSubmit={handleRenameSubmit}>
      <label className="plan-inline-rename-label" htmlFor={renameInputId}>
        Rename plan
      </label>
      <div className="plan-inline-rename-row">
        <input
          ref={renameInputRef}
          id={renameInputId}
          value={renameDraft}
          onChange={(event) => setRenameDraft(event.target.value)}
          className="plan-inline-rename-input"
          disabled={isActionPending}
          maxLength={120}
        />
        <div className="plan-inline-rename-actions">
          <button type="submit" className="secondary-button" disabled={isActionPending}>
            {pendingAction === "rename" ? "Saving..." : "Save"}
          </button>
          <button type="button" className="ghost-button" onClick={handleRenameCancel} disabled={isActionPending}>
            Cancel
          </button>
        </div>
      </div>
    </form>
  ) : null;

  const deleteConfirmationModal = isDeleteConfirmOpen && typeof document !== "undefined"
    ? createPortal(
      <div className="plan-dialog-backdrop" role="presentation" onClick={handleDeleteDismiss}>
        <div
          className="plan-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`delete-plan-title-${plan.plan_id}`}
          aria-describedby={`delete-plan-body-${plan.plan_id}`}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="plan-dialog-header">
            <p className="kicker">Delete plan</p>
            <h2 id={`delete-plan-title-${plan.plan_id}`} className="plan-dialog-title">
              Remove {getPlanDisplayName(plan)}?
            </h2>
          </div>
          <p id={`delete-plan-body-${plan.plan_id}`} className="muted">
            This deletes the saved plan and its export links from your account. This action cannot be undone.
          </p>
          {error ? <div className="error-banner">{error}</div> : null}
          <div className="plan-dialog-actions">
            <button type="button" className="ghost-button" onClick={handleDeleteDismiss} disabled={pendingAction === "delete"}>
              Cancel
            </button>
            <button type="button" className="secondary-button danger-button" onClick={handleDeleteConfirm} disabled={pendingAction === "delete"}>
              {pendingAction === "delete" ? "Deleting..." : "Delete plan"}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  if (variant === "featured") {
    return (
      <>
        <article className="list-card plan-card plans-featured-card">
          <div className="plans-featured-topline">
            <div className="plans-featured-kicker">
              <p className="kicker">Latest saved plan</p>
              <p className="muted">Created {createdLabel}</p>
            </div>
            <span className="badge">{statusLabel}</span>
          </div>
          <div className="plans-featured-main">
            <div className="plans-featured-copy">
              <p className="label">Fight date</p>
              <p className="plans-featured-fight-date">{fightDateLabel}</p>
              <Link href={`/plans/${plan.plan_id}`}>
                <h2 className="plan-card-title plans-featured-title">{featuredTitle}</h2>
              </Link>
              <p className="muted plans-featured-summary">Reopen, export, or refine the latest camp without digging through the archive.</p>
              {inlineRenameForm}
              <div className="plans-featured-footer">
                <div className="plans-featured-accent" aria-hidden="true">
                  <span />
                </div>
                <div className="plan-card-actions plans-featured-actions">{actionButtons}</div>
              </div>
            </div>
            <div className="plans-featured-meta">
              <div className="plans-featured-meta-chip">
                <span className="label">Athlete</span>
                <span className="plans-featured-meta-value">{plan.full_name || "Athlete profile"}</span>
              </div>
              <div className="plans-featured-meta-chip plans-featured-meta-chip-accent">
                <span className="label">Style</span>
                <span className="plans-featured-meta-value">{styleSummary}</span>
              </div>
              <div className="plans-featured-meta-chip">
                <span className="label">Status</span>
                <span className="plans-featured-meta-value">{statusLabel}</span>
              </div>
              <div className="plans-featured-meta-chip">
                <span className="label">Access</span>
                <span className="plans-featured-meta-value">Open plan for full export options</span>
              </div>
            </div>
          </div>
          {message ? <div className="success-banner">{message}</div> : null}
          {error && !isDeleteConfirmOpen ? <div className="error-banner">{error}</div> : null}
        </article>
        {deleteConfirmationModal}
      </>
    );
  }

  return (
    <>
      <article className="plan-history-row plan-history-row-card">
        <div className="plan-history-copy">
          <p className="label">{fightDateLabel}</p>
          <Link href={`/plans/${plan.plan_id}`}>
            <h2 className="plan-card-title">{planTitle}</h2>
          </Link>
          {inlineRenameForm}
          <div className="plan-card-meta">
            <span className="muted">{styleSummary}</span>
            <span className="muted">Created {createdLabel}</span>
          </div>
        </div>
        <div className="plan-history-meta">
          <span className="badge">{statusLabel}</span>
          <div className="plan-card-actions plans-history-actions">{actionButtons}</div>
        </div>
        {message || (error && !isDeleteConfirmOpen) ? (
          <div className="plan-history-feedback">
            {message ? <div className="success-banner">{message}</div> : null}
            {error ? <div className="error-banner">{error}</div> : null}
          </div>
        ) : null}
      </article>
      {deleteConfirmationModal}
    </>
  );
}

export default function PlansPage() {
  const router = useRouter();
  const { session } = useAppSession();
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localPlans, setLocalPlans] = useState<PlanSummary[] | null>(null);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const visiblePlans = useMemo(() => {
    const sourcePlans = localPlans ?? plans;
    return [...sourcePlans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  }, [localPlans, plans]);
  const featuredPlan = visiblePlans[0] ?? null;
  const historicalPlans = featuredPlan ? visiblePlans.slice(1) : [];
  const archiveCountLabel = historicalPlans.length === 1 ? "1 plan" : `${historicalPlans.length} plans`;
  const latestSavedLabel = featuredPlan ? formatPlanTimestamp(featuredPlan.created_at) : isLoading ? "Loading..." : "No saved plans yet";
  const latestFightLabel = featuredPlan ? formatPlanFightDate(featuredPlan.fight_date) : "Set during onboarding";
  const latestStyleLabel = featuredPlan ? getPlanStyleSummary(featuredPlan) : "Appears after the first generation";

  useEffect(() => {
    if (!session?.access_token) {
      return;
    }
    setIsLoading(true);
    setError(null);
    listPlans(session.access_token)
      .then((nextPlans) => {
        setPlans(nextPlans);
      })
      .catch((plansError) => {
        setError(plansError instanceof Error ? plansError.message : "Unable to load plan history.");
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [session?.access_token]);

  useEffect(() => {
    if (!historicalPlans.length) {
      setIsArchiveOpen(false);
    }
  }, [historicalPlans.length]);

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

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Plan History</p>
            <h1>Your saved plans</h1>
            <p className="muted">Open the latest camp fast, then reopen older saves from the archive dropdown.</p>
          </div>
        </div>

        <div className="plans-status-strip athlete-motion-slot athlete-motion-status" aria-label="Plan history status">
          <div className="plans-status-item">
            <p className="label">Saved plans</p>
            <p className="plans-status-value">{visiblePlans.length}</p>
            <p className="muted">Every generated camp stays attached to your account.</p>
          </div>
          <div className="plans-status-item">
            <p className="label">Latest save</p>
            <p className="plans-status-value">{latestSavedLabel}</p>
            <p className="muted">Newest version available to reopen right away.</p>
          </div>
          <div className="plans-status-item">
            <p className="label">Latest fight date</p>
            <p className="plans-status-value">{latestFightLabel}</p>
            <p className="muted">{latestStyleLabel}</p>
          </div>
        </div>

        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        {featuredPlan ? (
          <div className="plans-feature-stack athlete-motion-slot athlete-motion-main">
            <PlanCard
              plan={featuredPlan}
              variant="featured"
              accessToken={session?.access_token ?? null}
              onPlanDeleted={handlePlanDeleted}
              onPlanRenamed={handlePlanRenamed}
            />
          </div>
        ) : isLoading ? (
          <>
            <PlansFeaturedSkeleton />
            <div className="plans-history-block athlete-motion-slot athlete-motion-main" aria-busy="true">
              <div className="plan-history-list plans-history-list">
                <PlanHistoryRowSkeleton />
                <PlanHistoryRowSkeleton />
              </div>
            </div>
          </>
        ) : (
          <article className="list-card plan-card plans-featured-card plans-placeholder-card athlete-motion-slot athlete-motion-main">
            <div className="plans-featured-topline">
              <div className="plans-featured-kicker">
                <p className="kicker">No plans yet</p>
                <p className="muted">The first saved camp will take this featured slot.</p>
              </div>
            </div>
            <div className="plans-featured-main">
              <div className="plans-featured-copy">
                <p className="label">First generation</p>
                <h2 className="plan-card-title plans-featured-title">Start your first saved camp</h2>
                <p className="muted plans-featured-summary">Complete onboarding, generate the first plan, and this page turns into your archive and launchpad.</p>
              </div>
              <div className="plans-featured-meta">
                <div className="plans-featured-meta-chip plans-featured-meta-chip-accent">
                  <span className="label">Next step</span>
                  <span className="plans-featured-meta-value">Finish onboarding</span>
                </div>
              </div>
            </div>
            <div className="plans-featured-accent" aria-hidden="true">
              <span />
            </div>
            <div className="plan-card-actions plans-featured-actions">
              <Link href="/onboarding" className="cta plans-featured-primary-action">
                Start onboarding
              </Link>
            </div>
          </article>
        )}

        {featuredPlan ? (
          <div className="plans-history-block athlete-motion-slot athlete-motion-main">
            <div className="plans-history-header">
              <div className="plans-history-header-copy">
                <p className="kicker">Archive</p>
                <h2>Earlier saves</h2>
                <p className="muted">Open the archive for older versions.</p>
              </div>
              {historicalPlans.length ? (
                <button
                  type="button"
                  className={`plans-history-toggle ${isArchiveOpen ? "plans-history-toggle-open" : ""}`.trim()}
                  onClick={() => setIsArchiveOpen((current) => !current)}
                  aria-expanded={isArchiveOpen}
                  aria-controls="plans-history-dropdown"
                  aria-label={isArchiveOpen ? "Hide earlier saves" : "Show earlier saves"}
                >
                  <span className="plans-history-toggle-copy">
                    {isArchiveOpen ? "Hide archive" : "View archive"}
                  </span>
                  <span className="plans-history-toggle-meta">
                    <span className="plans-history-toggle-count">{archiveCountLabel}</span>
                    <span className="custom-select-chevron" aria-hidden="true" />
                  </span>
                </button>
              ) : (
                <span className="badge status-badge-neutral">No earlier plans</span>
              )}
            </div>

            {historicalPlans.length && isArchiveOpen ? (
              <div id="plans-history-dropdown" className="plans-history-dropdown" role="region" aria-label="Earlier saved plans">
                <div className="plan-history-list plans-history-list">
                  {historicalPlans.map((plan) => (
                    <PlanCard
                      key={plan.plan_id}
                      plan={plan}
                      accessToken={session?.access_token ?? null}
                      onPlanDeleted={handlePlanDeleted}
                      onPlanRenamed={handlePlanRenamed}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </RequireAuth>
  );
}
