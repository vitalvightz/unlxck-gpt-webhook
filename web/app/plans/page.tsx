"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanHistoryRowSkeleton, PlansFeaturedSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { ApiError, archivePlan, getActivePlan, listPlans, renamePlan, setActivePlan } from "@/lib/api";
import { markGenerationIntent } from "@/lib/generation-intent";
import {
  EQUIPMENT_ACCESS_OPTIONS,
  getOptionLabels,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import {
  formatPlanFightDate,
  formatPlanStatus,
  formatPlanTimestamp,
  getPlanDisplayName,
  getPlanStyleSummary,
} from "@/lib/plan-format";
import {
  ACTIVE_PLAN_OVERLAP_MESSAGE,
  type ActivePlanOverlapAction,
  canSetActivePlan,
  isActivePlanOverlapError,
  isArchivedPlan,
} from "@/lib/plan-active";
import { getPlanReviewReason, isHeldForAdminReviewPlan } from "@/lib/plan-review";
import type { MeResponse, PlanRequest, PlanSummary, ProfileRecord } from "@/lib/types";

type SummaryLine = {
  label: string;
  value: string;
};

function getRenameDraftValue(plan: PlanSummary): string {
  return plan.plan_name?.trim() || plan.fight_date || "";
}

function getArchivedPlans(plans: PlanSummary[]): PlanSummary[] {
  return plans.filter((plan) => isArchivedPlan(plan.status));
}

function canSetActive(plan: PlanSummary): boolean {
  return canSetActivePlan(plan.status);
}

function isActivePlan(plan: PlanSummary, activePlanId: string | null): boolean {
  return Boolean(activePlanId && plan.plan_id === activePlanId);
}

function formatCompactList(values: string[], fallback: string): string {
  return values.length ? values.join(", ") : fallback;
}

function formatWeeklySessions(value: number | null | undefined): string | null {
  if (!Number.isFinite(value) || value === null || value === undefined || value <= 0) {
    return null;
  }
  return `${value} session${value === 1 ? "" : "s"} per week`;
}

function countTrainingDays(availability: string[] | undefined): number | null {
  if (!availability?.length) {
    return null;
  }
  return availability.length;
}

function summarizeEquipment(equipmentAccess: string[] | undefined): string | null {
  if (!equipmentAccess?.length) {
    return null;
  }
  const labels = getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, equipmentAccess);
  const visible = labels.slice(0, 3);
  const remaining = labels.length - visible.length;
  return remaining > 0 ? `${visible.join(", ")} +${remaining} more` : visible.join(", ");
}

function getPlanVersionLabel(plan: PlanSummary): string {
  if (plan.plan_name?.trim()) {
    return "Named plan";
  }
  return plan.fight_date ? "Fight camp" : "Open camp";
}

function getProfileSource(me: MeResponse | null): ProfileRecord | null {
  return me?.profile ?? null;
}

type DraftWithSource = PlanRequest & { plan_source?: string };

function getSavedDetailedDraft(me: MeResponse | null): PlanRequest | null {
  const draft = me?.profile?.onboarding_draft as DraftWithSource | null | undefined;
  if (!draft) {
    return null;
  }
  return draft.plan_source === "quick_build" ? null : draft;
}

function getIntakeSource(me: MeResponse | null): PlanRequest | null {
  return me?.latest_intake ?? getSavedDetailedDraft(me) ?? null;
}

function summarizeProfile(me: MeResponse | null): SummaryLine[] {
  const profile = getProfileSource(me);
  const intake = getIntakeSource(me);
  const athleteName = profile?.full_name?.trim() || intake?.athlete.full_name?.trim() || "Athlete profile";
  const technicalStyle = getOptionLabels(
    TECHNICAL_STYLE_OPTIONS,
    profile?.technical_style?.length ? profile.technical_style : intake?.athlete.technical_style ?? [],
  );
  const tacticalStyle = getOptionLabels(
    TACTICAL_STYLE_OPTIONS,
    profile?.tactical_style?.length ? profile.tactical_style : intake?.athlete.tactical_style ?? [],
  );

  const lines: SummaryLine[] = [
    { label: "Athlete", value: athleteName },
    { label: "Technical style", value: formatCompactList(technicalStyle, "Not set yet") },
  ];

  if (tacticalStyle.length) {
    lines.push({ label: "Tactical style", value: tacticalStyle.join(", ") });
  }

  return lines;
}

function summarizeIntake(me: MeResponse | null): SummaryLine[] {
  const intake = getIntakeSource(me);
  if (!intake) {
    return [];
  }

  const lines: SummaryLine[] = [];
  const weeklySessions = formatWeeklySessions(intake.weekly_training_frequency);
  const trainingDayCount = countTrainingDays(intake.training_availability);
  const equipmentSummary = summarizeEquipment(intake.equipment_access);

  if (weeklySessions) {
    lines.push({ label: "Weekly volume", value: weeklySessions });
  }
  if (trainingDayCount !== null) {
    lines.push({ label: "Training days", value: `${trainingDayCount} day${trainingDayCount === 1 ? "" : "s"} available` });
  }
  if (equipmentSummary) {
    lines.push({ label: "Equipment", value: equipmentSummary });
  }

  return lines;
}

function HeldPlansReviewNotice({ plans }: { plans: PlanSummary[] }) {
  const visibleHeldPlans = plans.slice(0, 3);
  const remainingCount = Math.max(0, plans.length - visibleHeldPlans.length);

  return (
    <article className="list-card plans-dashboard-card athlete-motion-slot athlete-motion-status">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">Admin review hold</p>
          <h2>{plans.length === 1 ? "A plan is held for review" : `${plans.length} plans are held for review`}</h2>
          <p className="muted">
            These plans are saved, but they are not released to Overview or Today until admin approval clears the hold.
          </p>
        </div>
        <span className="badge">HELD</span>
      </div>

      <div className="plan-history-list plans-history-list">
        {visibleHeldPlans.map((plan) => (
          <div key={plan.plan_id} className="plan-history-row">
            <div className="plan-history-copy">
              <p className="label">{formatPlanStatus(plan.status)}</p>
              <Link href={`/plans/${plan.plan_id}`}>
                <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
              </Link>
              <p className="muted">{getPlanReviewReason(plan)}</p>
            </div>
            <div className="plan-history-meta">
              <Link href={`/plans/${plan.plan_id}?review_required=1`} className="ghost-button">
                Review hold
              </Link>
            </div>
          </div>
        ))}
      </div>

      {remainingCount > 0 ? (
        <p className="muted">
          {remainingCount} more held plan{remainingCount === 1 ? "" : "s"} shown in saved plan history.
        </p>
      ) : null}
    </article>
  );
}

function PlanCard({
  plan,
  accessToken,
  onPlanDeleted,
  onPlanRenamed,
  activePlanId,
  onSetActive,
  isSettingActive,
}: {
  plan: PlanSummary;
  accessToken: string | null;
  onPlanDeleted: (planId: string) => void;
  onPlanRenamed: (updatedPlan: PlanSummary) => void;
  activePlanId: string | null;
  onSetActive: (plan: PlanSummary) => Promise<void>;
  isSettingActive: boolean;
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
  const fightDateLabel = formatPlanFightDate(plan.fight_date);
  const createdLabel = formatPlanTimestamp(plan.created_at);
  const styleSummary = getPlanStyleSummary(plan);
  const statusLabel = formatPlanStatus(plan.status);
  const versionLabel = getPlanVersionLabel(plan);
  const isActionPending = pendingAction !== null || isSettingActive;
  const renameInputId = `rename-plan-${plan.plan_id}`;
  const active = isActivePlan(plan, activePlanId);
  const eligibleForActive = canSetActive(plan);
  const archived = isArchivedPlan(plan.status);
  const reviewReason = getPlanReviewReason(plan);

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
      setError("Session expired. Sign in again.");
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
        setError("Connection issue. Try again in a minute.");
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
      setError("Session expired. Sign in again.");
      return;
    }

    setPendingAction("delete");
    setError(null);
    setMessage(null);
    try {
      await archivePlan(accessToken, plan.plan_id);
      setIsDeleteConfirmOpen(false);
      onPlanDeleted(plan.plan_id);
      showToast(`Archived ${getPlanDisplayName(plan)}.`, { tone: "success" });
    } catch (deleteError) {
      const errorMessage = deleteError instanceof Error ? deleteError.message : "Unable to delete this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError("Connection issue. Try again in a minute.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setPendingAction(null);
    }
  }

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
            <p className="kicker">Archive plan</p>
            <h2 id={`delete-plan-title-${plan.plan_id}`} className="plan-dialog-title">
              Archive {getPlanDisplayName(plan)}?
            </h2>
          </div>
          <p id={`delete-plan-body-${plan.plan_id}`} className="muted">
            This moves the plan to your archived list. You can still view it later.
          </p>
          {error ? <div className="error-banner">{error}</div> : null}
          <div className="plan-dialog-actions">
            <button type="button" className="ghost-button" onClick={handleDeleteDismiss} disabled={pendingAction === "delete"}>
              Cancel
            </button>
            <button type="button" className="secondary-button" onClick={handleDeleteConfirm} disabled={pendingAction === "delete"}>
              {pendingAction === "delete" ? "Archiving..." : "Archive"}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <article className="plan-history-row plan-history-row-card">
        <div className="plan-history-copy">
          <p className="label">{versionLabel}</p>
          <Link href={`/plans/${plan.plan_id}`}>
            <h2 className="plan-card-title">{planTitle}</h2>
          </Link>
          {inlineRenameForm}
          <div className="plan-card-meta">
            {plan.fight_date ? <span className="muted">Fight {fightDateLabel}</span> : null}
            <span className="muted">{styleSummary}</span>
            <span className="muted">Built {createdLabel}</span>
          </div>
          {reviewReason ? <p className="muted">{reviewReason}</p> : null}
        </div>
        <div className="plan-history-meta">
          <span className="badge">{active ? "ACTIVE" : statusLabel}</span>
          {!active && !eligibleForActive ? <span className="muted">Cannot be active</span> : null}
          <div className="plan-card-actions plans-history-actions">
            <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
              {archived ? "Preview" : "Review"}
            </Link>
            {archived ? (
              <Link href="/onboarding" className="ghost-button">
                Duplicate as New Plan
              </Link>
            ) : null}
            {!archived && !active && eligibleForActive ? (
              <button type="button" className="secondary-button" onClick={() => void onSetActive(plan)} disabled={isActionPending || isRenaming}>
                {isSettingActive ? "Setting..." : "Set active"}
              </button>
            ) : null}
            {!archived ? (
              <>
                <button type="button" className="ghost-button" onClick={handleRenameStart} disabled={isActionPending || isRenaming}>
                  {pendingAction === "rename" ? "Saving..." : isRenaming ? "Editing name" : "Rename"}
                </button>
                <button type="button" className="ghost-button" onClick={handleDeleteRequest} disabled={isActionPending || isRenaming}>
                  {pendingAction === "delete" ? "Archiving..." : "Archive"}
                </button>
              </>
            ) : null}
          </div>
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

function PlanActivationConflictDialog({
  plan,
  isPending,
  onConfirm,
  onStartAfter,
  onCancel,
}: {
  plan: PlanSummary;
  isPending: boolean;
  onConfirm: (action: ActivePlanOverlapAction) => Promise<void>;
  onStartAfter: () => void;
  onCancel: () => void;
}) {
  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div className="plan-dialog-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="plan-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`activate-conflict-title-${plan.plan_id}`}
        aria-describedby={`activate-conflict-body-${plan.plan_id}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="plan-dialog-header">
          <p className="kicker">Active plan conflict</p>
          <h2 id={`activate-conflict-title-${plan.plan_id}`} className="plan-dialog-title">
            {getPlanDisplayName(plan)}
          </h2>
        </div>
        <p id={`activate-conflict-body-${plan.plan_id}`} className="muted">
          {ACTIVE_PLAN_OVERLAP_MESSAGE}
        </p>
        <div className="plan-dialog-actions">
          <button type="button" className="secondary-button" onClick={() => void onConfirm("replace")} disabled={isPending}>
            Replace current plan
          </button>
          <button type="button" className="secondary-button" onClick={() => void onConfirm("pause")} disabled={isPending}>
            Pause current plan
          </button>
          <button type="button" className="ghost-button" onClick={onStartAfter} disabled={isPending}>
            Start after current plan ends
          </button>
          <button type="button" className="ghost-button" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function DashboardSummary({
  title,
  lines,
  emptyLabel,
}: {
  title: string;
  lines: SummaryLine[];
  emptyLabel: string;
}) {
  return (
    <div className="plans-dashboard-summary">
      <p className="label">{title}</p>
      {lines.length ? (
        <div className="plans-dashboard-summary-grid">
          {lines.map((line) => (
            <div key={`${title}-${line.label}`} className="plans-dashboard-summary-row">
              <span className="plans-dashboard-summary-term">{line.label}</span>
              <span className="plans-dashboard-summary-value">{line.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">{emptyLabel}</p>
      )}
    </div>
  );
}

function LatestPlanCard({
  plan,
  intake,
  accessToken,
  onPlanDeleted,
  onPlanRenamed,
}: {
  plan: PlanSummary | null;
  intake: PlanRequest | null;
  accessToken: string | null;
  onPlanDeleted: (planId: string) => void;
  onPlanRenamed: (updatedPlan: PlanSummary) => void;
}) {
  const { showToast } = useToast();
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState(() => (plan ? getRenameDraftValue(plan) : ""));
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const fightDate = plan?.fight_date || "";
  const hasSavedIntake = Boolean(intake);
  const latestPlanLines: SummaryLine[] = [];
  const renameInputId = plan ? `rename-latest-plan-${plan.plan_id}` : "rename-latest-plan";
  const isActionPending = pendingAction !== null;

  if (plan) {
    latestPlanLines.push({ label: "Created", value: formatPlanTimestamp(plan.created_at) });
    if (fightDate) {
      latestPlanLines.push({ label: "Fight date", value: formatPlanFightDate(fightDate) });
    }
    if (plan.status?.trim()) {
      latestPlanLines.push({ label: "Status", value: formatPlanStatus(plan.status) });
    }
  }

  useEffect(() => {
    if (!plan) {
      setRenameDraft("");
      setIsRenaming(false);
      return;
    }
    if (!isRenaming) {
      setRenameDraft(getRenameDraftValue(plan));
      return;
    }

    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [isRenaming, plan]);

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
    if (!plan) {
      return;
    }
    setError(null);
    setRenameDraft(getRenameDraftValue(plan));
    setIsRenaming(true);
  }

  function handleRenameCancel() {
    if (isActionPending || !plan) {
      return;
    }
    setError(null);
    setRenameDraft(getRenameDraftValue(plan));
    setIsRenaming(false);
  }

  async function handleRenameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!plan) {
      return;
    }
    if (!accessToken) {
      setError("Session expired. Sign in again.");
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
    try {
      const updatedPlan = await renamePlan(accessToken, plan.plan_id, normalizedName);
      onPlanRenamed(updatedPlan);
      showToast("Plan renamed.", { tone: "success" });
      setIsRenaming(false);
    } catch (renameError) {
      const errorMessage = renameError instanceof Error ? renameError.message : "Unable to rename this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError("Connection issue. Try again in a minute.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setPendingAction(null);
    }
  }

  function handleDeleteRequest() {
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
    if (!plan) {
      return;
    }
    if (!accessToken) {
      setError("Session expired. Sign in again.");
      return;
    }

    setPendingAction("delete");
    setError(null);
    try {
      await archivePlan(accessToken, plan.plan_id);
      setIsDeleteConfirmOpen(false);
      onPlanDeleted(plan.plan_id);
      showToast(`Archived ${getPlanDisplayName(plan)}.`, { tone: "success" });
    } catch (deleteError) {
      const errorMessage = deleteError instanceof Error ? deleteError.message : "Unable to delete this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError("Connection issue. Try again in a minute.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setPendingAction(null);
    }
  }

  const inlineRenameForm = plan && isRenaming ? (
    <form className="plan-inline-rename" onSubmit={handleRenameSubmit}>
      <label className="plan-inline-rename-label" htmlFor={renameInputId}>
        Rename latest plan
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

  const deleteConfirmationModal = plan && isDeleteConfirmOpen && typeof document !== "undefined"
    ? createPortal(
      <div className="plan-dialog-backdrop" role="presentation" onClick={handleDeleteDismiss}>
        <div
          className="plan-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`delete-latest-plan-title-${plan.plan_id}`}
          aria-describedby={`delete-latest-plan-body-${plan.plan_id}`}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="plan-dialog-header">
            <p className="kicker">Archive latest plan</p>
            <h2 id={`delete-latest-plan-title-${plan.plan_id}`} className="plan-dialog-title">
              Archive {getPlanDisplayName(plan)}?
            </h2>
          </div>
          <p id={`delete-latest-plan-body-${plan.plan_id}`} className="muted">
            This moves the plan to your archived list. You can still view it later.
          </p>
          {error ? <div className="error-banner">{error}</div> : null}
          <div className="plan-dialog-actions">
            <button type="button" className="ghost-button" onClick={handleDeleteDismiss} disabled={pendingAction === "delete"}>
              Cancel
            </button>
            <button type="button" className="secondary-button" onClick={handleDeleteConfirm} disabled={pendingAction === "delete"}>
              {pendingAction === "delete" ? "Archiving..." : "Archive"}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <article className="list-card plans-dashboard-card plans-dashboard-primary-card">
        <div className="plans-dashboard-card-header">
          <div className="plans-dashboard-card-copy">
            <p className="kicker">Active Plan</p>
            <h2>{plan ? getPlanDisplayName(plan) : "No active plan"}</h2>
            <p className="muted">
              {plan
                ? "This plan controls Overview and Today."
                : hasSavedIntake
                  ? "No active plan is selected. Generate or set one active from saved plans."
                  : "Complete Intake or Quick Build to create your first active plan."}
            </p>
            {!plan ? (
              <div className="empty-state-example plans-dashboard-empty-example">
                <p className="label">What appears here next</p>
                <p className="empty-state-example-body">
                  Once a plan is active, it opens here with fight date, status, and management actions.
                </p>
              </div>
            ) : null}
          </div>
          {plan?.status ? <span className="badge">ACTIVE</span> : null}
        </div>

        <DashboardSummary
          title="Current snapshot"
          lines={latestPlanLines}
          emptyLabel="No active plan metadata yet."
        />

        {inlineRenameForm}

        <div className="plan-card-actions plans-dashboard-actions">
          {plan ? (
            <>
              <Link href={`/plans/${plan.plan_id}`} className="cta">
                Open plan
              </Link>
              <Link
                href={intake ? "/generate" : "/onboarding"}
                className="ghost-button"
                onClick={() => {
                  if (intake) {
                    markGenerationIntent();
                  }
                }}
              >
                Generate new version
              </Link>
            </>
          ) : (
            <Link href={hasSavedIntake ? "/onboarding" : "/quick-build"} className="cta">
              {hasSavedIntake ? "Resume Advanced Intake" : "Quick Build New Plan"}
            </Link>
          )}
        </div>

        {plan ? (
          <div className="plan-card-actions plans-dashboard-management-actions" aria-label="Manage latest plan">
            <button type="button" className="ghost-button" onClick={handleRenameStart} disabled={isActionPending || isRenaming}>
              {pendingAction === "rename" ? "Saving..." : isRenaming ? "Editing name" : "Rename"}
            </button>
            <button type="button" className="ghost-button" onClick={handleDeleteRequest} disabled={isActionPending || isRenaming}>
              {pendingAction === "delete" ? "Archiving..." : "Archive"}
            </button>
          </div>
        ) : null}

        {error && !isDeleteConfirmOpen ? <div className="error-banner">{error}</div> : null}
      </article>
      {deleteConfirmationModal}
    </>
  );
}

function IntakeCard({
  me,
}: {
  me: MeResponse | null;
}) {
  const profileLines = summarizeProfile(me);
  const intake = getIntakeSource(me);
  const intakeLines = summarizeIntake(me);
  const hasIntake = Boolean(intake);

  return (
    <article className="list-card plans-dashboard-card">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">Current Athlete Profile / Intake</p>
          <h2>{profileLines[0]?.value || "Athlete profile"}</h2>
          <p className="muted">
            This is the source for your next generated camp. Review it before starting another build.
          </p>
        </div>
        <span className={`badge ${hasIntake ? "status-badge-success" : "status-badge-neutral"}`}>
          {hasIntake ? "Intake ready" : "Profile only"}
        </span>
      </div>

      <div className="plans-dashboard-meta-grid">
        <DashboardSummary
          title="Profile"
          lines={profileLines}
          emptyLabel="No profile summary available yet."
        />
        <DashboardSummary
          title="Intake"
          lines={intakeLines}
          emptyLabel="No intake summary saved yet."
        />
      </div>

      <div className="plan-card-actions plans-dashboard-actions">
        <Link href="/onboarding" className="cta">
          {hasIntake ? "Review & edit intake" : "Complete Advanced Intake"}
        </Link>
      </div>
    </article>
  );
}

export default function PlansPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const { isMeHydrated, me, session } = useAppSession();
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localPlans, setLocalPlans] = useState<PlanSummary[] | null>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [isSettingActivePlanId, setIsSettingActivePlanId] = useState<string | null>(null);
  const [overlapConflictPlan, setOverlapConflictPlan] = useState<PlanSummary | null>(null);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const latestTokenRef = useRef(session?.access_token);

  useEffect(() => {
    latestTokenRef.current = session?.access_token;
  }, [session?.access_token]);

  const visiblePlans = useMemo(() => {
    const sourcePlans = localPlans ?? plans;
    return [...sourcePlans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  }, [localPlans, plans]);
  const latestEligiblePlan = visiblePlans.find(canSetActive) ?? null;
  const explicitActivePlan = activePlanId ? visiblePlans.find((plan) => plan.plan_id === activePlanId) ?? null : null;
  const activePlan = explicitActivePlan && canSetActive(explicitActivePlan) ? explicitActivePlan : latestEligiblePlan;
  const intakeSource = getIntakeSource(me);
  const heldForReviewPlans = visiblePlans.filter(isHeldForAdminReviewPlan);
  const archivedPlans = getArchivedPlans(visiblePlans);
  const otherSavedPlans = visiblePlans.filter((plan) => plan.plan_id !== activePlan?.plan_id && !isArchivedPlan(plan.status));
  const archiveCountLabel = archivedPlans.length === 1 ? "1 plan" : `${archivedPlans.length} plans`;
  const hasPlans = visiblePlans.length > 0;

  const loadPlans = useCallback(async () => {
    const token = session?.access_token;
    if (!token) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [nextPlans, active] = await Promise.all([
        listPlans(token),
        getActivePlan(token).catch((activeError) => {
          if (activeError instanceof ApiError && activeError.status === 404) {
            return null;
          }
          throw activeError;
        }),
      ]);
      // Ignore results from a request that the current session has moved past.
      if (latestTokenRef.current !== token) {
        return;
      }
      setPlans(nextPlans);
      setActivePlanId(active?.plan_id ?? null);
    } catch (plansError) {
      if (latestTokenRef.current !== token) {
        return;
      }
      const message = plansError instanceof Error ? plansError.message : "";
      setError(message.includes("401") || message.toLowerCase().includes("session")
        ? "Session expired. Sign in again."
        : "Connection issue. Try again in a minute.");
    } finally {
      if (latestTokenRef.current === token) {
        setIsLoading(false);
      }
    }
  }, [session?.access_token]);

  useEffect(() => {
    void loadPlans();
  }, [loadPlans]);

  useEffect(() => {
    if (!archivedPlans.length) {
      setIsArchiveOpen(false);
    }
  }, [archivedPlans.length]);

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

  async function activatePlan(plan: PlanSummary, overlapAction?: ActivePlanOverlapAction): Promise<void> {
    const token = session?.access_token;
    if (!token || !canSetActive(plan)) {
      return;
    }
    setIsSettingActivePlanId(plan.plan_id);
    try {
      const active = await setActivePlan(token, plan.plan_id, { overlapAction });
      setActivePlanId(active.plan_id);
      setOverlapConflictPlan(null);
      showToast("Active plan updated.", { tone: "success" });
      await loadPlans();
      router.refresh();
    } catch (activeError) {
      if (!overlapAction && isActivePlanOverlapError(activeError)) {
        setOverlapConflictPlan(plan);
        return;
      }
      const message = activeError instanceof Error ? activeError.message : "Unable to set active plan.";
      showToast(message, { tone: "error" });
    } finally {
      setIsSettingActivePlanId(null);
    }
  }

  async function handleSetActive(plan: PlanSummary): Promise<void> {
    await activatePlan(plan);
  }

  async function handleOverlapConfirm(action: ActivePlanOverlapAction): Promise<void> {
    if (!overlapConflictPlan) {
      return;
    }
    await activatePlan(overlapConflictPlan, action);
  }

  function handleStartAfterCurrentPlan() {
    setOverlapConflictPlan(null);
    showToast("Choose a new start date before generating the next version.", { tone: "success" });
    router.push("/onboarding");
  }

  const isPlanListLoading = isLoading;
  const isProfileLoading = !isMeHydrated;

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Plan Dashboard</p>
            <h1>Your plan workspace</h1>
            <p className="muted">Open the active camp, review your current intake, or generate a new version from the current profile.</p>
          </div>
        </div>

        {error ? (
          <div className="error-banner athlete-motion-slot athlete-motion-status" role="alert">
            <span>{error}</span>
            {error.includes("Session expired") ? null : (
              <button
                type="button"
                className="error-banner-retry"
                onClick={() => void loadPlans()}
                disabled={isLoading}
              >
                {isLoading ? "Retrying..." : "Retry"}
              </button>
            )}
          </div>
        ) : null}

        {!isLoading && heldForReviewPlans.length > 0 ? (
          <HeldPlansReviewNotice plans={heldForReviewPlans} />
        ) : null}

        <div className="plans-dashboard-stack athlete-motion-slot athlete-motion-main">
          {isPlanListLoading ? (
            <PlansFeaturedSkeleton />
          ) : (
            <LatestPlanCard
              plan={activePlan}
              intake={intakeSource}
              accessToken={session?.access_token ?? null}
              onPlanDeleted={handlePlanDeleted}
              onPlanRenamed={handlePlanRenamed}
            />
          )}
          {isProfileLoading ? <PlansFeaturedSkeleton /> : <IntakeCard me={me} />}
        </div>

        {isLoading ? (
          <div className="plans-history-block athlete-motion-slot athlete-motion-main" aria-busy="true">
            <div className="plan-history-list plans-history-list">
              <PlanHistoryRowSkeleton />
              <PlanHistoryRowSkeleton />
            </div>
          </div>
        ) : null}

        {!isLoading && hasPlans ? (
          <div className="plans-history-block athlete-motion-slot athlete-motion-main">
            <div className="plans-history-header">
              <div className="plans-history-header-copy">
                <p className="kicker">Plan Manager</p>
                <h2>Other saved plans</h2>
                <p className="muted">Compare previous versions by fight date, build time, and status before making one active.</p>
              </div>
              {archivedPlans.length ? (
                <button
                  type="button"
                  className={`plans-history-toggle ${isArchiveOpen ? "plans-history-toggle-open" : ""}`.trim()}
                  onClick={() => setIsArchiveOpen((current) => !current)}
                  aria-expanded={isArchiveOpen}
                  aria-controls="plans-history-dropdown"
                  aria-label={isArchiveOpen ? "Hide older saved plans" : "Show older saved plans"}
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


            {otherSavedPlans.length > 0 ? (
              <div className="plan-history-list plans-history-list">
                {otherSavedPlans.map((plan) => (
                  <PlanCard
                    key={plan.plan_id}
                    plan={plan}
                    accessToken={session?.access_token ?? null}
                    onPlanDeleted={handlePlanDeleted}
                    onPlanRenamed={handlePlanRenamed}
                    activePlanId={activePlanId}
                    onSetActive={handleSetActive}
                    isSettingActive={isSettingActivePlanId === plan.plan_id}
                  />
                ))}
              </div>
            ) : (
              <p className="muted">No other saved plans.</p>
            )}

            {archivedPlans.length > 0 && isArchiveOpen ? (
              <div id="plans-history-dropdown" className="plans-history-dropdown" role="region" aria-label="Older saved plans">
                <div className="plan-history-list plans-history-list">
                  {archivedPlans.map((plan) => (
                    <PlanCard
                      key={plan.plan_id}
                      plan={plan}
                      accessToken={session?.access_token ?? null}
                      onPlanDeleted={handlePlanDeleted}
                      onPlanRenamed={handlePlanRenamed}
                      activePlanId={activePlanId}
                      onSetActive={handleSetActive}
                      isSettingActive={isSettingActivePlanId === plan.plan_id}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
        {overlapConflictPlan ? (
          <PlanActivationConflictDialog
            plan={overlapConflictPlan}
            isPending={isSettingActivePlanId === overlapConflictPlan.plan_id}
            onConfirm={handleOverlapConfirm}
            onStartAfter={handleStartAfterCurrentPlan}
            onCancel={() => setOverlapConflictPlan(null)}
          />
        ) : null}
      </section>
    </RequireAuth>
  );
}
