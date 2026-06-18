"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { Skeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { getToday, submitTodayCheckin, submitTodaySessionCompletion } from "@/lib/api";
import {
  TODAY_EMPTY_TEXT,
  TODAY_EMPTY_TITLE,
  buildTodayCheckinPayload,
  canCompleteTodaySession,
  completionRequiresModificationReason,
  completionRequiresReviewFields,
  formatSessionValue,
  getCompletionLabel,
  getRecommendationCopy,
  getSessionTitle,
  getVisibleRiskWatch,
  hasActivePlan,
  hasTodaySession,
  shouldShowTodayCheckin,
} from "@/lib/today";
import type {
  TodayActivePlan,
  TodayCheckinBody,
  TodayCheckinPain,
  TodayCheckinSleep,
  TodayCommandView,
  TodayCompletionStatus,
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
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(date);
}

function formatSessionDate(session: TodaySession): string {
  const dayText = session.weekday_with_label || session.weekday;
  const countdown =
    typeof session.d_day === "number" ? `D-${Math.abs(session.d_day)}` : session.day_label;
  const hasCountdownInDayText = Boolean(dayText && countdown && dayText.includes(countdown));
  const parts = [
    dayText,
    session.calendar_date ? formatTrainingDay(session.calendar_date) : null,
    hasCountdownInDayText ? null : countdown,
  ].filter(Boolean);
  return parts.length ? parts.join(" / ") : "Athlete-local training day";
}

function getSessionFocus(session: TodaySession): string {
  return (
    session.primary_focus?.trim() ||
    session.emphasis?.trim() ||
    formatSessionValue(session.effective_load) ||
    session.reason?.trim() ||
    session.coach_note?.trim() ||
    "Follow the current plan guidance."
  );
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

function getSessionRelationCopy(session: TodaySession): {
  kicker: string;
  status: string;
  helper: string;
} {
  if (session.session_relation === "next") {
    return {
      kicker: "Next scheduled session",
      status: "Preview",
      helper: "Today has no matched training card, so this shows the next available plan day.",
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

function RiskWatch({ risks }: { risks: TodayCommandView["risk_watch"] }) {
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
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
      {overflow > 0 ? <span className="today-risk-more">+{overflow} more</span> : null}
    </section>
  );
}

function RecommendationCard({ state }: { state: TodayCommandView }) {
  const copy = getRecommendationCopy(state.today.recommendation_state);
  const session = state.today.next_session;
  const hasSession = hasTodaySession(session);
  return (
    <section className="today-card today-recommendation-card" data-tone={copy.tone} aria-labelledby="today-recommendation-heading">
      <div className="today-card-head">
        <div>
          <p className="kicker">Recommendation</p>
          <h2 id="today-recommendation-heading">{copy.label}</h2>
        </div>
      </div>
      <p className="today-recommendation-reason">
        {state.today.recommendation_reason || copy.actionText}
      </p>
      <div className="today-meta-strip">
        <span>{formatTrainingDay(state.today.training_day)}</span>
        <span>{hasSession ? getSessionTitle(session) : "No matched session"}</span>
      </div>
      {state.today.recommendation_state === "pull_back" ? (
        <p className="today-safety-note">
          If pain escalates or red flags appear, stop the session and use recovery work.
        </p>
      ) : null}
      {hasSession ? (
        <a href="#today-session" className="secondary-button today-session-jump">
          Go to session
        </a>
      ) : state.active_plan.id ? (
        <Link href={`/plans/${state.active_plan.id}`} className="secondary-button today-session-jump">
          View plan
        </Link>
      ) : null}
    </section>
  );
}

function CheckinModule({
  plan,
  token,
  onRefresh,
}: {
  plan: TodayActivePlan;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [sleep, setSleep] = useState<TodayCheckinSleep>("good");
  const [body, setBody] = useState<TodayCheckinBody>("normal");
  const [pain, setPain] = useState<TodayCheckinPain>("none");
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
          safetyFlags,
        }),
      );
      showToast(`Recommendation: ${getRecommendationCopy(response.recommendation_state).label}.`, {
        tone: response.recommendation_state === "pull_back" ? "info" : "success",
      });
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

        <details className="today-red-flags">
          <summary>Any red flags?</summary>
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
  const [sessionRpe, setSessionRpe] = useState("");
  const [painAfter, setPainAfter] = useState("");
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
    if (needsReviewFields && (!sessionRpe || !painAfter)) {
      setError("Add session RPE and pain-after before saving.");
      return;
    }
    await onSubmit({
      sessionRpe: sessionRpe ? Number.parseInt(sessionRpe, 10) : null,
      painAfter: painAfter ? Number.parseInt(painAfter, 10) : null,
      modificationReason: modificationReason.trim(),
      notes: notes.trim(),
    });
  }

  return (
    <form className="today-completion-form" onSubmit={handleSubmit}>
      {needsReviewFields ? (
        <div className="today-completion-fields">
          <label className="field" htmlFor="today-session-rpe">
            <span>Session RPE</span>
            <input
              id="today-session-rpe"
              type="number"
              inputMode="numeric"
              min={1}
              max={10}
              value={sessionRpe}
              onChange={(event) => setSessionRpe(event.target.value)}
            />
          </label>
          <label className="field" htmlFor="today-pain-after">
            <span>Pain after</span>
            <input
              id="today-pain-after"
              type="number"
              inputMode="numeric"
              min={0}
              max={10}
              value={painAfter}
              onChange={(event) => setPainAfter(event.target.value)}
            />
          </label>
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

function SessionCard({
  state,
  token,
  onRefresh,
}: {
  state: TodayCommandView;
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
  const relationCopy = getSessionRelationCopy(session);
  const isNextSessionPreview = session.session_relation === "next";
  const canCompleteSession = canCompleteTodaySession(session) && !isNextSessionPreview;

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
      <section id="today-session" className="today-card today-session-card" aria-labelledby="today-session-heading">
        <div className="today-card-head">
          <div>
            <p className="kicker">Today&apos;s session</p>
            <h2 id="today-session-heading">No session scheduled today</h2>
          </div>
        </div>
        <p className="muted">No active plan card matched today. Review the plan for the next training target.</p>
        <div className="today-action-row">
          <Link href={`/plans/${state.active_plan?.id}`} className="secondary-button">
            View full plan
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section id="today-session" className="today-card today-session-card" aria-labelledby="today-session-heading">
      <div className="today-card-head">
        <div>
          <p className="kicker">{relationCopy.kicker}</p>
          <h2 id="today-session-heading">{getSessionTitle(session)}</h2>
        </div>
      </div>
      <div className="today-session-summary">
        <div>
          <p className="today-detail-label">Day</p>
          <p>{formatSessionDate(session)}</p>
        </div>
        <div>
          <p className="today-detail-label">Focus</p>
          <p>{getSessionFocus(session)}</p>
        </div>
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
    return (
      <section className="panel today-shell">
        <div className="today-hero-copy">
          <p className="kicker">Today</p>
          <h1>Today did not load</h1>
          <p className="muted" role="alert">{error}</p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void loadToday()}>
          Retry
        </button>
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
            <p className="muted">
              {trainingDayLabel} / {activePlan.phase || "Current phase"} / Today&apos;s training decision and session control.
            </p>
          </div>
          <div className="today-hero-actions">
            <Link href={`/plans/${activePlan.id}`} className="secondary-button">
              View full plan
            </Link>
            <Link href="/" className="ghost-button">
              Back to Overview
            </Link>
          </div>
        </div>
        <RiskWatch risks={state.risk_watch} />
      </section>

      <div className="today-grid">
        <SessionCard state={state} token={token ?? ""} onRefresh={loadToday} />
        <div className="today-stack">
          {showCheckin ? (
            <CheckinModule plan={activePlan} token={token ?? ""} onRefresh={loadToday} />
          ) : null}
          <RecommendationCard state={state} />
        </div>
      </div>
    </div>
  );
}
