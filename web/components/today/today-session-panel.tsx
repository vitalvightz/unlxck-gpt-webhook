"use client";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import { SessionFeedbackPrompt } from "@/components/feedback/session-feedback-prompt";
import {
  SessionCompletionForm,
  type CompletionIntent,
} from "@/components/session-completion-form";
import {
  DaySessionContext,
  RehabLabelProvider,
  SessionCard as StructuredSessionCard,
  SessionlessDayCard,
} from "@/components/structured-plan-renderer";
import { formatTrainingDay } from "@/components/today/format";
import { SessionTimer, type SessionTimerSummary } from "@/components/session-timer/session-timer";
import { clearSavedRun, hasSavedRun } from "@/components/session-timer/use-session-timer";
import { RehabResponsePrompt } from "@/components/today/rehab-response-prompt";
import { SparringLogPrompt, type SparringDraft } from "@/components/today/sparring-log-prompt";
import { useToast } from "@/components/toast-provider";
import { listPendingRehabResponses, submitTodaySessionCompletion } from "@/lib/api";
import { timerAudio } from "@/lib/session-timer/audio";
import {
  CONTACT_FORMAT_MEMORY_KEY,
  contactRoundsItem,
  contactTimerTarget,
  contactTitle,
  freeRoundsItem,
  savedRoundFormat,
  type ContactTimerTarget,
} from "@/lib/session-timer/contact";
import { sessionTimerItems, timerSessionFor, type TimerItem } from "@/lib/session-timer/plan";
import {
  resolveCurrentDay,
  resolveOpenPlanWeekNumber,
  sessionIdentity,
  type CurrentDayResolution,
} from "@/lib/camp-map";
import type { TodayPlanSchedule } from "@/components/today/use-today-command";
import { openBlockWeekIntent, type OpenBlockWeekIntent } from "@/lib/open-block";
import { isOpenOngoingPlan } from "@/lib/plan-format";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { shouldPromptSessionFeedback } from "@/lib/session-feedback";
import { useTrainingDay } from "@/lib/use-training-day";
import {
  getCompletionLabel,
  getSafeSessionView,
  getSessionFocus,
  getSessionTitle,
  isHardCombatSession,
  resolveTodayDecision,
  resolveSessionFocusDate,
  type SafeSessionView,
} from "@/lib/today";
import type {
  RehabLabelPolicy,
  PendingRehabResponseSet,
  SparringPlannedIntensity,
  StructuredDay,
  StructuredPlan,
  TodayCommandView,
  TodayCompletionStatus,
  TodaySession,
} from "@/lib/types";

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

/** Which timer is running: today's planned session, today's coach-led contact
 * (sparring the athlete declared, with no app session to start), or plain rounds. */
type TimerSource = "session" | "contact" | "free";

const CONTACT_LOCK_COPY = {
  not_checked_in: "Sparring rounds unlock after check-in",
  blocked: "Sparring rounds locked today",
};

const PLANNED_SPARRING_INTENSITY: Record<ContactTimerTarget["kind"], SparringPlannedIntensity> = {
  sparring: "hard",
  light_combat: "light",
  technical: "technical",
  coach_led: "contact",
};

type ToolIconName = "bell" | "timer" | "lock" | "check" | "adjust" | "skip";

const TOOL_ICON_PATHS: Record<ToolIconName, ReactNode> = {
  // A ring bell: sparring rounds.
  bell: <path d="M6 16h12M8 16a4 4 0 118 0M12 8V6M10 19h4" />,
  timer: <path d="M12 13V9.5M9.5 3h5M12 21a8 8 0 100-16 8 8 0 000 16zM18.5 6.5l1.5-1.5" />,
  lock: <path d="M7 11V8a5 5 0 0110 0v3M6 11h12v9H6z" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  adjust: <path d="M4 8h9M17 8h3M4 16h3M11 16h9M15 6v4M9 14v4" />,
  skip: <path d="M6 6l12 12M18 6L6 18" />,
};

function ToolIcon({ name }: { name: ToolIconName }) {
  return (
    <svg className="today-tool-icon" viewBox="0 0 24 24" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {TOOL_ICON_PATHS[name]}
      </g>
    </svg>
  );
}

/** Saved timer runs only change through this tab's own actions, which re-render. */
function subscribeToNothing(): () => void {
  return () => undefined;
}

function textValue(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Position of the session being completed within its day, or -1 when unmatched. */
function activeSessionIndex(
  current: CurrentDayResolution,
  sessionId: string | null | undefined,
): number {
  const active = timerSessionFor(current.sessions, sessionId);
  return active ? current.sessions.indexOf(active) : -1;
}

function getStructuredTodaySessionTitle(
  current: CurrentDayResolution,
  sessionId: string | null | undefined,
): string {
  // Headline the session being completed, not the day's first: once the first of
  // two is logged, the backend targets the second and the card must follow it.
  const session = current.sessions[Math.max(activeSessionIndex(current, sessionId), 0)];
  const card = current.day?.today_card;
  return (
    textValue(session?.title) ||
    textValue(card?.headline) ||
    humanizeIfRawEnum(textValue(session?.session_type))
  );
}

function sameTitle(a: string, b: string): boolean {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return Boolean(normalize(a)) && normalize(a) === normalize(b);
}

function getSessionRelationCopy(
  session: TodaySession,
  completionStatus: TodayCompletionStatus,
  sessionIsToday: boolean,
): {
  kicker: string;
  status: string;
  helper: string;
} {
  // The authoritative resolver owns "today vs next". It normally follows the
  // backend relation, but rejects an impossible calendar-date mismatch so a
  // stale payload cannot label or unlock future work as today's session.
  if (!sessionIsToday) {
    const loggedToday =
      completionStatus === "done" ||
      completionStatus === "modified" ||
      completionStatus === "skipped";
    return {
      kicker: "Next session",
      status: "Preview",
      helper: loggedToday
        ? "Today's session is logged, so this shows your next session."
        : "Today has no matched training card, so this shows the next available plan day.",
    };
  }
  return {
    kicker: "Today's session",
    status: "Live today",
    helper: "Matched from the active plan by the athlete-local training day.",
  };
}

/**
 * The recovery/mobility-only card shown in place of the scheduled blocks when
 * today is a STOP — Today never displays hard combat as available under a stop.
 */
function SafeSessionCard({ view }: { view: SafeSessionView }) {
  return (
    <div className="today-safe-session" data-tone="red">
      <p className="today-safe-session-eyebrow">{view.eyebrow}</p>
      <p className="today-safe-session-title">{view.title}</p>
      <p className="today-safe-session-detail">{view.detail}</p>
      <div className="today-safe-session-lists">
        <div className="today-safe-list" data-kind="allowed">
          <p className="today-safe-list-label">Allowed</p>
          <ul>{view.allowed.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
        <div className="today-safe-list" data-kind="blocked">
          <p className="today-safe-list-label">Blocked</p>
          <ul>{view.blocked.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
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
export function TodaySessionBlocks({
  planId,
  current,
  openWeekIntent,
  rehabLabelPolicy,
  activeSessionId,
}: {
  planId?: string;
  current: CurrentDayResolution;
  /** Today's session being completed. The backend offers a day's sessions in
   * order, first outstanding first, so every session ahead of it is already
   * logged: those collapse to a "Logged today" line instead of full cards. */
  activeSessionId?: string | null;
  /** Development-block week intent of an open (renewable) plan: headlines where
   * today sits in the block and forwards the per-block directive to the cards. */
  openWeekIntent?: OpenBlockWeekIntent | null;
  /** Per-region Rehab/Prehab policy from the active plan. Today renders
   * SessionCard directly rather than through Plan Detail's full-plan renderer,
   * so it has to mount the provider itself; without it every rehab block on this
   * screen read "Rehab" no matter which injuries had cleared. */
  rehabLabelPolicy?: RehabLabelPolicy | null;
}) {
  if (!current.inRange || !current.day) {
    return null;
  }
  // A renewable plan may resolve today's weekday against a projected template
  // row from another month. Keep that row for plan identity, but never present
  // its projected date as today's calendar date.
  const displayDay =
    current.matchType === "weekday" && current.trainingDayISO
      ? { ...current.day, date: current.trainingDayISO }
      : current.day;
  const weekIntentNote = openWeekIntent ? (
    <p className="today-open-week-note">
      <span className="sp-tag sp-accent">
        Week {openWeekIntent.weekNumber} · {openWeekIntent.label}
      </span>
      {openWeekIntent.summary}
    </p>
  ) : null;
  if (current.sessions.length === 0) {
    return (
      <div className="today-blocks">
        {weekIntentNote}
        <SessionlessDayCard day={displayDay} />
      </div>
    );
  }
  const firstOpenIndex = Math.max(activeSessionIndex(current, activeSessionId), 0);
  const loggedTitles = current.sessions
    .slice(0, firstOpenIndex)
    .map((session) => textValue(session.title) || humanizeIfRawEnum(textValue(session.session_type)))
    .filter(Boolean);
  return (
    <RehabLabelProvider policy={rehabLabelPolicy}>
      <div className="today-blocks">
        {weekIntentNote}
        <DaySessionContext day={displayDay} />
        {loggedTitles.length ? (
          <p className="today-logged-sessions">
            <span className="sp-tag">Logged today</span>
            {loggedTitles.join(" · ")}
          </p>
        ) : null}
        {current.sessions.map((session, index) =>
          index < firstOpenIndex ? null : (
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
              day={index === firstOpenIndex ? displayDay : undefined}
              defaultOpenBlocks
              showDayContext={false}
              openWeekIntent={openWeekIntent}
            />
          ),
        )}
      </div>
    </RehabLabelProvider>
  );
}

/**
 * The session card: today's (or the next) session with its structured blocks,
 * the decision banner framing it, and the start/complete lifecycle actions.
 */
export function TodaySessionPanel({
  state,
  structuredPlan,
  planSchedule,
  rehabLabelPolicy,
  token,
  onRefresh,
}: {
  state: TodayCommandView;
  structuredPlan: StructuredPlan | null;
  /** Server-derived per-region Rehab/Prehab policy for the active plan. */
  rehabLabelPolicy?: RehabLabelPolicy | null;
  /** Server schedule projection + plan creation date, used to anchor the
   * current week of a weekday-only (open / renewable) plan. */
  planSchedule?: TodayPlanSchedule | null;
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [intent, setIntent] = useState<CompletionIntent>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  // The session the athlete just logged as trained, captured at write time.
  // The refresh that follows can advance `next_session` to tomorrow's card, so
  // reading the id live would attach the review to the wrong session.
  const [reviewableSession, setReviewableSession] = useState<
    { planId: string; sessionId: string } | null
  >(null);
  // Interaction stays local, but existence comes from durable server context.
  // This is an array so two completed sessions on one day cannot hide each
  // other's independently pending injury response.
  const [rehabResponses, setRehabResponses] = useState<PendingRehabResponseSet[]>([]);
  // The running timer, full screen or minimised to a bar while it keeps time.
  const [activeTimer, setActiveTimer] = useState<
    { source: TimerSource; mode: "open" | "minimized" } | null
  >(null);
  // What the timer recorded, pre-filled (editable) into the completion notes.
  const [timerNotes, setTimerNotes] = useState("");
  // Finished sparring rounds waiting for the athlete's quick log entry.
  const [sparringDraft, setSparringDraft] = useState<SparringDraft | null>(null);
  const session = state.today.next_session;
  const status = state.today.completion_status;
  const duration = getSessionDuration(session);
  const resolvedDecision = resolveTodayDecision(state);
  const hasSession = resolvedDecision.hasSession;
  // Resolve today's day/session from the structured plan through the shared
  // 03:00 rollover, exactly as Plan Detail does. These blocks — not the backend
  // session summary — are the "what exact blocks apply today" answer. The
  // training day comes from the client-mounted hook (SSR-safe, null until mount)
  // and is resolved on every render so a long-lived tab follows the rollover
  // instead of sticking on a memoized day.
  const trainingDay = useTrainingDay();
  const activePlanId = state.active_plan.id ?? "";
  useEffect(() => {
    if (!token || !activePlanId) {
      return;
    }
    let cancelled = false;
    void listPendingRehabResponses(token, activePlanId)
      .then((pending) => {
        if (!cancelled) {
          setRehabResponses(pending.response_sets);
          if (pending.history_truncated && process.env.NODE_ENV !== "production") {
            console.warn("Pending rehab response history was truncated");
          }
        }
      })
      .catch((error: unknown) => {
        // A read failure must not fabricate an answered state. Keep any prompt
        // already in memory; a remount/retry can retrieve the durable context.
        if (process.env.NODE_ENV !== "production") {
          console.error("Pending rehab responses could not be loaded", error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activePlanId, token]);
  // Center the structured blocks on whatever the backend command view targets:
  // today's day in the normal case, or the NEXT scheduled session's day once
  // today is logged / carries no app card (session_relation === "next"). Resolving
  // by that target day — not the bare calendar day — stops the card from sticking
  // on the finished session while the header has already advanced to "Next
  // session", which is exactly how Overview already behaves.
  const focusDate = resolveSessionFocusDate(trainingDay, session);
  // Open (renewable) plans carry weekday-only days with no calendar dates, so
  // the resolver needs to know which week of the block "today" falls in. Dated
  // camps ignore the hint — they still resolve purely by calendar date.
  const openWeekNumber = resolveOpenPlanWeekNumber(structuredPlan, focusDate, {
    currentWeekNumber: planSchedule?.scheduleContext?.current_week_number,
    anchorDate: planSchedule?.scheduleContext?.anchor_date,
    createdAt: planSchedule?.createdAt,
  });
  const openOngoing = Boolean(
    state.active_plan && isOpenOngoingPlan(state.active_plan.fight_date),
  );
  const current = resolveCurrentDay(structuredPlan, focusDate, {
    openWeekNumber,
    allowDatedWeekdayMatch: openOngoing,
  });
  // Where the resolved day sits in the renewable development block (baseline /
  // progress / peak / deload). The resolved week position wins over the bare
  // anchor-derived number so the note always matches the blocks shown below.
  // Dated camps stay null and render unchanged.
  const openWeekIntent = openOngoing
    ? openBlockWeekIntent(current.weekPos != null ? current.weekPos + 1 : openWeekNumber)
    : null;
  const showStructuredBlocks = current.inRange && Boolean(current.day);
  const hasResolvedDaySessions = current.inRange && current.sessions.length > 0;
  const isSessionPreview = resolvedDecision.displayTier === "preview";
  const relationCopy = getSessionRelationCopy(
    session,
    status,
    resolvedDecision.sessionIsToday,
  );
  const decisionBlocksCurrentSession = resolvedDecision.blocksCurrentSession;
  const severeInjuryBlocksCurrentSession =
    resolvedDecision.severeInjuryBlocksCurrentSession;
  // STOP + the scheduled session is today: show the recovery/mobility safe
  // session in place of the real blocks so Today never displays hard combat as
  // available under a stop. Future sessions stay visible but read as pending.
  const safeSession =
    resolvedDecision.useSafeReplacement
      ? getSafeSessionView(getSessionTitle(session), state.open_injuries)
      : null;
  const nextIsHardCombat = isHardCombatSession(session);
  // Gate completion on the scope-aware "is this today" check, not just the
  // session_relation stamp: a session that reaches the card without an explicit
  // session_relation but whose scope is not "today" must still read as pending,
  // never completable.
  //
  // Whether today HAS a session is the server's answer, not one re-derived here.
  // An empty sessions array is not the same question: a headline-only support
  // day ("Rhythm flush") carries no session objects and is still prescribed
  // work, so reading rest-ness off the array disabled real sessions. The server
  // resolves the plan card — and rejects completion writes on a rest day — so
  // scope "today" is the single answer both sides use.
  const canCompleteSession = resolvedDecision.canCompleteSession;
  // The timer runs the blocks of the ONE session being completed, never the
  // whole day (a day can carry several sessions, and completion is written
  // against this session's id). No timeable blocks means no session timer:
  // a zero-load session such as Tactical Focus is never turned into rounds.
  const timerSourceText = structuredPlan?.raw_markdown_fallback ?? null;
  const timerCountdown = current.day?.countdown_label ?? null;
  const timerItems: TimerItem[] = hasResolvedDaySessions
    ? sessionTimerItems(current.sessions, session.session_id, {
        sourceText: timerSourceText,
        countdown: timerCountdown,
      })
    : [];
  const timerAvailable =
    canCompleteSession && !safeSession && Boolean(session.session_id) && timerItems.length > 0;
  // Titled from the matched session itself: the card headline follows the
  // day's first session, which is not necessarily the one being completed.
  const timerSessionTitle = hasResolvedDaySessions
    ? textValue(timerSessionFor(current.sessions, session.session_id)?.title)
    : "";
  const timerKeys: Record<TimerSource, string> = {
    session: `unlxck.session-timer.run:${activePlanId}:${session.session_id ?? ""}:${state.today.training_day}`,
    contact: `unlxck.session-timer.contact:${activePlanId}:${state.today.training_day}`,
    free: `unlxck.session-timer.free:${state.today.training_day}`,
  };
  const timerStorageKey = timerKeys.session;
  // Coach-led contact is timed from TODAY's plan day, even when the card above
  // has moved on to the next app session (a sparring-only day has none).
  const todayOpenWeekNumber = resolveOpenPlanWeekNumber(structuredPlan, trainingDay, {
    currentWeekNumber: planSchedule?.scheduleContext?.current_week_number,
    anchorDate: planSchedule?.scheduleContext?.anchor_date,
    createdAt: planSchedule?.createdAt,
  });
  const todayResolved =
    focusDate === trainingDay
      ? current
      : resolveCurrentDay(structuredPlan, trainingDay, {
          openWeekNumber: todayOpenWeekNumber,
          allowDatedWeekdayMatch: openOngoing,
        });
  const contactTarget: ContactTimerTarget | null =
    (todayResolved.inRange ? contactTimerTarget(todayResolved.day) : null) ??
    (resolvedDecision.sessionIsToday && session.coach_led_contact
      ? contactTimerTarget({ today_card: { coach_led_contact: session.coach_led_contact } } as StructuredDay)
      : null);
  // Hard contact follows the same readiness authority as a session: only a
  // go / follow-the-limits day, never under pull back, stop or a severe injury.
  const contactCleared =
    (resolvedDecision.authoritativeTier === "green" ||
      resolvedDecision.authoritativeTier === "modify") &&
    !severeInjuryBlocksCurrentSession &&
    !safeSession;
  const contactTimerAvailable = Boolean(contactTarget) && contactCleared;
  // The athlete's declared gym work (hard sparring, technical rounds) is the
  // day's main event: it owns the headline and the primary button, and any app
  // work that day reads as what comes with it. Contact never leads a day the
  // decision blocks (pull back, stop): it is not happening, so it cannot be
  // the day's headline.
  const contactLeads =
    Boolean(contactTarget) &&
    resolvedDecision.sessionIsToday &&
    !safeSession &&
    !decisionBlocksCurrentSession;
  const contactHeadline = contactTarget ? contactTitle(contactTarget) : "";
  // Is the session being logged the contact itself? A sparring-only day has no
  // session objects, so the server logs it against the day's headline entry.
  const contactIsSession =
    contactLeads &&
    ((current.inRange && Boolean(current.day) && current.sessions.length === 0) ||
      sameTitle(getSessionTitle(session), contactTarget?.headline ?? "") ||
      sameTitle(getSessionTitle(session), contactHeadline));
  const contactLockCopy =
    resolvedDecision.authoritativeTier === "not_checked_in"
      ? CONTACT_LOCK_COPY.not_checked_in
      : CONTACT_LOCK_COPY.blocked;
  const freeTimerAvailable =
    resolvedDecision.authoritativeTier !== "stop" && !severeInjuryBlocksCurrentSession;
  // A run left in progress (app closed mid-session) comes back as the mini bar.
  // Read from storage on the client only, so server and first client render agree.
  const savedTimerSource = useSyncExternalStore<TimerSource | null>(
    subscribeToNothing,
    () =>
      timerAvailable && status === "started" && hasSavedRun(timerKeys.session)
        ? "session"
        : contactTimerAvailable && hasSavedRun(timerKeys.contact)
          ? "contact"
          : freeTimerAvailable && hasSavedRun(timerKeys.free)
            ? "free"
            : null,
    () => null,
  );
  const shownTimer =
    activeTimer ?? (savedTimerSource ? { source: savedTimerSource, mode: "minimized" as const } : null);
  // Tint the session card to match today's decision (green/amber/red) so the page
  // reads at a glance instead of being a wall of identical dark cards. Neutral
  // (not-checked-in) carries no tone — the card stays default until check-in.
  const cardTone =
    resolvedDecision.tone === "green" ||
    resolvedDecision.tone === "amber" ||
    resolvedDecision.tone === "red"
      ? resolvedDecision.tone
      : undefined;
  const terminalStatusCopy = severeInjuryBlocksCurrentSession
    ? "Blocked by an active severe injury."
    : decisionBlocksCurrentSession
      ? "Follow the recommendation above. Do not start this session from Today."
      : isSessionPreview
        ? "Preview only. Completion opens on the matched training day."
        : resolvedDecision.authoritativeTier === "not_checked_in"
          ? "Submit today's check-in to unlock session actions."
          : "This entry has nothing to log. Follow it as written.";

  async function saveCompletion(
    nextStatus: TodayCompletionStatus,
    details: {
      sessionRpe?: number | null;
      painAfter?: number | null;
      modificationReason?: string;
      notes?: string;
    } = {},
  ): Promise<boolean> {
    if (!state.active_plan.id || !session.session_id || isSubmitting) {
      return false;
    }
    setIsSubmitting(true);
    try {
      const completion = await submitTodaySessionCompletion(token, {
        plan_id: state.active_plan.id,
        session_id: session.session_id,
        status: nextStatus,
        session_rpe: details.sessionRpe ?? null,
        pain_after: details.painAfter ?? null,
        modification_reason: details.modificationReason ?? "",
        notes: details.notes ?? "",
      });
      setIntent(null);
      if (nextStatus !== "started") {
        clearSavedRun(timerStorageKey);
        setActiveTimer((timer) => (timer?.source === "session" ? null : timer));
        setTimerNotes("");
      }
      // Non-empty only when the server established that this session contained
      // rehab attributable to a known injury, so a normal session never shows
      // this block.
      const prompts = completion.rehab_response_prompts ?? [];
      setRehabResponses((current) => {
        const others = current.filter(
          (item) => item.completion_id !== completion.completion.id,
        );
        if (prompts.length === 0) {
          return others;
        }
        return [
          ...others,
          {
            completion_id: completion.completion.id,
            plan_id: completion.completion.plan_id,
            session_id: completion.completion.session_id,
            training_day: completion.completion.training_day,
            rehab_response_prompts: prompts,
          },
        ];
      });
      showToast(getCompletionLabel(nextStatus), { tone: "success" });
      // Order matters: the confirmation toast is already up and the refresh
      // below is what surfaces the XP award, so the review prompt is queued
      // here and only renders once both have landed.
      setReviewableSession(
        shouldPromptSessionFeedback(nextStatus)
          ? { planId: state.active_plan.id, sessionId: session.session_id }
          : null,
      );
      await onRefresh();
      return true;
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Session update failed.", { tone: "error" });
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }

  function openTimer(source: TimerSource) {
    // Audio only unlocks inside the tap itself.
    timerAudio().unlock();
    setActiveTimer({ source, mode: "open" });
  }

  /** Lead button on a contact day: time the rounds, and when the contact IS
   * today's session, mark it started so it can be logged when the rounds end. */
  function startContact() {
    openTimer("contact");
    if (contactIsSession && canCompleteSession && status === "not_started") {
      void saveCompletion("started");
    }
  }

  const sparringPrompt = sparringDraft ? (
    <SparringLogPrompt
      key={`${sparringDraft.source}:${sparringDraft.rounds}:${sparringDraft.title}`}
      token={token}
      draft={sparringDraft}
      onDismiss={() => setSparringDraft(null)}
    />
  ) : null;

  // Timer shortcuts shown along the bottom of the action tray. Hidden while a
  // timer is running: its mini bar is the way back in.
  function timerTools(trailing?: ReactNode, options: { contactAsPrimary?: boolean } = {}) {
    const showContact = Boolean(contactTarget) && !options.contactAsPrimary;
    const tools = !shownTimer && (showContact || freeTimerAvailable);
    if (!tools && !trailing) {
      return null;
    }
    return (
      <>
      {tools ? (
      <div className="today-action-tools">
        {tools && showContact ? (
          contactTimerAvailable ? (
            <button type="button" className="today-tool-button" data-accent="true" onClick={() => openTimer("contact")}>
              <ToolIcon name="bell" />
              Sparring rounds
            </button>
          ) : (
            <span className="today-tool-lock">
              <ToolIcon name="lock" />
              {contactLockCopy}
            </span>
          )
        ) : null}
        {tools && freeTimerAvailable ? (
          <button type="button" className="today-tool-button" onClick={() => openTimer("free")}>
            <ToolIcon name="timer" />
            Round timer
          </button>
        ) : null}
      </div>
      ) : null}
      {trailing ? <div className="today-action-footer">{trailing}</div> : null}
      </>
    );
  }

  // A sparring-only day has no session actions: its tray leads with the rounds.
  const contactOnlyTray =
    !shownTimer && (contactTarget || freeTimerAvailable) ? (
      <div className="today-session-actions today-action-tray">
        {contactTarget && contactTimerAvailable ? (
          <button type="button" className="cta" onClick={() => openTimer("contact")}>
            Start sparring rounds
          </button>
        ) : null}
        {timerTools(undefined, { contactAsPrimary: Boolean(contactTarget && contactTimerAvailable) })}
      </div>
    ) : null;

  function renderTimer(sessionTitle: string) {
    if (!shownTimer) {
      return null;
    }
    const { source, mode } = shownTimer;
    let items: TimerItem[];
    let title: string;
    if (source === "session") {
      if (!timerAvailable) return null;
      items = timerItems;
      title = timerSessionTitle || sessionTitle;
    } else if (source === "contact") {
      if (!contactTimerAvailable || !contactTarget) return null;
      items = [contactRoundsItem(contactTarget, savedRoundFormat(CONTACT_FORMAT_MEMORY_KEY))];
      title = items[0].title;
    } else {
      if (!freeTimerAvailable) return null;
      items = [freeRoundsItem()];
      title = "Round timer";
    }
    const storageKey = timerKeys[source];
    return (
      <SessionTimer
        key={storageKey}
        items={items}
        storageKey={storageKey}
        sessionTitle={title}
        visible={mode === "open"}
        finishLabel={source === "session" ? "Log session" : "Done"}
        onMinimize={() => setActiveTimer({ source, mode: "minimized" })}
        onExpand={() => openTimer(source)}
        onFinish={(summary: SessionTimerSummary) => {
          clearSavedRun(storageKey);
          setActiveTimer(null);
          // Any sparring rounds actually done get the quick sparring log.
          if (summary.sparring && summary.sparring.rounds > 0 && source !== "free") {
            setSparringDraft({
              source,
              planId: activePlanId || null,
              sessionId: source === "session" ? session.session_id ?? null : null,
              // The day's deterministic contact classification is authoritative
              // for both contact rounds and sparring inside a planned session;
              // the sparring block's own structured intensity is the fallback.
              plannedIntensity: contactTarget
                ? PLANNED_SPARRING_INTENSITY[contactTarget.kind]
                : summary.sparring.plannedIntensity,
              title: title,
              rounds: summary.sparring.rounds,
              roundSeconds: summary.sparring.roundSeconds,
            });
          }
          if (source === "session") {
            setTimerNotes(summary.notes.slice(0, 2000));
            // A run that fell short of the plan is logged as modified, so the
            // athlete gives the reason instead of it silently reading as done.
            setIntent(summary.complete ? "done" : "modified");
            return;
          }
          if (
            source === "contact" &&
            contactIsSession &&
            canCompleteSession &&
            (status === "not_started" || status === "started") &&
            (summary.sparring?.rounds ?? 0) > 0
          ) {
            // The gym sets the round count, so fewer rounds than the timer's
            // default is not a modified session: the rounds done are the log.
            setTimerNotes(summary.notes.slice(0, 2000));
            setIntent("done");
            return;
          }
          const recorded = summary.notes.replace(/^Timer:\s*/, "");
          showToast(recorded || "Timer closed.", { tone: recorded ? "success" : "info" });
        }}
      />
    );
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
              {contactTarget ? contactHeadline : formatTrainingDay(state.today.training_day)}
            </h2>
          </div>
        </div>
        {showStructuredBlocks ? (
          <TodaySessionBlocks
            planId={state.active_plan?.id}
            current={current}
            openWeekIntent={openWeekIntent}
            rehabLabelPolicy={rehabLabelPolicy}
          />
        ) : (
          <p className="muted">No active plan card matched today. Use Open camp plan to find the next training target.</p>
        )}
        {contactOnlyTray}
        {sparringPrompt}
        {renderTimer(formatTrainingDay(state.today.training_day))}
      </section>
    );
  }

  const sessionTitle = hasResolvedDaySessions
    ? getStructuredTodaySessionTitle(current, session.session_id) || getSessionTitle(session)
    : getSessionTitle(session);
  // Avoid the "Today's session / Today's session" stutter: when the session has
  // no real name and falls back to the generic title that already matches the
  // kicker, headline the training day instead so the eyebrow and heading differ.
  const sessionHeadline =
    sessionTitle.trim().toLowerCase() === "today's session" ||
    sessionTitle.trim().toLowerCase() === relationCopy.kicker.trim().toLowerCase()
      ? formatSessionDate(session)
      : sessionTitle;
  const headline = contactLeads ? contactHeadline : sessionHeadline;
  // The contact rounds lead the tray while no timer is already running.
  const contactCta = contactLeads && contactTimerAvailable && !shownTimer;
  // The app work that comes with the day's contact, named under the headline.
  const alongsideTitle = contactLeads && !contactIsSession ? sessionTitle.trim() : "";

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
          {alongsideTitle ? (
            <p className="today-session-alongside">
              <span className="today-detail-label">Also today</span> {alongsideTitle}
            </p>
          ) : null}
        </div>
      </div>
      {safeSession ? (
        <SafeSessionCard view={safeSession} />
      ) : showStructuredBlocks ? (
        <TodaySessionBlocks
          planId={state.active_plan?.id}
          current={current}
          openWeekIntent={openWeekIntent}
          rehabLabelPolicy={rehabLabelPolicy}
          activeSessionId={resolvedDecision.sessionIsToday ? session.session_id : null}
        />
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
          {!isSessionPreview ? (
            <div>
              <p className="today-detail-label">Status</p>
              <p>{getCompletionLabel(status)}</p>
            </div>
          ) : null}
        </div>
      )}
      {isSessionPreview && !safeSession ? (
        <div className="today-next-planned-note">
          <p className="today-pending-line">
            <span className="today-pending-pill">Pending</span>
            Check in on the day to unlock this session.
          </p>
          {nextIsHardCombat ? (
            <div className="today-caution-row">
              <span className="today-caution-label">Caution</span>
              <span className="today-caution-text">
                Combat session planned next. Re-check fatigue, pain, and injury status before clearing.
              </span>
            </div>
          ) : null}
        </div>
      ) : null}

      {!canCompleteSession && !safeSession ? (
        <div className="today-terminal-block">
          <p
            className="today-terminal-status"
            data-tone={decisionBlocksCurrentSession ? "blocked" : "neutral"}
          >
            {terminalStatusCopy}
          </p>
          {severeInjuryBlocksCurrentSession ? (
            <a href="#today-injury" className="secondary-button today-terminal-action">
              Open injury check-in
            </a>
          ) : null}
        </div>
      ) : null}

      {canCompleteSession && status === "not_started" ? (
        <div className="today-session-actions today-action-tray">
          {contactCta ? (
            <button type="button" className="cta" onClick={startContact} disabled={isSubmitting}>
              Start {contactHeadline.toLowerCase()}
            </button>
          ) : null}
          {contactLeads && contactTimerAvailable && contactIsSession ? null : (
            <button
              type="button"
              className={contactCta ? "secondary-button" : "cta"}
              onClick={() => {
                // Audio only unlocks inside the tap itself, before any await.
                if (timerAvailable) timerAudio().unlock();
                void saveCompletion("started").then((started) => {
                  if (started && timerAvailable) setActiveTimer({ source: "session", mode: "open" });
                });
              }}
              disabled={isSubmitting}
            >
              {alongsideTitle ? `Start ${alongsideTitle}` : "Start session"}
            </button>
          )}
          {timerTools(
            <button
              type="button"
              className="today-tool-link"
              onClick={() => setIntent("skipped")}
              disabled={isSubmitting}
            >
              Skip session
            </button>,
            { contactAsPrimary: contactLeads && contactTimerAvailable },
          )}
        </div>
      ) : null}

      {canCompleteSession && status === "started" ? (
        <div className="today-session-actions today-action-tray">
          <button
            type="button"
            className="cta"
            onClick={() => {
              if (timerAvailable) {
                openTimer("session");
                return;
              }
              if (contactIsSession && contactTimerAvailable) {
                openTimer("contact");
                return;
              }
              showToast("Session is in progress.", { tone: "info" });
            }}
            disabled={isSubmitting}
          >
            Resume session
          </button>
          <div className="today-log-row">
            <span className="today-log-label" id="today-log-label">
              Log as
            </span>
            <div className="today-log-group" role="group" aria-labelledby="today-log-label">
              {(["done", "modified", "skipped"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  data-value={value}
                  aria-pressed={intent === value}
                  onClick={() => setIntent(value)}
                  disabled={isSubmitting}
                >
                  <ToolIcon name={value === "done" ? "check" : value === "modified" ? "adjust" : "skip"} />
                  {value === "done" ? "Done" : value === "modified" ? "Modified" : "Skipped"}
                </button>
              ))}
            </div>
          </div>
          {timerTools()}
        </div>
      ) : null}

      {canCompleteSession && (status === "done" || status === "modified" || status === "skipped") ? (
        <p className="today-terminal-status">{getCompletionLabel(status)}</p>
      ) : null}

      {/* Locked, logged or blocked sessions still get the timer shortcuts. */}
      {!(canCompleteSession && (status === "not_started" || status === "started")) &&
      (contactTarget || freeTimerAvailable) &&
      !shownTimer ? (
        <div className="today-session-actions today-action-tray">{timerTools()}</div>
      ) : null}

      {sparringPrompt}

      {canCompleteSession ? (
        <SessionCompletionForm
          key={`${intent ?? "closed"}:${timerNotes}`}
          intent={intent}
          initialNotes={timerNotes}
          isSubmitting={isSubmitting}
          onCancel={() => setIntent(null)}
          onSubmit={async (nextStatus, details) => {
            await saveCompletion(nextStatus, {
              sessionRpe: details.sessionRpe,
              painAfter: details.painAfter,
              modificationReason: details.modificationReason,
              notes: details.notes,
            });
          }}
        />
      ) : null}

      {/* Above the session review on purpose: an injury observation is the more
          time-sensitive of the two, and the athlete should not have to get past
          a programming survey to report that something hurt. */}
      {rehabResponses.map((pending) => (
        <RehabResponsePrompt
          key={`rehab-${pending.completion_id}`}
          token={token}
          planId={pending.plan_id}
          sessionId={pending.session_id}
          trainingDay={pending.training_day}
          prompts={pending.rehab_response_prompts}
          onDismiss={() =>
            setRehabResponses((current) =>
              current.filter((item) => item.completion_id !== pending.completion_id),
            )
          }
        />
      ))}

      {renderTimer(headline)}

      {reviewableSession ? (
        <SessionFeedbackPrompt
          key={reviewableSession.sessionId}
          token={token}
          planId={reviewableSession.planId}
          sessionId={reviewableSession.sessionId}
          onDismiss={() => setReviewableSession(null)}
        />
      ) : null}
    </section>
  );
}
