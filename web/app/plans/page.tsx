"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
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
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const planTitle = getPlanDisplayName(plan);
  const featuredTitle = getFeaturedPlanTitle(plan);
  const fightDateLabel = formatPlanFightDate(plan.fight_date);
  const createdLabel = formatPlanTimestamp(plan.created_at);
  const styleSummary = getPlanStyleSummary(plan);
  const statusLabel = formatPlanStatus(plan.status);

  const actionButtons = (
    <>
      <Link href={`/plans/${plan.plan_id}`} className={variant === "featured" ? "cta plans-featured-primary-action" : "ghost-button"}>
        Open plan
      </Link>
      <button type="button" className="ghost-button" onClick={handleRename} disabled={pendingAction !== null}>
        {pendingAction === "rename" ? "Renaming..." : "Rename"}
      </button>
      <button type="button" className="ghost-button danger-button" onClick={handleDelete} disabled={pendingAction !== null}>
        {pendingAction === "delete" ? "Deleting..." : "Delete"}
      </button>
      {plan.pdf_url ? (
        <Link href={plan.pdf_url} target="_blank" rel="noreferrer" className="secondary-button">
          Open PDF
        </Link>
      ) : null}
    </>
  );

  async function handleRename() {
    if (!accessToken) {
      setError("Session missing. Please sign in again.");
      return;
    }

    const currentName = plan.plan_name?.trim() || "";
    const nextName = window.prompt("Rename this plan", currentName || plan.fight_date || "");
    if (nextName == null) {
      return;
    }

    const normalizedName = nextName.trim();
    if (!normalizedName) {
      setError("Plan name cannot be empty.");
      return;
    }
    if (normalizedName === currentName) {
      return;
    }

    setPendingAction("rename");
    setError(null);
    setMessage(null);
    try {
      const updatedPlan = await renamePlan(accessToken, plan.plan_id, normalizedName);
      onPlanRenamed(updatedPlan);
      setMessage("Plan renamed.");
    } catch (renameError) {
      setError(renameError instanceof Error ? renameError.message : "Unable to rename this plan.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleDelete() {
    if (!accessToken) {
      setError("Session missing. Please sign in again.");
      return;
    }
    const confirmed = window.confirm(`Delete "${getPlanDisplayName(plan)}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }

    setPendingAction("delete");
    setError(null);
    setMessage(null);
    try {
      await deletePlan(accessToken, plan.plan_id);
      onPlanDeleted(plan.plan_id);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete this plan.");
    } finally {
      setPendingAction(null);
    }
  }

  if (variant === "featured") {
    return (
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
              <span className="label">PDF</span>
              <span className="plans-featured-meta-value">{plan.pdf_url ? "Ready to open" : "Not available yet"}</span>
            </div>
          </div>
        </div>
        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}
      </article>
    );
  }

  return (
    <article className="plan-history-row plan-history-row-card">
      <div className="plan-history-copy">
        <p className="label">{fightDateLabel}</p>
        <Link href={`/plans/${plan.plan_id}`}>
          <h2 className="plan-card-title">{planTitle}</h2>
        </Link>
        <div className="plan-card-meta">
          <span className="muted">{styleSummary}</span>
          <span className="muted">Created {createdLabel}</span>
        </div>
      </div>
      <div className="plan-history-meta">
        <span className="badge">{statusLabel}</span>
        <div className="plan-card-actions plans-history-actions">{actionButtons}</div>
      </div>
      {message || error ? (
        <div className="plan-history-feedback">
          {message ? <div className="success-banner">{message}</div> : null}
          {error ? <div className="error-banner">{error}</div> : null}
        </div>
      ) : null}
    </article>
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
      return source.filter((plan) => plan.plan_id !== planId);
    });
    router.refresh();
  }

  function handlePlanRenamed(updatedPlan: PlanSummary) {
    setLocalPlans((current) => {
      const source = current ?? plans;
      return source.map((plan) => (plan.plan_id === updatedPlan.plan_id ? { ...plan, ...updatedPlan } : plan));
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
          <article className="list-card plan-card plans-featured-card plans-placeholder-card athlete-motion-slot athlete-motion-main">
            <div className="plans-featured-topline">
              <div className="plans-featured-kicker">
                <p className="kicker">Loading</p>
                <p className="muted">Rebuilding your plan history now.</p>
              </div>
            </div>
            <div className="plans-featured-main">
              <div className="plans-featured-copy">
                <p className="label">Plan history</p>
                <h2 className="plan-card-title plans-featured-title">Fetching your saved plans</h2>
                <p className="muted plans-featured-summary">Pulling the latest plan first so the current camp becomes the main focus.</p>
              </div>
            </div>
            <div className="plans-featured-accent" aria-hidden="true">
              <span />
            </div>
          </article>
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
