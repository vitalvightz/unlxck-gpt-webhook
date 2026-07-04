"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useId, useMemo, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import {
  BodyMap,
  type BodyMapSelection,
  type BodyMapSeverity,
  type BodyMapSide,
} from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { Skeleton } from "@/components/skeleton";
import {
  DaySessionContext,
  SessionCard as StructuredSessionCard,
  SessionlessDayCard,
} from "@/components/structured-plan-renderer";
import { useToast } from "@/components/toast-provider";
import { EffortSlider, FaceScale } from "@/components/rating-controls";
import { SafetyNote } from "@/components/safety-note";
import { TODAY_RED_FLAG_SAFETY } from "@/lib/safety-copy";
import {
  getPlan,
  getToday,
  submitTodayCheckin,
  submitTodayInjuryCheckin,
  submitTodaySessionCompletion,
} from "@/lib/api";
import {
  resolveCurrentDay,
  sessionIdentity,
  type CurrentDayResolution,
} from "@/lib/camp-map";
import { formatAppDate } from "@/lib/date-format";
import { normalizeInjuryLabel } from "@/lib/injury-display";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { useTrainingDay } from "@/lib/use-training-day";
import {
  TODAY_EMPTY_TEXT,
  TODAY_EMPTY_TITLE,
  buildTodayCheckinPayload,
  canCompleteTodaySession,
  completionRequiresModificationReason,
  completionRequiresReviewFields,
  getCompletionLabel,
  getRecommendationCopy,
  getSessionFocus,
  getSessionTitle,
  getTodayDecisionBanner,
  getVisibleRiskWatch,
  hasActivePlan,
  hasTodaySession,
  resolveSessionFocusDate,
  shouldShowTodayCheckin,
} from "@/lib/today";
import type {
  InjuryFlagRecord,
  InjuryFlagSeverity,
  StructuredPlan,
  TodayActiveInjury,
  TodayActivePlan,
  TodayCheckinBody,
  TodayCheckinPain,
  TodayCheckinSleep,
  TodayCommandView,
  TodayCompletionStatus,
  TodayInjuryCheckinStatus,
  TodayInjuryDeclaration,
  TodayPreviousSession,
  TodayRecommendationState,
  TodaySession,
} from "@/lib/types";

const SLEEP_OPTIONS: Array<{ value: TodayCheckinSleep; label: string }> = [
  { value: "poor", label: "Poor" },
  { value: "okay", label: "Okay" },
  { value: "good", label: "Good" },
];

const BODY_OPTIONS: Array<{ value: TodayCheckinBody; label: string }> = [
  { value: "flat", label: "Flat" },
  { value: "normal", label: "Normal" },
  { value: "sharp", label: "Sharp" },
];

const PAIN_OPTIONS: Array<{ value: TodayCheckinPain; label: string }> = [
  { value: "none", label: "None" },
  { value: "manageable", label: "Manageable" },
  { value: "high", label: "High" },
];

const ACTIVE_INJURY_OPTIONS: Array<{ value: TodayActiveInjury; label: string }> = [
  { value: "none", label: "None" },
  { value: "stable", label: "Stable" },
  { value: "worse", label: "Worse" },
];

const PREVIOUS_SESSION_OPTIONS: Array<{ value: TodayPreviousSession; label: string }> = [
  { value: "none", label: "N/A" },
  { value: "normal", label: "Normal" },
  { value: "very_hard", label: "Very hard" },
];

const SAFETY_FLAGS: Array<{ key: keyof TodaySafetyFlags; label: string }> = [
  { key: "sharp_pain", label: "Sharp pain" },
  { key: "instability", label: "Instability" },
  { key: "swelling", label: "Swelling" },
  { key: "neurological_symptoms", label: "Neurological symptoms" },
  { key: "illness_symptoms", label: "Illness symptoms" },
  { key: "cannot_warm_into_movement", label: "Cannot warm into movement" },
  { key: "worse_next_day_pain", label: "Worse next-day pain" },
];

type TodaySafetyFlags = {
  sharp_pain: boolean;
  instability: boolean;
  swelling: boolean;
  neurological_symptoms: boolean;
  illness_symptoms: boolean;
  cannot_warm_into_movement: boolean;
  worse_next_day_pain: boolean;
};

type CompletionIntent = Extract<TodayCompletionStatus, "done" | "modified" | "skipped"> | null;

function formatTrainingDay(value: string | null | undefined): string {
  if (!value) {
    return "Today";
  }
  return formatAppDate(value);
}

function formatSessionDate(session: TodaySession): string {
  const dayText = session.weekday_with_label || session.weekday;
  const countdown =
    typeof session.d_day === "number" ? `D-${Math.abs(session.d_day)}` : session.day_label;
  // The canonical date already carries the short weekday, so only fall back to
  // the raw weekday token when there's no calendar date to format.
  const dayPart = session.calendar_date ? formatTrainingDay(session.calendar_date) : dayText;
  const hasCountdownInDayPart = Boolean(dayPart && countdown && dayPart.includes(countdown));
  const parts = [dayPart, hasCountdownInDayPart ? null : countdown].filter(Boolean);
  return parts.length ? parts.join(" / ") : "Athlete-local training day";
}

function getSessionDuration(session: TodaySession): string | null {
  if (typeof session.estimated_duration === "string" && session.estimated_duration.trim()) {
    return session.estimated_duration.trim();
  }
  if (typeof session.estimated_duration === "number" && Number.isFinite(session.estimated_duration)) {
    return `${session.estimated_duration} min`;
  }
  if (typeof session.duration_minutes === "number" && Number.isFinite(session.duration_minutes)) {
    return `${session.duration_minutes} min`;
  }
  if (session.planned_duration?.display) {
    return session.planned_duration.display;
  }
  if (typeof session.planned_duration?.value === "number") {
    return `${session.planned_duration.value} ${session.planned_duration.unit || "min"}`;
  }
  return null;
}

function textValue(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

function getStructuredTodaySessionTitle(current: CurrentDayResolution): string {
  const session = current.sessions[0];
  const card = current.day?.today_card;
  return (
    textValue(session?.title) ||
    textValue(card?.headline) ||
    humanizeIfRawEnum(textValue(session?.session_type))
  );
}

function getSessionRelationCopy(
  session: TodaySession,
  completionStatus: TodayCompletionStatus,
): {
  kicker: string;
  status: string;
  helper: string;
} {
  // The backend owns "today vs next" via session_relation, so trust it rather
  // than re-deriving it from the structured plan — that mismatch is what left the
  // card stuck on the completed day while the header already read "Next session".
  if (session.session_relation === "next") {
    const loggedToday =
      completionStatus === "done" ||
      completionStatus === "modified" ||
      completionStatus === "skipped";
    return {
      kicker: "Next scheduled session",
      status: "Preview",
      helper: loggedToday
        ? "Today's session is logged, so this shows your next scheduled session."
        : "Today has no matched training card, so this shows the next available plan day.",
    };
  }
  return {
    kicker: "Today's session",
    status: "Live today",
    helper: "Matched from the active plan by the athlete-local training day.",
  };
}

function SegmentGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="today-field-group">
      <p className="today-field-label">{label}</p>
      <div className="today-segment-row">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={option.value === value ? "today-segment today-segment-active" : "today-segment"}
            aria-pressed={option.value === value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function TodayLoadingState() {
  return (
    <section className="panel today-shell" aria-busy="true">
      <Skeleton variant="text" width={120} />
      <Skeleton variant="text" width="70%" height={42} />
      <Skeleton variant="block" height={180} />
      <Skeleton variant="block" height={220} />
    </section>
  );
}

function NoActivePlanState() {
  return (
    <section className="panel today-shell today-empty-state">
      <div className="today-hero-copy">
        <p className="kicker">Today</p>
        <h1>{TODAY_EMPTY_TITLE}</h1>
        <p className="muted">{TODAY_EMPTY_TEXT}</p>
      </div>
      <div className="today-action-row">
        <Link href="/intake" className="cta">
          Complete Intake
        </Link>
      </div>
    </section>
  );
}

function TodayReadinessStrip({
  needsCheckin,
  openInjuryCount,
  completionStatus,
}: {
  needsCheckin: boolean;
  openInjuryCount: number;
  completionStatus: TodayCompletionStatus;
}) {
  const injuryLabel = openInjuryCount
    ? `${openInjuryCount} active injur${openInjuryCount === 1 ? "y" : "ies"}`
    : "No active injuries";

  return (
    <dl className="today-readiness-strip" aria-label="Today command status">
      <div>
        <dt>Check-in</dt>
        <dd>{needsCheckin ? "Due" : "Logged"}</dd>
      </div>
      <div data-tone={openInjuryCount ? "risk" : "clear"}>
        <dt>Injury</dt>
        <dd>{injuryLabel}</dd>
      </div>
      <div>
        <dt>Session</dt>
        <dd>{getCompletionLabel(completionStatus)}</dd>
      </div>
    </dl>
  );
}

function RiskWatch({ risks }: { risks: TodayCommandView["risk_watch"] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const overflowId = useId();
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
  const overflowRisks = risks.slice(visible.length);
  return (
    <section className="today-risk-watch" aria-label="Risk watch">
      {visible.map((risk) => (
        <article key={`${risk.category}-${risk.label}`} className="today-risk-item" data-tone={risk.tone}>
          <span className="today-risk-icon" aria-hidden="true">
            !
          </span>
          <div>
            <p className="today-risk-label">{risk.label}</p>
            <p className="today-risk-text">{risk.text || "Monitor this before training."}</p>
          </div>
        </article>
      ))}
      {isExpanded ? (
        <div id={overflowId} className="today-risk-overflow">
          {overflowRisks.map((risk) => (
            <article key={`${risk.category}-${risk.label}`} className="today-risk-item" data-tone={risk.tone}>
              <span className="today-risk-icon" aria-hidden="true">
                !
              </span>
              <div>
                <p className="today-risk-label">{risk.label}</p>
                <p className="today-risk-text">{risk.text || "Monitor this before training."}</p>
              </div>
            </article>
          ))}
        </div>
      ) : null}
      {overflow > 0 ? (
        <button
          type="button"
          className="today-risk-more"
          aria-controls={overflowId}
          aria-expanded={isExpanded}
          data-expanded={isExpanded ? "true" : "false"}
          onClick={() => setIsExpanded((current) => !current)}
        >
          {isExpanded ? "Show less" : `+${overflow} more`}
        </button>
      ) : null}
    </section>
  );
}

function CheckinModule({
  plan,
  token,
  warnings,
  onRefresh,
}: {
  plan: TodayActivePlan;
  token: string;
  warnings?: string[];
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [sleep, setSleep] = useState<TodayCheckinSleep>("good");
  const [body, setBody] = useState<TodayCheckinBody>("normal");
  const [pain, setPain] = useState<TodayCheckinPain>("none");
  const [activeInjury, setActiveInjury] = useState<TodayActiveInjury>("none");
  const [previousSession, setPreviousSession] = useState<TodayPreviousSession>("none");
  const [safetyFlags, setSafetyFlags] = useState<TodaySafetyFlags>({
    sharp_pain: false,
    instability: false,
    swelling: false,
    neurological_symptoms: false,
    illness_symptoms: false,
    cannot_warm_into_movement: false,
    worse_next_day_pain: false,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!plan.id || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await submitTodayCheckin(
        token,
        buildTodayCheckinPayload({
          planId: plan.id,
          phase: plan.phase,
          sleep,
          body,
          pain,
          activeInjury,
          previousSession,
          safetyFlags,
        }),
      );
      showToast(`Recommendation: ${getRecommendationCopy(response.recommendation_state).label}.`, {
        tone: response.recommendation_state === "pull_back" ? "info" : "success",
      });
      if (response.warnings?.length) {
        showToast(response.warnings[0], { tone: "info" });
      }
      await onRefresh();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Check-in failed.", { tone: "error" });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="today-card today-checkin-card" aria-labelledby="today-checkin-heading">
      <div className="today-card-head">
        <div>
          <p className="kicker">Fast check-in</p>
          <h2 id="today-checkin-heading">Set today&apos;s recommendation</h2>
        </div>
      </div>
      <form className="today-checkin-form" onSubmit={handleSubmit}>
        <SegmentGroup label="Sleep" value={sleep} options={SLEEP_OPTIONS} onChange={setSleep} />
        <SegmentGroup label="Body" value={body} options={BODY_OPTIONS} onChange={setBody} />
        <SegmentGroup label="Pain" value={pain} options={PAIN_OPTIONS} onChange={setPain} />
        <SegmentGroup
          label="Active injury"
          value={activeInjury}
          options={ACTIVE_INJURY_OPTIONS}
          onChange={setActiveInjury}
        />
        <SegmentGroup
          label="Previous session"
          value={previousSession}
          options={PREVIOUS_SESSION_OPTIONS}
          onChange={setPreviousSession}
        />
        {warnings?.length ? (
          <p className="today-inline-warning" role="status">{warnings[0]}</p>
        ) : null}

        <details className="today-red-flags">
          <summary>Any red flags?</summary>
          <SafetyNote tone="warning">{TODAY_RED_FLAG_SAFETY}</SafetyNote>
          <div className="today-flag-grid">
            {SAFETY_FLAGS.map((flag) => (
              <label key={flag.key} className="today-flag-option">
                <input
                  type="checkbox"
                  checked={safetyFlags[flag.key]}
                  onChange={(event) =>
                    setSafetyFlags((current) => ({
                      ...current,
                      [flag.key]: event.target.checked,
                    }))
                  }
                />
                <span>{flag.label}</span>
              </label>
            ))}
          </div>
        </details>

        <button type="submit" className="cta today-primary-action" disabled={isSubmitting}>
          {isSubmitting ? "Submitting..." : "Submit check-in"}
        </button>
      </form>
    </section>
  );
}

const INJURY_STATUS_ACTIONS: Array<{ value: TodayInjuryCheckinStatus; label: string }> = [
  { value: "improving", label: "Easing" },
  { value: "ongoing", label: "Same" },
  { value: "worse", label: "Worse" },
  { value: "resolved", label: "Cleared" },
];

const INJURY_SEVERITY_OPTIONS: Array<{ value: InjuryFlagSeverity; label: string }> = [
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
];

const BODY_MAP_SEVERITY_BY_FLAG: Record<InjuryFlagSeverity, BodyMapSeverity> = {
  mild: "low",
  moderate: "moderate",
  severe: "high",
};

const BODY_MAP_VISIBILITY_OPTIONS = [
  { value: "shown", label: "Show" },
  { value: "hidden", label: "Hide" },
];

function cycleInjuryFlagSeverity(severity: InjuryFlagSeverity): InjuryFlagSeverity {
  if (severity === "mild") {
    return "moderate";
  }
  if (severity === "moderate") {
    return "severe";
  }
  return "mild";
}

function getInjuryLabel(injury: InjuryFlagRecord): string {
  // Prefer the server-computed label (built from the shared injury synonym
  // logic) so the card matches the reminder and never re-parses raw words.
  const serverLabel = injury.label?.trim();
  if (serverLabel) {
    return serverLabel;
  }
  const raw = injury.body_area?.trim() || injury.description?.trim();
  return normalizeInjuryLabel(raw) || "Injury";
}

/**
 * Daily injury check-in. Each open injury can be marked easing / same / worse /
 * resolved (a per-injury update), and new injuries can be added. Writes reconcile
 * the athlete's injury_flags server-side so a resolved injury clears and a new one
 * is tracked — the data the dynamic plan engine will later read. It also feeds the
 * risk watch, so the badge stays live while any injury is open.
 */
function InjuryCheckinCard({
  openInjuries,
  token,
  onRefresh,
}: {
  openInjuries: InjuryFlagRecord[];
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [pendingFlagId, setPendingFlagId] = useState<string | null>(null);
  const [selectedStatusByFlagId, setSelectedStatusByFlagId] = useState<
    Partial<Record<string, TodayInjuryCheckinStatus>>
  >({});
  // Clearing an injury removes it from tracking, so it asks for an explicit
  // confirmation first; this holds the flag id awaiting that "are you sure?".
  const [confirmingClearId, setConfirmingClearId] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [newArea, setNewArea] = useState("");
  const [newSeverity, setNewSeverity] = useState<InjuryFlagSeverity>("moderate");
  const [newZone, setNewZone] = useState("");
  const [bodyMapVisibility, setBodyMapVisibility] = useState<"shown" | "hidden">("hidden");
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
  const bodyMapVisibilityId = useId();
  const newInjurySelections: BodyMapSelection[] = newArea.trim()
    ? [
        {
          zone: newZone || undefined,
          label: newArea.trim(),
          severity: BODY_MAP_SEVERITY_BY_FLAG[newSeverity],
        },
      ]
    : [];

  async function submit(injuries: TodayInjuryDeclaration[]) {
    await submitTodayInjuryCheckin(token, { injuries });
    await onRefresh();
  }

  async function updateInjury(flagId: string, status: TodayInjuryCheckinStatus) {
    if (pendingFlagId) {
      return;
    }
    setPendingFlagId(flagId);
    setSelectedStatusByFlagId((current) => ({ ...current, [flagId]: status }));
    try {
      await submit([{ flag_id: flagId, status }]);
      showToast(status === "resolved" ? "Injury cleared." : "Injury updated.", {
        tone: "success",
      });
    } catch (error) {
      setSelectedStatusByFlagId((current) => {
        const next = { ...current };
        delete next[flagId];
        return next;
      });
      showToast(error instanceof Error ? error.message : "Injury update failed.", { tone: "error" });
    } finally {
      setPendingFlagId(null);
    }
  }

  // "Easing" / "Same" / "Worse" apply straight away; "Cleared" routes through an
  // inline confirmation because it removes the injury from tracking.
  function handleInjuryAction(flagId: string, status: TodayInjuryCheckinStatus) {
    if (status === "resolved") {
      setConfirmingClearId(flagId);
      return;
    }
    void updateInjury(flagId, status);
  }

  async function confirmClear(flagId: string) {
    await updateInjury(flagId, "resolved");
    setConfirmingClearId(null);
  }

  async function addInjury(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const area = newArea.trim();
    if (!area || isAdding) {
      return;
    }
    setIsAdding(true);
    try {
      await submit([{ body_area: area, severity: newSeverity, status: "ongoing" }]);
      setNewArea("");
      setNewSeverity("moderate");
      setNewZone("");
      showToast("Injury added.", { tone: "success" });
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not add injury.", { tone: "error" });
    } finally {
      setIsAdding(false);
    }
  }

  function selectBodyMapZone(zone: string, label: string) {
    const sameZone = newZone === zone;
    setNewZone(zone);
    if (!sameZone || !newArea.trim()) {
      setNewArea(label);
    }
    setNewSeverity((current) => (sameZone ? cycleInjuryFlagSeverity(current) : "mild"));
  }

  return (
    <section className="today-card today-injury-card" aria-labelledby="today-injury-heading">
      <div className="today-card-head">
        <div>
          <p className="kicker">Injury check-in</p>
          <h2 id="today-injury-heading">Track today&apos;s injuries</h2>
        </div>
      </div>
      {openInjuries.length ? (
        <ul className="today-injury-list">
          {openInjuries.map((injury) => {
            const selectedStatus = selectedStatusByFlagId[injury.id];
            const isPending = pendingFlagId === injury.id;

            return (
              <li key={injury.id} className="today-injury-item" data-severity={injury.severity}>
                <div className="today-injury-meta">
                  <span className="today-injury-name">{getInjuryLabel(injury)}</span>
                  <span className="badge status-badge-neutral">{injury.severity}</span>
                  {injury.status === "monitoring" ? <span className="badge">Monitoring</span> : null}
                </div>
                <div className="today-segment-row" role="group" aria-label={`Update ${getInjuryLabel(injury)}`}>
                  {INJURY_STATUS_ACTIONS.map((action) => {
                    const activeStatus = confirmingClearId === injury.id ? "resolved" : selectedStatus;
                    const isSelected = action.value === activeStatus;

                    return (
                      <button
                        key={action.value}
                        type="button"
                        className={`today-segment${isSelected ? " today-segment-active" : ""}`}
                        disabled={isPending}
                        aria-pressed={isSelected}
                        onClick={() => handleInjuryAction(injury.id, action.value)}
                      >
                        {action.label}
                      </button>
                    );
                  })}
                </div>
                {confirmingClearId === injury.id ? (
                  <div
                    className="today-injury-confirm"
                    role="alertdialog"
                    aria-label={`Clear ${getInjuryLabel(injury)}?`}
                  >
                    <span className="today-injury-confirm-text">
                      Clear this injury? It will be removed from today&apos;s tracking.
                    </span>
                    <div className="today-injury-confirm-actions">
                      <button
                        type="button"
                        className="today-injury-confirm-yes"
                        disabled={pendingFlagId !== null}
                        onClick={() => void confirmClear(injury.id)}
                      >
                        {pendingFlagId === injury.id ? "Clearing..." : "Yes, clear"}
                      </button>
                      <button
                        type="button"
                        className="today-injury-confirm-cancel"
                        disabled={pendingFlagId !== null}
                        onClick={() => setConfirmingClearId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">No injuries are being tracked. Add one below if something is bothering you.</p>
      )}

      <form className="today-injury-add" onSubmit={addInjury}>
        <div className="today-injury-add-toolbar">
          <p className="today-injury-add-title">Add injury</p>
          <div className="field today-injury-map-control">
            <label htmlFor={bodyMapVisibilityId}>Body map</label>
            <CustomSelect
              id={bodyMapVisibilityId}
              value={bodyMapVisibility}
              options={BODY_MAP_VISIBILITY_OPTIONS}
              placeholder="Body map"
              onChange={(value) => setBodyMapVisibility(value === "hidden" ? "hidden" : "shown")}
            />
          </div>
        </div>
        {bodyMapVisibility === "shown" ? (
          <BodyMap
            side={bodyMapSide}
            selections={newInjurySelections}
            onZoneSelect={selectBodyMapZone}
            onSideChange={setBodyMapSide}
          />
        ) : null}
        {newArea.trim() ? (
          <div className="today-injury-selection" aria-live="polite">
            <span>Selected</span>
            <strong>{newArea.trim()}</strong>
            <small>Tap the same zone to raise severity.</small>
          </div>
        ) : null}
        <label className="field" htmlFor="today-injury-area">
          <span className="sr-only">Add injury</span>
          <input
            id="today-injury-area"
            value={newArea}
            maxLength={200}
            placeholder="e.g. left shoulder bruise"
            onChange={(event) => {
              const value = event.target.value;
              setNewArea(value);
              if (!value.trim()) {
                setNewZone("");
              }
            }}
          />
        </label>
        <SegmentGroup
          label="Severity"
          value={newSeverity}
          options={INJURY_SEVERITY_OPTIONS}
          onChange={setNewSeverity}
        />
        <button
          type="submit"
          className="secondary-button"
          disabled={isAdding || !newArea.trim()}
        >
          {isAdding ? "Adding..." : "Add injury"}
        </button>
      </form>
    </section>
  );
}

function CompletionForm({
  intent,
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  intent: CompletionIntent;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (payload: {
    sessionRpe: number | null;
    painAfter: number | null;
    modificationReason: string;
    notes: string;
  }) => Promise<void>;
}) {
  const [sessionRpe, setSessionRpe] = useState<number | null>(null);
  const [painAfter, setPainAfter] = useState<number | null>(null);
  const [modificationReason, setModificationReason] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!intent) {
    return null;
  }

  const activeIntent = intent;
  const needsReviewFields = completionRequiresReviewFields(activeIntent);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (completionRequiresModificationReason(activeIntent) && !modificationReason.trim()) {
      setError("Modified sessions need a reason.");
      return;
    }
    if (needsReviewFields && (sessionRpe === null || painAfter === null)) {
      setError("Add session RPE and pain-after before saving.");
      return;
    }
    await onSubmit({
      sessionRpe,
      painAfter,
      modificationReason: modificationReason.trim(),
      notes: notes.trim(),
    });
  }

  return (
    <form className="today-completion-form" onSubmit={handleSubmit}>
      {needsReviewFields ? (
        <div className="today-completion-fields">
          <div className="field">
            <span>Session effort</span>
            <EffortSlider
              id="today-session-rpe"
              ariaLabel="Session effort"
              value={sessionRpe}
              onChange={setSessionRpe}
            />
          </div>
          <div className="field">
            <span>Pain after</span>
            <FaceScale value={painAfter} onChange={setPainAfter} />
          </div>
        </div>
      ) : null}
      {completionRequiresModificationReason(activeIntent) ? (
        <label className="field" htmlFor="today-modification-reason">
          <span>Modification reason</span>
          <input
            id="today-modification-reason"
            value={modificationReason}
            maxLength={2000}
            onChange={(event) => setModificationReason(event.target.value)}
          />
        </label>
      ) : null}
      <label className="field" htmlFor="today-session-notes">
        <span>Notes {intent === "skipped" ? "(optional)" : ""}</span>
        <input
          id="today-session-notes"
          value={notes}
          maxLength={2000}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      {error ? <p className="today-inline-error" role="alert">{error}</p> : null}
      <div className="today-action-row">
        <button type="submit" className="cta" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : `Save ${getCompletionLabel(intent).toLowerCase()}`}
        </button>
        <button type="button" className="ghost-button" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/**
 * Compact train/modify/pull-back banner shown above today's blocks once the
 * athlete has checked in. Returns null before check-in. It frames the original
 * blocks — it never mutates the saved plan.
 */
function DecisionBanner({
  state,
  reason,
}: {
  state: TodayRecommendationState;
  reason?: string | null;
}) {
  const banner = getTodayDecisionBanner(state, reason);
  if (!banner) {
    return null;
  }
  const icon = getRecommendationCopy(state).icon;
  return (
    <div className="today-decision-banner" data-tone={banner.tone} role="status">
      <span className="today-decision-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="today-decision-body">
        <p className="today-decision-title">{banner.title}</p>
        <p className="today-decision-detail">{banner.detail}</p>
        {state === "pull_back" ? (
          <p className="today-decision-safety">
            If pain escalates or red flags appear, stop and switch to recovery work.
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Today's exact blocks, resolved from the active plan's structured_plan via the
 * same shared resolver and the same SessionCard component Plan Detail renders.
 * This guarantees Today and Plan Detail agree on the current day, its sessions
 * and their counts — Today simply scopes the view to today's day only (no week
 * strip, no other days, no full camp map).
 */
function TodaySessionBlocks({
  planId,
  current,
}: {
  planId?: string;
  current: CurrentDayResolution;
}) {
  if (!current.inRange || !current.day) {
    return null;
  }
  if (current.sessions.length === 0) {
    return (
      <div className="today-blocks">
        <SessionlessDayCard day={current.day} />
      </div>
    );
  }
  return (
    <div className="today-blocks">
      <DaySessionContext day={current.day} />
      {current.sessions.map((session, index) => (
        <StructuredSessionCard
          key={sessionIdentity({
            planId,
            weekPos: current.weekPos ?? 0,
            dayPos: current.dayPos ?? 0,
            sessionPos: index,
            week: current.week,
            day: current.day,
            session,
          })}
          session={session}
          day={index === 0 ? current.day ?? undefined : undefined}
          defaultOpenBlocks
          showDayContext={false}
        />
      ))}
    </div>
  );
}

function SessionCard({
  state,
  structuredPlan,
  token,
  onRefresh,
}: {
  state: TodayCommandView;
  structuredPlan: StructuredPlan | null;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [intent, setIntent] = useState<CompletionIntent>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const session = state.today.next_session;
  const status = state.today.completion_status;
  const duration = getSessionDuration(session);
  const hasSession = hasTodaySession(session);
  // Resolve today's day/session from the structured plan through the shared
  // 04:00 rollover, exactly as Plan Detail does. These blocks — not the backend
  // session summary — are the "what exact blocks apply today" answer. The
  // training day comes from the client-mounted hook (SSR-safe, null until mount)
  // and is resolved on every render so a long-lived tab follows the rollover
  // instead of sticking on a memoized day.
  const trainingDay = useTrainingDay();
  // Center the structured blocks on whatever the backend command view targets:
  // today's day in the normal case, or the NEXT scheduled session's day once
  // today is logged / carries no app card (session_relation === "next"). Resolving
  // by that target day — not the bare calendar day — stops the card from sticking
  // on the finished session while the header has already advanced to "Next
  // scheduled session", which is exactly how Overview already behaves.
  const focusDate = resolveSessionFocusDate(trainingDay, session);
  const current = resolveCurrentDay(structuredPlan, focusDate);
  const showStructuredBlocks = current.inRange && Boolean(current.day);
  const hasResolvedDaySessions = current.inRange && current.sessions.length > 0;
  const isNextSessionPreview = session.session_relation === "next";
  const relationCopy = getSessionRelationCopy(session, status);
  const canCompleteSession = canCompleteTodaySession(session) && !isNextSessionPreview;
  const recommendationState = state.today.recommendation_state;
  // Tint the session card to match today's decision (green/amber/red) so the page
  // reads at a glance instead of being a wall of identical dark cards. Neutral
  // (not-checked-in) carries no tone — the card stays default until check-in.
  const recommendationTone = getRecommendationCopy(recommendationState).tone;
  const cardTone =
    recommendationTone === "green" ||
    recommendationTone === "amber" ||
    recommendationTone === "red"
      ? recommendationTone
      : undefined;

  async function saveCompletion(
    nextStatus: TodayCompletionStatus,
    details: {
      sessionRpe?: number | null;
      painAfter?: number | null;
      modificationReason?: string;
      notes?: string;
    } = {},
  ) {
    if (!state.active_plan.id || !session.session_id || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    try {
      await submitTodaySessionCompletion(token, {
        plan_id: state.active_plan.id,
        session_id: session.session_id,
        status: nextStatus,
        session_rpe: details.sessionRpe ?? null,
        pain_after: details.painAfter ?? null,
        modification_reason: details.modificationReason ?? "",
        notes: details.notes ?? "",
      });
      setIntent(null);
      showToast(getCompletionLabel(nextStatus), { tone: "success" });
      await onRefresh();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Session update failed.", { tone: "error" });
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!hasSession) {
    return (
      <section
        id="today-session"
        className="today-card today-session-card"
        data-tone={cardTone}
        aria-labelledby="today-session-heading"
      >
        <div className="today-card-head">
          <div>
            <p className="kicker">Today&apos;s session</p>
            {/* training_day is always present in the initial payload, so headline
                it unconditionally — gating on the async-loaded structuredPlan
                caused a flash from "No session scheduled" to the date on load. */}
            <h2 id="today-session-heading">
              {formatTrainingDay(state.today.training_day)}
            </h2>
          </div>
        </div>
        <DecisionBanner state={recommendationState} reason={state.today.recommendation_reason} />
        {showStructuredBlocks ? (
          <TodaySessionBlocks planId={state.active_plan?.id} current={current} />
        ) : (
          <p className="muted">No active plan card matched today. Use View full plan to find the next training target.</p>
        )}
      </section>
    );
  }

  const sessionTitle = hasResolvedDaySessions
    ? getStructuredTodaySessionTitle(current) || getSessionTitle(session)
    : getSessionTitle(session);
  // Avoid the "Today's session / Today's session" stutter: when the session has
  // no real name and falls back to the generic title that already matches the
  // kicker, headline the training day instead so the eyebrow and heading differ.
  const headline =
    sessionTitle.trim().toLowerCase() === "today's session" ||
    sessionTitle.trim().toLowerCase() === relationCopy.kicker.trim().toLowerCase()
      ? formatSessionDate(session)
      : sessionTitle;

  return (
    <section
      id="today-session"
      className="today-card today-session-card"
      data-tone={cardTone}
      aria-labelledby="today-session-heading"
    >
      <div className="today-card-head">
        <div>
          <p className="kicker">{relationCopy.kicker}</p>
          <h2 id="today-session-heading">{headline}</h2>
        </div>
      </div>
      <DecisionBanner state={recommendationState} reason={state.today.recommendation_reason} />
      {showStructuredBlocks ? (
        <TodaySessionBlocks planId={state.active_plan?.id} current={current} />
      ) : (
        <div className="today-session-summary">
          <div>
            <p className="today-detail-label">Day</p>
            <p>{formatSessionDate(session)}</p>
          </div>
          <div>
            <p className="today-detail-label">Focus</p>
            <p>{getSessionFocus(session)}</p>
          </div>
          {session.coach_led_contact ? (
            <div>
              <p className="today-detail-label">Coach contact</p>
              <p>{session.coach_led_contact}</p>
            </div>
          ) : null}
          {duration ? (
            <div>
              <p className="today-detail-label">Duration</p>
              <p>{duration}</p>
            </div>
          ) : null}
          <div>
            <p className="today-detail-label">Status</p>
            <p>{isNextSessionPreview ? relationCopy.status : getCompletionLabel(status)}</p>
          </div>
        </div>
      )}

      {!canCompleteSession ? (
        <p className="today-terminal-status">
          {isNextSessionPreview
            ? `${relationCopy.helper} Completion opens on the matched training day.`
            : "Session details available, but completion is unavailable for this entry."}
        </p>
      ) : null}

      {canCompleteSession && status === "not_started" ? (
        <div className="today-action-row today-sticky-actions">
          <button type="button" className="cta" onClick={() => void saveCompletion("started")} disabled={isSubmitting}>
            Start session
          </button>
          <button type="button" className="ghost-button" onClick={() => setIntent("skipped")} disabled={isSubmitting}>
            Mark skipped
          </button>
        </div>
      ) : null}

      {canCompleteSession && status === "started" ? (
        <div className="today-action-row today-sticky-actions">
          <button
            type="button"
            className="cta"
            onClick={() => showToast("Session is in progress.", { tone: "info" })}
            disabled={isSubmitting}
          >
            Resume session
          </button>
          <button type="button" className="secondary-button" onClick={() => setIntent("done")} disabled={isSubmitting}>
            Mark done
          </button>
          <button type="button" className="secondary-button" onClick={() => setIntent("modified")} disabled={isSubmitting}>
            Mark modified
          </button>
          <button type="button" className="ghost-button" onClick={() => setIntent("skipped")} disabled={isSubmitting}>
            Mark skipped
          </button>
        </div>
      ) : null}

      {canCompleteSession && (status === "done" || status === "modified" || status === "skipped") ? (
        <p className="today-terminal-status">{getCompletionLabel(status)}</p>
      ) : null}

      {canCompleteSession ? (
        <CompletionForm
          intent={intent}
          isSubmitting={isSubmitting}
          onCancel={() => setIntent(null)}
          onSubmit={(details) =>
            saveCompletion(intent ?? "skipped", {
              sessionRpe: details.sessionRpe,
              painAfter: details.painAfter,
              modificationReason: details.modificationReason,
              notes: details.notes,
            })
          }
        />
      ) : null}
    </section>
  );
}

export function TodayScreen() {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;
  const [state, setState] = useState<TodayCommandView | null>(null);
  const [structuredPlan, setStructuredPlan] = useState<StructuredPlan | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadToday = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const nextState = await getToday(token);
      setState(nextState);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Today failed to load.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadToday();
  }, [loadToday]);

  // Pull the active plan's structured_plan so Today can render today's exact
  // session blocks from the same data Plan Detail uses. This is read-only and
  // best-effort: if it fails, Today still works from the backend command view
  // (it just falls back to the session summary instead of full blocks).
  const activePlanId = state?.active_plan?.id;
  useEffect(() => {
    if (!token || !activePlanId) {
      setStructuredPlan(null);
      return;
    }
    let cancelled = false;
    getPlan(token, activePlanId)
      .then((detail) => {
        if (!cancelled) {
          setStructuredPlan(detail.outputs?.structured_plan ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStructuredPlan(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, activePlanId]);

  const activePlan = state?.active_plan ?? {};
  const planTitle = activePlan.name?.trim() || "Active fight camp";
  const hasPlan = hasActivePlan(activePlan);
  const showCheckin = state ? shouldShowTodayCheckin(state) : false;
  const trainingDayLabel = useMemo(
    () => formatTrainingDay(state?.today.training_day),
    [state?.today.training_day],
  );

  if (isLoading) {
    return <TodayLoadingState />;
  }
  if (error) {
    const isAccessIssue = /unauthorized|forbidden|not authenticated/i.test(error);
    return (
      <section className="panel today-shell today-error-state">
        <div className="today-hero-copy">
          <p className="kicker">Today command feed</p>
          <h1>{isAccessIssue ? "Access is locked" : "Today is temporarily unavailable"}</h1>
          <p className="muted" role="alert">
            {isAccessIssue
              ? "Sign in with an active athlete account to unlock Today."
              : "The live check-in feed did not respond. Your saved plan has not changed."}
          </p>
          {process.env.NODE_ENV !== "production" ? (
            <p className="today-error-detail">Technical detail: {error}</p>
          ) : null}
        </div>
        <div className="today-action-row">
          <button type="button" className="cta" onClick={() => void loadToday()}>
            Retry Today
          </button>
          <Link href="/plans" className="secondary-button">
            Open Plans
          </Link>
          <Link href="/" className="ghost-button">
            Overview
          </Link>
        </div>
      </section>
    );
  }

  if (!state || !hasPlan) {
    return <NoActivePlanState />;
  }

  return (
    <div className="today-page">
      <section className="panel today-shell">
        <div className="today-hero-grid">
          <div className="today-hero-copy">
            <p className="kicker">Today</p>
            <h1>{planTitle}</h1>
            <p className="muted today-hero-meta">
              {trainingDayLabel}
              {activePlan.phase ? <span aria-hidden="true"> · </span> : null}
              {activePlan.phase ? humanizeIfRawEnum(activePlan.phase) : null}
            </p>
          </div>
          <div className="today-hero-actions">
            <Link href={`/plans/${activePlan.id}`} className="secondary-button">
              View full plan
            </Link>
            <Link href="/" className="ghost-button">
              Overview
            </Link>
          </div>
        </div>
        <TodayReadinessStrip
          needsCheckin={showCheckin}
          openInjuryCount={state.open_injuries?.length ?? 0}
          completionStatus={state.today.completion_status}
        />
        <RiskWatch risks={state.risk_watch} />
      </section>

      {showCheckin ? (
        <CheckinModule
          plan={activePlan}
          token={token ?? ""}
          warnings={state.today.warnings}
          onRefresh={loadToday}
        />
      ) : null}

      {token ? (
        <InjuryCheckinCard
          openInjuries={state.open_injuries ?? []}
          token={token}
          onRefresh={loadToday}
        />
      ) : null}

      <SessionCard
        state={state}
        structuredPlan={structuredPlan}
        token={token ?? ""}
        onRefresh={loadToday}
      />
    </div>
  );
}
