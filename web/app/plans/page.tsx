"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations, useTranslations as useAppTranslations } from "next-intl";
import { createPortal } from "react-dom";
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { translateUiText } from "@/i18n/ui-text";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PlanHistoryRowSkeleton, PlansFeaturedSkeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { ApiError, archivePlan, getActivePlan, listPlans, renamePlan, setActivePlan } from "@/lib/api";
import { requestXpRefresh } from "@/lib/xp-events";
import { markGenerationIntent } from "@/lib/generation-intent";
import {
  EQUIPMENT_ACCESS_OPTIONS,
  getOptionLabels,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import {
  formatAthletePlanStatus,
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
  isCompletedFightCamp,
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
  return canSetActivePlan(plan.activation_state);
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
    { label: "Combat sport", value: formatCompactList(technicalStyle, "Not set yet") },
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
    const appText = useAppTranslations("AppText");
  const visibleHeldPlans = plans.slice(0, 3);
  const remainingCount = Math.max(0, plans.length - visibleHeldPlans.length);

  return (
    <article className="list-card plans-dashboard-card athlete-motion-slot athlete-motion-status">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">{appText("text_3913e9f3b004")}</p>
          <h2>{plans.length === 1 ? appText("text_f6fa09defada") : `${plans.length} plans are held for review`}</h2>
          <p className="muted">
            {appText("text_c61b33f3a2f9")}</p>
        </div>
        <span className="badge">{appText("text_0b6463c43302")}</span>
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
                {appText("text_06c73a110c8d")}</Link>
            </div>
          </div>
        ))}
      </div>

      {remainingCount > 0 ? (
        <p className="muted">
          {remainingCount} {appText("text_fcc4ec9969fc")}{remainingCount === 1 ? "" : appText("text_043a718774c5")} {appText("text_48681c8fd8c8")}</p>
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
    const appText = useAppTranslations("AppText");
  const { showToast } = useToast();
  const [pendingAction, setPendingAction] = useState<"rename" | "delete" | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState(() => getRenameDraftValue(plan));
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const renameDraftValue = plan.plan_name?.trim() || plan.fight_date || "";
  const planTitle = getPlanDisplayName(plan);
  const fightDateLabel = formatPlanFightDate(plan.fight_date);
  const createdLabel = formatPlanTimestamp(plan.created_at);
  const styleSummary = getPlanStyleSummary(plan);
  const statusLabel = formatAthletePlanStatus(plan.status);
  const versionLabel = getPlanVersionLabel(plan);
  const isActionPending = pendingAction !== null || isSettingActive;
  const renameInputId = `rename-plan-${plan.plan_id}`;
  const active = isActivePlan(plan, activePlanId);
  const eligibleForActive = canSetActive(plan);
  const archived = isArchivedPlan(plan.status);
  const completed = isCompletedFightCamp(plan.activation_state);
  const reviewReason = getPlanReviewReason(plan);

  useEffect(() => {
    if (!isRenaming) {
      setRenameDraft(renameDraftValue);
      return;
    }

    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [isRenaming, renameDraftValue]);

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
      setError(appText("text_95f5b7d0dc11"));
      return;
    }

    const currentName = plan.plan_name?.trim() || "";
    const normalizedName = renameDraft.trim();
    if (!normalizedName) {
      setError(appText("text_bee32f4af8c5"));
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
      showToast(appText("text_3884343b3c7f"), { tone: "success" });
      setIsRenaming(false);
    } catch (renameError) {
      const errorMessage = renameError instanceof Error ? renameError.message : "Unable to rename this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError(appText("text_c0ca548a25f7"));
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
      setError(appText("text_95f5b7d0dc11"));
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
        setError(appText("text_c0ca548a25f7"));
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
        {appText("text_3448258b1fbd")}</label>
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
            {pendingAction === "rename" ? appText("text_dc85af8f2b1d") : appText("text_1509f561f241")}
          </button>
          <button type="button" className="ghost-button" onClick={handleRenameCancel} disabled={isActionPending}>
            {appText("text_19766ed6ccb2")}</button>
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
            <p className="kicker">{appText("text_978244186546")}</p>
            <h2 id={`delete-plan-title-${plan.plan_id}`} className="plan-dialog-title">
              {appText("text_66f4804ee23d")}{getPlanDisplayName(plan)}{appText("text_8a8de823d5ed")}</h2>
          </div>
          <p id={`delete-plan-body-${plan.plan_id}`} className="muted">
            {appText("text_8affd0d4d884")}</p>
          {error ? <div className="error-banner">{translateUiText(appText, error)}</div> : null}
          <div className="plan-dialog-actions">
            <button type="button" className="ghost-button" onClick={handleDeleteDismiss} disabled={pendingAction === "delete"}>
              {appText("text_19766ed6ccb2")}</button>
            <button type="button" className="secondary-button" onClick={handleDeleteConfirm} disabled={pendingAction === "delete"}>
              {pendingAction === "delete" ? appText("text_6f3407113f07") : appText("text_66f4804ee23d")}
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <article className={`plan-history-row plan-history-row-card${archived ? " plan-history-row-archived" : ""}`}>
        <div className="plan-history-copy">
          <p className="label">{versionLabel}</p>
          <Link href={`/plans/${plan.plan_id}`}>
            <h2 className="plan-card-title">{planTitle}</h2>
          </Link>
          {inlineRenameForm}
          <div className="plan-card-meta">
            {plan.fight_date ? <span className="muted">{appText("text_1ef142c8213e")}{fightDateLabel}</span> : null}
            <span className="muted">{styleSummary}</span>
            <span className="muted">{appText("text_cfe0e6cbcf5c")}{createdLabel}</span>
          </div>
          {reviewReason ? <p className="muted">{reviewReason}</p> : null}
        </div>
        <div className="plan-history-meta">
          <span className={`badge${archived || completed ? " status-badge-neutral plan-archived-badge" : ""}`}>
            {active ? appText("text_630c2f1c0ee1") : archived ? appText("text_24e132330784") : completed ? appText("text_c48179f5246e") : statusLabel}
          </span>
          {!active && completed ? <span className="muted">{appText("text_a761ce901255")}</span> : null}
          {!active && !completed && !eligibleForActive ? <span className="muted">{appText("text_72c68b0adbc9")}</span> : null}
          <div className="plan-card-actions plans-history-actions">
            <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
              {archived ? appText("text_324b134f57c7") : appText("text_ed077f3d8125")}
            </Link>
            {archived ? (
              <Link href="/onboarding" className="ghost-button">
                {appText("text_255aec73f85a")}</Link>
            ) : null}
            {!archived && !active && eligibleForActive ? (
              <button type="button" className="secondary-button" onClick={() => void onSetActive(plan)} disabled={isActionPending || isRenaming}>
                {isSettingActive ? appText("text_48fcb6854990") : appText("text_24433c70eba5")}
              </button>
            ) : null}
            {!archived ? (
              <details className="plan-action-menu plans-history-menu">
                <summary className="ghost-button">{appText("text_5a23444828db")}</summary>
                <div className="plan-action-menu-popover">
                  <button type="button" className="ghost-button" onClick={handleRenameStart} disabled={isActionPending || isRenaming}>
                    {pendingAction === "rename" ? appText("text_dc85af8f2b1d") : isRenaming ? appText("text_3f698ede035f") : appText("text_3064d79a295c")}
                  </button>
                  <button type="button" className="ghost-button danger-button" onClick={handleDeleteRequest} disabled={isActionPending || isRenaming}>
                    {pendingAction === "delete" ? appText("text_6f3407113f07") : appText("text_66f4804ee23d")}
                  </button>
                </div>
              </details>
            ) : null}
          </div>
        </div>
        {message || (error && !isDeleteConfirmOpen) ? (
          <div className="plan-history-feedback">
            {message ? <div className="success-banner">{message}</div> : null}
            {error ? <div className="error-banner">{translateUiText(appText, error)}</div> : null}
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
    const appText = useAppTranslations("AppText");
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
          <p className="kicker">{appText("text_938ca3ac3e5b")}</p>
          <h2 id={`activate-conflict-title-${plan.plan_id}`} className="plan-dialog-title">
            {getPlanDisplayName(plan)}
          </h2>
        </div>
        <p id={`activate-conflict-body-${plan.plan_id}`} className="muted">
          {ACTIVE_PLAN_OVERLAP_MESSAGE}
        </p>
        <div className="plan-dialog-actions active-conflict-actions">
          <button
            type="button"
            className="secondary-button active-conflict-button active-conflict-button-primary"
            onClick={() => void onConfirm("replace")}
            disabled={isPending}
          >
            {appText("text_1ed300e8dd25")}</button>
          <button
            type="button"
            className="secondary-button active-conflict-button"
            onClick={() => void onConfirm("pause")}
            disabled={isPending}
          >
            {appText("text_e4442a988e6d")}</button>
          <button
            type="button"
            className="ghost-button active-conflict-button active-conflict-button-wide"
            onClick={onStartAfter}
            disabled={isPending}
          >
            {appText("text_a88e0234c719")}</button>
          <button
            type="button"
            className="ghost-button active-conflict-button active-conflict-button-cancel"
            onClick={onCancel}
            disabled={isPending}
          >
            {appText("text_19766ed6ccb2")}</button>
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
  compact = false,
}: {
  title: string;
  lines: SummaryLine[];
  emptyLabel: string;
  compact?: boolean;
}) {
  return (
    <div className={`plans-dashboard-summary${compact ? " plans-dashboard-summary-compact" : ""}`}>
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
    const appText = useAppTranslations("AppText");
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
      latestPlanLines.push({ label: "Status", value: formatAthletePlanStatus(plan.status) });
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
      setError(appText("text_95f5b7d0dc11"));
      return;
    }

    const currentName = plan.plan_name?.trim() || "";
    const normalizedName = renameDraft.trim();
    if (!normalizedName) {
      setError(appText("text_bee32f4af8c5"));
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
      showToast(appText("text_3884343b3c7f"), { tone: "success" });
      setIsRenaming(false);
    } catch (renameError) {
      const errorMessage = renameError instanceof Error ? renameError.message : "Unable to rename this plan.";
      if (errorMessage.includes("Unable to reach the server") || errorMessage.includes("502") || errorMessage.includes("503") || errorMessage.includes("504")) {
        setError(appText("text_c0ca548a25f7"));
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
      setError(appText("text_95f5b7d0dc11"));
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
        setError(appText("text_c0ca548a25f7"));
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
        {appText("text_58a73698329f")}</label>
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
            {pendingAction === "rename" ? appText("text_dc85af8f2b1d") : appText("text_1509f561f241")}
          </button>
          <button type="button" className="ghost-button" onClick={handleRenameCancel} disabled={isActionPending}>
            {appText("text_19766ed6ccb2")}</button>
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
            <p className="kicker">{appText("text_d35bfdc67670")}</p>
            <h2 id={`delete-latest-plan-title-${plan.plan_id}`} className="plan-dialog-title">
              {appText("text_66f4804ee23d")}{getPlanDisplayName(plan)}{appText("text_8a8de823d5ed")}</h2>
          </div>
          <p id={`delete-latest-plan-body-${plan.plan_id}`} className="muted">
            {appText("text_8affd0d4d884")}</p>
          {error ? <div className="error-banner">{translateUiText(appText, error)}</div> : null}
          <div className="plan-dialog-actions">
            <button type="button" className="ghost-button" onClick={handleDeleteDismiss} disabled={pendingAction === "delete"}>
              {appText("text_19766ed6ccb2")}</button>
            <button type="button" className="secondary-button" onClick={handleDeleteConfirm} disabled={pendingAction === "delete"}>
              {pendingAction === "delete" ? appText("text_6f3407113f07") : appText("text_66f4804ee23d")}
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
            <p className="kicker">{appText("text_340baae8d262")}</p>
            <h2>{plan ? getPlanDisplayName(plan) : appText("text_637ae3d9e272")}</h2>
            <p className="muted">
              {plan
                ? appText("text_55974c130fa6")
                : hasSavedIntake
                  ? appText("text_c081cb9060f3")
                  : appText("text_3cf62a8b076f")}
            </p>
            {!plan ? (
              <div className="empty-state-example plans-dashboard-empty-example">
                <p className="label">{appText("text_017fd22c1e13")}</p>
                <p className="empty-state-example-body">
                  {appText("text_c9aba0169e6e")}</p>
              </div>
            ) : null}
          </div>
          {plan?.status ? <span className="badge">{appText("text_630c2f1c0ee1")}</span> : null}
        </div>

        <DashboardSummary
          title={appText("text_6d3657e552a8")}
          lines={latestPlanLines}
          emptyLabel={appText("text_354ca0dd5314")}
          compact
        />

        {inlineRenameForm}

        <div className="plan-card-actions plans-dashboard-actions">
          {plan ? (
            <>
              <Link href={`/plans/${plan.plan_id}`} className="cta">
                {appText("text_9e70b18d5255")}</Link>
              <Link
                href={intake ? "/generate" : "/onboarding"}
                className="ghost-button"
                onClick={() => {
                  if (intake) {
                    markGenerationIntent();
                  }
                }}
              >
                {appText("text_7246e01bf5dc")}</Link>
              <details className="plan-action-menu plans-dashboard-management-actions">
                <summary className="ghost-button">{appText("text_5a23444828db")}</summary>
                <div className="plan-action-menu-popover">
                  <button type="button" className="ghost-button" onClick={handleRenameStart} disabled={isActionPending || isRenaming}>
                    {pendingAction === "rename" ? appText("text_dc85af8f2b1d") : isRenaming ? appText("text_3f698ede035f") : appText("text_3064d79a295c")}
                  </button>
                  <button type="button" className="ghost-button danger-button" onClick={handleDeleteRequest} disabled={isActionPending || isRenaming}>
                    {pendingAction === "delete" ? appText("text_6f3407113f07") : appText("text_66f4804ee23d")}
                  </button>
                </div>
              </details>
            </>
          ) : (
            <Link href={hasSavedIntake ? "/onboarding" : "/quick-build"} className="cta">
              {hasSavedIntake ? appText("text_f9f11b3f2f2f") : appText("text_004feb71bbd7")}
            </Link>
          )}
        </div>

        {error && !isDeleteConfirmOpen ? <div className="error-banner">{translateUiText(appText, error)}</div> : null}
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
    const appText = useAppTranslations("AppText");
  const profileLines = summarizeProfile(me);
  const intake = getIntakeSource(me);
  const intakeLines = summarizeIntake(me);
  const hasIntake = Boolean(intake);
  const sourceLines = [...profileLines.slice(1), ...intakeLines];

  return (
    <article className="list-card plans-dashboard-card plans-source-card">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">{appText("text_995d74d7974c")}</p>
          <h2>{translateUiText(appText, profileLines[0]?.value || "Athlete profile")}</h2>
          <p className="muted">{appText("text_e44c11f1b9b3")}</p>
        </div>
        <span className={`badge ${hasIntake ? "status-badge-success" : "status-badge-neutral"}`}>
          {hasIntake ? appText("text_d18ca7852333") : appText("text_28c8508c2541")}
        </span>
      </div>

      {sourceLines.length ? (
        <dl className="plans-source-facts">
          {sourceLines.map((line) => (
            <div key={line.label} className="plans-source-fact">
              <dt>{translateUiText(appText, line.label)}</dt>
              <dd>{translateUiText(appText, line.value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted">{appText("text_6576c97ed653")}</p>
      )}

      <div className="plan-card-actions plans-dashboard-actions">
        <Link href="/onboarding" className="ghost-button">
          {hasIntake ? appText("text_5fc7125dc9ec") : appText("text_5a0ddd65c6e3")}
        </Link>
      </div>
    </article>
  );
}

function PlansSyncState() {
    const appText = useAppTranslations("AppText");
  return (
    <article className="list-card plans-sync-card" aria-busy="true">
      <div className="plans-dashboard-card-header">
        <div className="plans-dashboard-card-copy">
          <p className="kicker">{appText("text_d138c7912580")}</p>
          <h2>{appText("text_88ceaccd4702")}</h2>
          <p className="muted">
            {appText("text_2a8a270db701")}</p>
        </div>
        <span className="badge status-badge-neutral">{appText("text_5c8b9e1ce0a2")}</span>
      </div>
      <div className="plans-sync-grid" aria-hidden="true">
        <div className="plans-sync-line plans-sync-line-short" />
        <div className="plans-sync-line" />
        <div className="plans-sync-line plans-sync-line-mid" />
      </div>
    </article>
  );
}

export default function PlansPage() {
    const appText = useAppTranslations("AppText");
  const t = useTranslations("Workspace");
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
  const explicitActivePlan = activePlanId ? visiblePlans.find((plan) => plan.plan_id === activePlanId) ?? null : null;
  const activePlan = explicitActivePlan && canSetActive(explicitActivePlan) ? explicitActivePlan : null;
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
      showToast(appText("text_77ce0f42e3ee"), { tone: "success" });
      await loadPlans();
      requestXpRefresh();
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
    showToast(appText("text_4aa20e49e701"), { tone: "success" });
    router.push("/onboarding");
  }

  const isPlanListLoading = isLoading;
  const isProfileLoading = !isMeHydrated;

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">{t("planDashboard")}</p>
            <h1>{t("planWorkspace")}</h1>
            <p className="muted">{t("planSummary")}</p>
          </div>
        </div>

        {error ? (
          <div className="error-banner athlete-motion-slot athlete-motion-status" role="alert">
            <span>{translateUiText(appText, error)}</span>
            {error.includes("Session expired") ? null : (
              <button
                type="button"
                className="error-banner-retry"
                onClick={() => void loadPlans()}
                disabled={isLoading}
              >
                {isLoading ? t("retrying") : t("retry")}
              </button>
            )}
          </div>
        ) : null}

        {!isLoading && heldForReviewPlans.length > 0 ? (
          <HeldPlansReviewNotice plans={heldForReviewPlans} />
        ) : null}

        <div className="plans-dashboard-stack athlete-motion-slot athlete-motion-main">
          {isPlanListLoading ? (
            <PlansSyncState />
          ) : (
            <LatestPlanCard
              plan={activePlan}
              intake={intakeSource}
              accessToken={session?.access_token ?? null}
              onPlanDeleted={handlePlanDeleted}
              onPlanRenamed={handlePlanRenamed}
            />
          )}
        </div>

        {isLoading ? (
          <div className="plans-history-block athlete-motion-slot athlete-motion-main" aria-busy="true">
            <div className="plans-history-header">
              <div className="plans-history-header-copy">
                <p className="kicker">{t("planManager")}</p>
                <h2>{t("syncingHistory")}</h2>
                <p className="muted">{t("savedVersions")}</p>
              </div>
              <span className="badge status-badge-neutral">{t("loading")}</span>
            </div>
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
                <p className="kicker">{t("planManager")}</p>
                <h2>{t("otherPlans")}</h2>
                <p className="muted">{t("comparePlans")}</p>
              </div>
              {archivedPlans.length ? (
                <button
                  type="button"
                  className={`plans-history-toggle ${isArchiveOpen ? "plans-history-toggle-open" : ""}`.trim()}
                  onClick={() => setIsArchiveOpen((current) => !current)}
                  aria-expanded={isArchiveOpen}
                  aria-controls="plans-history-dropdown"
                  aria-label={isArchiveOpen ? appText("text_b23f8f717e99") : appText("text_b2f59ebc6326")}
                >
                  <span className="plans-history-toggle-copy">
                    {isArchiveOpen ? t("hideArchive") : t("viewArchive")}
                  </span>
                  <span className="plans-history-toggle-meta">
                    <span className="plans-history-toggle-count">{archiveCountLabel}</span>
                    <span className="custom-select-chevron" aria-hidden="true" />
                  </span>
                </button>
              ) : (
                <span className="badge status-badge-neutral">{t("noEarlierPlans")}</span>
              )}
            </div>

            {/* Archive expands directly under its toggle so opening/closing it is
                visible right where the control is — not appended far below the
                always-shown recent plans, where it read as "not working". */}
            {archivedPlans.length > 0 && isArchiveOpen ? (
              <div id="plans-history-dropdown" className="plans-history-dropdown" role="region" aria-label={t("olderPlans")}>
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
              <p className="muted">{appText("text_313749b7f694")}</p>
            )}
          </div>
        ) : null}

        <div className="plans-source-block athlete-motion-slot athlete-motion-main">
          {isProfileLoading ? <PlansFeaturedSkeleton /> : <IntakeCard me={me} />}
        </div>

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
