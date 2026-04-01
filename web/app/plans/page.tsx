"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { deletePlan, listPlans, renamePlan } from "@/lib/api";
import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import type { PlanSummary } from "@/lib/types";

function getPlanDisplayName(plan: PlanSummary): string {
  return plan.plan_name?.trim() || plan.fight_date || "Open plan";
}

function PlanCard({
  plan,
  accessToken,
  onPlanDeleted,
  onPlanRenamed,
}: {
  plan: PlanSummary;
  accessToken: string | null;
  onPlanDeleted: (planId: string) => void;
  onPlanRenamed: (updatedPlan: PlanSummary) => void;
}) {
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <article className="list-card plan-card">
      <div className="plan-card-header">
        <div>
          <p className="label">Fight date</p>
          <Link href={`/plans/${plan.plan_id}`}>
            <h2 className="plan-card-title">{getPlanDisplayName(plan)}</h2>
          </Link>
        </div>
        <span className="badge">{plan.status}</span>
      </div>
      <p className="muted">{getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Unspecified style"}</p>
      <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
      <div className="plan-card-actions">
        <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
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
      </div>
      {message ? <div className="success-banner">{message}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
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
  const visiblePlans = useMemo(() => {
    const sourcePlans = localPlans ?? plans;
    return [...sourcePlans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  }, [localPlans, plans]);

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
          <div>
            <p className="kicker">Plan History</p>
            <h1>Your saved plans</h1>
            <p className="muted">Open current and older plans from one saved history.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Saved</p>
            <h2 className="plan-summary-title">{visiblePlans.length}</h2>
            <p className="muted">Every generated plan stays attached to your account.</p>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        <div className="plans-grid">
          {visiblePlans.map((plan) => (
            <PlanCard
              key={plan.plan_id}
              plan={plan}
              accessToken={session?.access_token ?? null}
              onPlanDeleted={handlePlanDeleted}
              onPlanRenamed={handlePlanRenamed}
            />
          ))}

          {!isLoading && !visiblePlans.length ? (
            <article className="list-card plan-card">
              <div className="form-section-header">
                <p className="kicker">No plans yet</p>
                <h2>Start your first generation</h2>
              </div>
              <p className="muted">Complete onboarding to create the first saved fight camp in this workspace.</p>
              <div className="plan-card-actions">
                <Link href="/onboarding" className="cta inline-cta">
                  Start onboarding
                </Link>
              </div>
            </article>
          ) : null}
          {isLoading ? (
            <article className="list-card plan-card">
              <div className="form-section-header">
                <p className="kicker">Loading</p>
                <h2>Fetching your saved plans</h2>
              </div>
              <p className="muted">Rebuilding your plan history now.</p>
            </article>
          ) : null}
        </div>
      </section>
    </RequireAuth>
  );
}

