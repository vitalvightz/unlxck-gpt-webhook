"use client";

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import {
  classifySessionlessDay,
  cleanText,
  formatBlockLoad,
  formatEffort,
  formatMeasured,
  getBlocks,
  getCoachingCues,
  getActiveNotesExcludingRedFlags,
  getCoachLedContactView,
  getDays,
  getDisplayableRedFlags,
  getFallbackSafetyNotes,
  getRehabOrMobilityBlocks,
  isDeEmphasisedWeightCutSafety,
  progressionRuleLabel,
  planNoteLabel,
  formatWeightCutBand,
  getDeterministicNutritionPhases,
  getDeterministicRecoveryPhases,
  getMindsetLines,
  getSessions,
  getStringList,
  getWeeks,
  hasNutrition,
  normalizeSupportPhaseKey,
  nutritionPhaseRows,
  recoveryPhaseView,
  redFlagView,
  selectBlockMetric,
  shouldShowRest,
  weekLabel,
} from "@/lib/structured-plan";
import {
  buildCompletionIndex,
  canRetroLog,
  completionForSession,
  completionSessionId,
  dayCompletion,
  getSessionDisplayStatus,
  resolveNextPlanFocusDay,
  resolvePlanProgress,
  weekCompletion,
  weekLoadProxy,
  weekSessionSummary,
  type Completion,
  type CompletionIndex,
  type SessionDisplayStatus,
} from "@/lib/camp-map";
import { useTrainingDay } from "@/lib/use-training-day";
import { formatAppDate } from "@/lib/date-format";
import { formatPlanLabel } from "@/lib/plan-labels";
import { SafetyNote } from "@/components/safety-note";
import { PLAN_SAFETY_NOTE } from "@/lib/safety-copy";
import type {
  DeterministicNutritionPhase,
  DeterministicRecoveryPhase,
  MindsetAnchor,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
  TodaySessionCompletionRecord,
} from "@/lib/types";

/** Live logging info CampDayCard resolves per session and hands to SessionCard:
 * the display status (tone + label), the stored row (for RPE/reason lines) and
 * the retro-log hook when the session is still loggable. */
export type SessionCompletionInfo = {
  display: SessionDisplayStatus;
  completion?: TodaySessionCompletionRecord;
  onLog?: () => void;
};

const titleize = formatPlanLabel;

const LIGHT_TECHNICAL_NOTE =
  "Light technical combat tag — no hard sparring here. Low-noise app work can stay on this day if prescribed.";

const COACH_LED_CONTACT_NOTE =
  "Coach-owned contact today — done with your coach alongside the app work below. Keep freshness the priority.";

function blockCountLabel(count: number): string {
  return `${count} block${count === 1 ? "" : "s"}`;
}

function blockSummaryMetric(block: StructuredBlock): string | null {
  const metric = selectBlockMetric(block)[0]?.value;
  return metric || formatBlockLoad(block.load) || formatMeasured(block.duration);
}

function CollapsibleSection({
  title,
  detailLabel,
  defaultOpen,
  syncKey,
  className,
  children,
}: {
  title: string;
  detailLabel?: string;
  defaultOpen?: boolean;
  /** When provided and it CHANGES, the open state re-syncs to `defaultOpen`.
   * Used to make the support phase follow the selected week: a new week supplies
   * a new syncKey, so the matching phase opens and the others close, while a
   * manual toggle is preserved until the next week change. Omit to keep the
   * mount-only `defaultOpen` behaviour. */
  syncKey?: string | null;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  // Reset-on-key-change during render (React's recommended pattern): re-open to
  // the new default when the sync key changes, without an effect or a flash.
  const [prevSyncKey, setPrevSyncKey] = useState<string | null | undefined>(syncKey);
  if (syncKey !== undefined && syncKey !== prevSyncKey) {
    setPrevSyncKey(syncKey);
    setOpen(Boolean(defaultOpen));
  }
  const actionTarget = detailLabel || title;
  return (
    <details
      className={`sp-collapse${className ? ` ${className}` : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary">
        <span className="sp-collapse-title">{title}</span>
        <span className="sp-collapse-action">{open ? "Hide" : "Show"} {actionTarget}</span>
      </summary>
      <div className="sp-collapse-body">{children}</div>
    </details>
  );
}

export function MindsetAnchorCard({ anchor }: { anchor?: MindsetAnchor | null }) {
  const lines = getMindsetLines(anchor);
  if (lines.length === 0) {
    return null;
  }
  const renderLine = (line: { label: string; value: string }) => (
    <li key={line.label}>
      <span className="sp-mindset-label">{line.label}</span>
      <span>{line.value}</span>
    </li>
  );
  return (
    <div className="sp-mindset">
      <p className="sp-eyebrow">Mindset</p>
      <ul className="sp-mindset-list">{lines.map(renderLine)}</ul>
    </div>
  );
}

export function BlockCard({ block }: { block: StructuredBlock }) {
  const title = cleanText(block.display_name) || "Block";
  const blockType = cleanText(block.block_type);
  const load = formatBlockLoad(block.load);
  const metrics = selectBlockMetric(block);
  const work = formatMeasured(block.work);
  const rest = shouldShowRest(block.rest) ? formatMeasured(block.rest) : null;
  const effort = formatEffort(block);
  const purpose = cleanText(block.purpose);
  const cues = getCoachingCues(block);
  const substitutions = getStringList(block.substitutions);
  const regressions = getStringList(block.regression_options);
  const progression = cleanText(block.progression_rule);

  return (
    <div className="sp-block">
      <div className="sp-block-head">
        <span className="sp-block-title">{title}</span>
        {blockType ? <span className="sp-tag">{titleize(blockType)}</span> : null}
      </div>
      {metrics.length > 0 || work || load || rest || effort ? (
        <div className="sp-block-stats">
          {metrics.map((metric) => (
            <span key={metric.label} className="sp-stat">
              <span className="sp-stat-label">{metric.label}</span>
              {metric.value}
            </span>
          ))}
          {work ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Work</span>
              {work}
            </span>
          ) : null}
          {load ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Load</span>
              {load}
            </span>
          ) : null}
          {rest ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Rest</span>
              {rest}
            </span>
          ) : null}
          {effort ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Effort</span>
              {effort}
            </span>
          ) : null}
        </div>
      ) : null}
      {purpose ? <p className="sp-block-purpose">{purpose}</p> : null}
      {cues.length > 0 ? (
        <ul className="sp-cues">
          {cues.map((cue, index) => (
            <li key={`${cue}-${index}`}>{cue}</li>
          ))}
        </ul>
      ) : null}
      {substitutions.length > 0 ? (
        <p className="sp-block-aside">
          <span className="sp-stat-label">Swaps</span>
          {substitutions.join(", ")}
        </p>
      ) : null}
      {regressions.length > 0 ? (
        <p className="sp-block-aside">
          <span className="sp-stat-label">Easier</span>
          {regressions.join(", ")}
        </p>
      ) : null}
      {progression ? (
        <p className="sp-block-aside">
          <span className="sp-stat-label">{progressionRuleLabel(progression)}</span>
          {progression}
        </p>
      ) : null}
    </div>
  );
}

function RehabSummary({ blocks }: { blocks: StructuredBlock[] }) {
  if (blocks.length === 0) {
    return null;
  }
  return (
    <div className="sp-rehab-summary">
      <p className="sp-eyebrow">Rehab / Mobility</p>
      <ul className="sp-rehab-list">
        {blocks.map((block, index) => {
          const title = cleanText(block.display_name) || "Rehab block";
          const metric = blockSummaryMetric(block);
          return (
            <li key={cleanText(block.block_id) || `${title}-${index}`}>
              <span className="sp-rehab-title">{title}</span>
              {metric ? <span className="sp-rehab-metric">{metric}</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SessionCard({
  session,
  day,
  defaultOpenBlocks,
  showDayContext = true,
  completionInfo,
}: {
  session: StructuredSession;
  day?: StructuredDay;
  defaultOpenBlocks?: boolean;
  /** When false, day-level context like warnings/nutrition/mindset is rendered by
   * the parent day card instead, so the same information does not repeat inside
   * every session. */
  showDayContext?: boolean;
  /** Live logged status for this session (plan viewer only). Absent on
   * surfaces without completion data (e.g. the Today screen's embedded card). */
  completionInfo?: SessionCompletionInfo;
}) {
  const detailsId = useId();
  const [showDetails, setShowDetails] = useState(Boolean(defaultOpenBlocks));
  const userToggledDetails = useRef(false);

  useEffect(() => {
    if (!userToggledDetails.current) {
      setShowDetails(Boolean(defaultOpenBlocks));
    }
  }, [defaultOpenBlocks]);

  const card = day?.today_card;
  const title =
    cleanText(session.title) ||
    cleanText(card?.headline) ||
    titleize(cleanText(session.session_type) || "Session");
  const sessionType = cleanText(session.session_type);
  const objective = cleanText(session.objective);
  const duration = formatMeasured(session.planned_duration);
  const date = cleanText(day?.date);
  const countdown = cleanText(day?.countdown_label);
  const warning = showDayContext ? cleanText(card?.primary_warning) : null;
  const nutrition = showDayContext ? cleanText(card?.nutrition_summary) : null;
  const weightCut = showDayContext ? cleanText(card?.weight_cut_warning) : null;
  const blocks = getBlocks(session);
  const rehabBlocks = getRehabOrMobilityBlocks(session);
  const blocksLabel = blockCountLabel(blocks.length);
  const sessionMindset =
    getMindsetLines(session.mindset_anchor).length > 0
      ? session.mindset_anchor
      : showDayContext
        ? card?.mindset_anchor
        : undefined;

  return (
    <article className="sp-session">
      <header className="sp-session-head">
        <div>
          {countdown || date ? (
            <div className="sp-day-labels sp-session-day-labels">
              {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
              {date ? <span className="sp-day-date">{formatAppDate(date)}</span> : null}
            </div>
          ) : null}
          <h4 className="sp-session-title">{title}</h4>
          {objective ? <p className="sp-session-objective">{objective}</p> : null}
        </div>
        <div className="sp-session-meta">
          {sessionType ? <span className="sp-tag">{titleize(sessionType)}</span> : null}
          {duration ? <span className="sp-tag">{duration}</span> : null}
          {completionInfo?.display.label ? (
            <span className="sp-tag sp-status-tag" data-tone={completionInfo.display.tone}>
              {completionInfo.display.label}
            </span>
          ) : null}
        </div>
      </header>

      {completionInfo?.completion &&
      (completionInfo.completion.session_rpe != null || completionInfo.completion.modification_reason) ? (
        <p className="sp-session-log-meta">
          {completionInfo.completion.session_rpe != null
            ? `RPE ${completionInfo.completion.session_rpe}/10`
            : null}
          {completionInfo.completion.session_rpe != null && completionInfo.completion.modification_reason
            ? " · "
            : null}
          {completionInfo.completion.modification_reason
            ? `Reason: ${completionInfo.completion.modification_reason}`
            : null}
        </p>
      ) : null}

      {completionInfo?.onLog ? (
        <button type="button" className="secondary-button sp-log-session" onClick={completionInfo.onLog}>
          Log this session
        </button>
      ) : null}

      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}

      <MindsetAnchorCard anchor={sessionMindset} />
      {/* The rehab/mobility summary is a compact PREVIEW of the inserts shown
          only while the full blocks are collapsed. Once expanded, every rehab
          block renders in full below, so keeping the summary too would print the
          same insert as two separate cards. */}
      {!showDetails ? <RehabSummary blocks={rehabBlocks} /> : null}

      {blocks.length > 0 ? (
        <>
          <button
            type="button"
            className="sp-more-toggle sp-session-toggle"
            aria-expanded={showDetails}
            aria-controls={detailsId}
            aria-label={showDetails ? "Show less session detail" : `Show more session detail: ${blocksLabel}`}
            onClick={() => {
              userToggledDetails.current = true;
              setShowDetails((prev) => !prev);
            }}
          >
            {showDetails ? "Show less" : `Show more (${blocksLabel})`}
          </button>

          {showDetails ? (
            <div id={detailsId} className="sp-blocks">
              {blocks.map((block, index) => (
                <BlockCard key={cleanText(block.block_id) || `block-${index}`} block={block} />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

export function TodayCard({ day }: { day: StructuredDay }) {
  const card = day.today_card;
  const headline = cleanText(card?.headline);
  const readiness = cleanText(card?.readiness_status);
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const mindsetLines = getMindsetLines(card?.mindset_anchor);
  if (
    !headline &&
    !readiness &&
    !warning &&
    !nutrition &&
    !weightCut &&
    mindsetLines.length === 0
  ) {
    return null;
  }
  return (
    <div className="sp-today">
      {headline ? <p className="sp-today-headline">{headline}</p> : null}
      {readiness ? (
        <span className="sp-tag">{titleize(readiness)}</span>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={card?.mindset_anchor} />
    </div>
  );
}

/**
 * A day with no app sessions. Coach-led / sparring / technical days legitimately
 * carry no app S&C blocks, so they are rendered as a self-contained card derived
 * deterministically from the day data (see classifySessionlessDay) instead of
 * collapsing into "Rest day.". Only a genuine rest day reads as a rest day.
 */
export function SessionlessDayCard({ day }: { day: StructuredDay }) {
  const date = cleanText(day.date);
  const countdown = cleanText(day.countdown_label);
  const card = day.today_card;
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const { kind, title, tag, coachLed } = classifySessionlessDay(day);
  const isRest = kind === "rest";

  return (
    <article className={`sp-session sp-day-card sp-day-card-${kind}`}>
      <header className="sp-session-head">
        <div>
          {countdown || date ? (
            <div className="sp-day-labels sp-session-day-labels">
              {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
              {date ? <span className="sp-day-date">{formatAppDate(date)}</span> : null}
            </div>
          ) : null}
          <h4 className="sp-session-title">{title}</h4>
        </div>
        <div className="sp-session-meta">
          {tag ? <span className="sp-tag sp-accent">{tag}</span> : null}
        </div>
      </header>
      {kind === "light_combat" ? (
        <p className="sp-today-note">{LIGHT_TECHNICAL_NOTE}</p>
      ) : coachLed ? (
        <p className="sp-today-note">No extra S&amp;C today — train with your coach and keep freshness priority.</p>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={card?.mindset_anchor} />
      {isRest ? <p className="sp-muted">Rest day.</p> : null}
    </article>
  );
}

function LightTechnicalDayContext({
  title,
  tag,
}: {
  title: string;
  tag: string | null;
}) {
  return (
    <div className="cm-light-technical">
      <div className="cm-light-technical-head">
        {tag ? <span className="sp-tag sp-accent">{tag}</span> : null}
        <p className="sp-today-headline">{title}</p>
      </div>
      <p className="sp-today-note">{LIGHT_TECHNICAL_NOTE}</p>
    </div>
  );
}

/**
 * Coach-owned contact (declared / downgraded sparring) shown above the day's app
 * sessions so the two coexist in one card instead of the sparring day silently
 * disappearing behind the low-RPE app work scheduled on the same day.
 */
function CoachLedDayContext({
  title,
  tag,
}: {
  title: string;
  tag: string | null;
}) {
  return (
    <div className="cm-light-technical cm-coach-led-contact">
      <div className="cm-light-technical-head">
        {tag ? <span className="sp-tag sp-accent">{tag}</span> : null}
        <p className="sp-today-headline">{title}</p>
      </div>
      <p className="sp-today-note">{COACH_LED_CONTACT_NOTE}</p>
    </div>
  );
}

export function DaySessionContext({ day }: { day: StructuredDay }) {
  const card = day.today_card;
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const sessionlessDay = classifySessionlessDay(day);
  const lightTechnicalContext = sessionlessDay.kind === "light_combat";
  const coachLedContact = getCoachLedContactView(day);
  // Rule: the DAY mindset renders exactly once, here at the day level, whenever
  // it exists. Session cards render with showDayContext=false, so they show ONLY
  // their own session mindset (never the day's) — this avoids both dropping the
  // day mindset when a session lacks one AND duplicating the day mindset into
  // every session. A session that defines its own mindset shows that on its card
  // in addition to this day-level one; they are distinct anchors.
  const dayMindset = card?.mindset_anchor;
  const hasDayMindset = getMindsetLines(dayMindset).length > 0;
  const hasDayContext = Boolean(
    warning || nutrition || weightCut || lightTechnicalContext || coachLedContact || hasDayMindset,
  );
  if (!hasDayContext) {
    return null;
  }

  return (
    <div className="cm-day-context">
      {lightTechnicalContext ? (
        <LightTechnicalDayContext title={sessionlessDay.title} tag={sessionlessDay.tag} />
      ) : null}
      {coachLedContact ? (
        <CoachLedDayContext title={coachLedContact.title} tag={coachLedContact.tag} />
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      {hasDayMindset ? <MindsetAnchorCard anchor={dayMindset} /> : null}
    </div>
  );
}

/** Short weekday name from an ISO date string ("2026-06-19" -> "Fri"), or null. */
function weekdayLabel(date: string | null): string | null {
  if (!date) {
    return null;
  }
  const parsed = new Date(`${date.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return weekdays[parsed.getDay()];
}

function CompletionTag({ completion }: { completion: Completion }) {
  if (completion.total === 0) {
    return null;
  }
  const done = completion.done >= completion.total && completion.total > 0;
  // "Done" is a positive, completed state — give it a calm success tone rather
  // than the brand red, which we keep reserved for current action / risk.
  return (
    <span className={`sp-tag${done ? " sp-done" : ""}`}>
      {completion.done}/{completion.total} done
    </span>
  );
}

/**
 * One day of the selected week, as a collapsible card. Collapsed by default
 * except the current/selected day so the athlete lands on what matters today;
 * the current day's session blocks are expanded too. Session-less days reuse the
 * deterministic coach-led / rest classification.
 */
export function CampDayCard({
  day,
  fallbackLabel,
  isCurrent,
  currentLabel = "Today",
  defaultOpen,
  completionIndex,
  currentTrainingDayIso,
  onLogSession,
}: {
  day: StructuredDay;
  fallbackLabel?: string;
  isCurrent?: boolean;
  /** Badge text for the highlighted day — "Today" normally, "Next session" once
   * the view has advanced past a logged today's session. */
  currentLabel?: string;
  defaultOpen?: boolean;
  /** Live completion rows keyed by training_day|session_id. When present the
   * session cards show real done/modified/skipped/missed status. */
  completionIndex?: CompletionIndex;
  /** Server-authoritative athlete-local day (drives Missed + the retro window). */
  currentTrainingDayIso?: string | null;
  /** Opens the retro-log form for a past, still-loggable session. */
  onLogSession?: (day: StructuredDay, session: StructuredSession, sessionId: string) => void;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  const userToggledOpen = useRef(false);

  useEffect(() => {
    if (!userToggledOpen.current) {
      setOpen(Boolean(defaultOpen));
    }
  }, [defaultOpen]);

  const sessions = getSessions(day);
  const date = cleanText(day.date);
  const weekday = weekdayLabel(date);
  const countdown = cleanText(day.countdown_label);
  const undatedLabel = cleanText(day.today_card?.headline) || fallbackLabel || "Training day";
  const completion = dayCompletion(day, completionIndex);
  const sessionCount = sessions.length;
  const dayIso = date ? date.slice(0, 10) : null;

  const completionInfoFor = (session: StructuredSession): SessionCompletionInfo | undefined => {
    if (!completionIndex) {
      return undefined;
    }
    const record = completionForSession(completionIndex, day, session);
    const sessionId = completionSessionId(day, session);
    // A session with no completion identity (id-less secondary) stays neutral.
    if (!sessionId) {
      return undefined;
    }
    const display = getSessionDisplayStatus(record, dayIso, currentTrainingDayIso ?? null);
    const terminal = display.state === "done" || display.state === "modified" || display.state === "skipped";
    const canLog =
      Boolean(onLogSession) && !terminal && canRetroLog(dayIso, currentTrainingDayIso ?? null);
    return {
      display,
      completion: record,
      onLog: canLog ? () => onLogSession?.(day, session, sessionId) : undefined,
    };
  };

  return (
    <details
      className={`sp-week cm-day${isCurrent ? " cm-day-current" : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary
        className="sp-week-summary cm-day-summary"
        onClick={() => {
          userToggledOpen.current = true;
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            userToggledOpen.current = true;
          }
        }}
      >
        <span className="cm-day-head">
          {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
          <span className="sp-week-title">{weekday || date || undatedLabel}</span>
        </span>

        <span className="cm-day-meta">
          {isCurrent ? <span className="sp-tag sp-accent">{currentLabel}</span> : null}
          {sessionCount > 0 ? (
            <span className="sp-tag">
              {sessionCount} session{sessionCount === 1 ? "" : "s"}
            </span>
          ) : null}
          <CompletionTag completion={completion} />
        </span>
      </summary>

      <div className="sp-week-body">
        {sessions.length > 0 ? <DaySessionContext day={day} /> : null}

        {sessions.length > 0 ? (
          <div className="sp-sessions">
            {sessions.map((session, index) => (
              <SessionCard
                key={cleanText(session.session_id) || `session-${index}`}
                session={session}
                day={index === 0 ? day : undefined}
                defaultOpenBlocks={isCurrent}
                showDayContext={false}
                completionInfo={completionInfoFor(session)}
              />
            ))}
          </div>
        ) : (
          <SessionlessDayCard day={day} />
        )}
      </div>
    </details>
  );
}

// Plan-level "active notes": the short, always-on reminders (weight cut,
// injury, nutrition, general non-negotiables) that live outside any week. Kept
// as a standalone card near the top so this context is not lost in the
// structured view the way it would be if it only existed in the raw text.
export function ActiveNotesCard({ plan }: { plan: StructuredPlan }) {
  // Drop any note that just restates a red-flag rule — the Red Flags card is the
  // single home for stop/report rules, so Active Notes stays context-only.
  const notes = getActiveNotesExcludingRedFlags(plan);
  // Collapsed by default so the plan opens short: the title + count stay visible
  // and the detail is one tap away.
  const [open, setOpen] = useState(false);
  if (notes.length === 0) {
    return null;
  }
  return (
    <details
      className="sp-collapse sp-active-notes"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary">
        <span className="sp-collapse-title">Active notes</span>
        <span className="sp-collapse-action">
          {open ? "Hide" : "Show"} ({notes.length})
        </span>
      </summary>
      <div className="sp-collapse-body">
        <ul className="sp-note-list">
          {notes.map((note, index) => (
            <li key={`${note.category}-${index}`} className={`sp-note sp-note-${note.category}`}>
              <span className="sp-note-label">{planNoteLabel(note)}</span>
              <span className="sp-note-text">{note.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

/** Map a severity label ("Red", "Amber", "High", "Low"…) to a tone class so the
 *  badge colour carries the meaning. Unknown severities stay neutral. */
function severityToneClass(label: string | null): string {
  if (!label) {
    return "";
  }
  const l = label.toLowerCase();
  if (/\b(red|high|critical|severe)\b/.test(l)) {
    return "sp-sev-red";
  }
  if (/\b(amber|orange|moderate|medium|elevated)\b/.test(l)) {
    return "sp-sev-amber";
  }
  if (/\b(green|low|mild|minor)\b/.test(l)) {
    return "sp-sev-green";
  }
  return "";
}

export function RedFlagsCard({ plan }: { plan: StructuredPlan }) {
  const rules = getDisplayableRedFlags(plan);
  const fallbackNotes = rules.length === 0 ? getFallbackSafetyNotes(plan) : [];
  const hasStopRules = rules.length > 0 || fallbackNotes.length > 0;
  // Collapsed by default to keep the plan short; the "stop & report" title stays
  // on screen so the rules are always one tap away.
  const [open, setOpen] = useState(false);
  // The safety/medical disclaimer is folded in here (it used to be a separate
  // banner) so safety lives in one block. The body therefore always renders the
  // disclaimer, with the stop/report rules above it when present.
  return (
    <details
      className="sp-collapse sp-redflags"
      aria-label="Red flags and safety actions"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary sp-redflags-summary">
        <span className="sp-redflags-summary-text">
          <span className="sp-eyebrow">Safety priority</span>
          <span className="sp-collapse-title">Red flags - stop &amp; report</span>
        </span>
        <span className="sp-collapse-action">{open ? "Hide" : "Show"}</span>
      </summary>
      <div className="sp-collapse-body">
      {hasStopRules ? (
      <ul className="sp-redflag-list">
        {rules.length > 0 ? rules.map((rule, index) => {
          const { text, action, severityLabel } = redFlagView(rule);
          // A weight-cut symptom rule is always shown, but its secondary text is
          // softened when cut risk is EXPLICITLY below moderate so it does not
          // lead. An explicit red/critical/high severity is never softened (the
          // severity is passed so it overrides), and the severity badge itself
          // always stays full-strength (see the CSS — only text is muted).
          const deEmphasised = isDeEmphasisedWeightCutSafety(plan, text, rule.severity as string);
          return (
            <li
              key={cleanText(rule.rule_id) || `flag-${index}`}
              className={`sp-redflag${deEmphasised ? " sp-redflag-deemphasised" : ""}`}
            >
              <div className="sp-redflag-head">
                <span className="sp-redflag-kicker">Stop signal</span>
                {severityLabel ? (
                  <span
                    className={`sp-tag sp-redflag-badge ${severityToneClass(severityLabel)}`.trim()}
                  >
                    {severityLabel}
                  </span>
                ) : null}
              </div>
              {text ? <span className="sp-redflag-text">{text}</span> : null}
              {action ? <p className="sp-muted">{action}</p> : null}
            </li>
          );
        }) : fallbackNotes.map((note, index) => {
          const deEmphasised = isDeEmphasisedWeightCutSafety(plan, note.text);
          return (
          <li
            key={`${note.category}-${index}`}
            className={`sp-redflag${deEmphasised ? " sp-redflag-deemphasised" : ""}`}
          >
            <div className="sp-redflag-head">
              <span className="sp-redflag-kicker">Safety note</span>
              <span className="sp-tag sp-redflag-badge">{planNoteLabel(note)}</span>
            </div>
            <span className="sp-redflag-text">{note.text}</span>
          </li>
          );
        })}
      </ul>
      ) : null}
      <SafetyNote tone="warning" showRedFlags>{PLAN_SAFETY_NOTE}</SafetyNote>
      </div>
    </details>
  );
}

/** Athlete-safe deterministic weight-cut line: risk band + supervision only. */
function DeterministicWeightCutLine({
  weightCut,
}: {
  weightCut: { band: string; supervisionRequired: boolean } | null;
}) {
  if (!weightCut) {
    return null;
  }
  return (
    <p className="sp-warning">
      <span className="sp-tag">{titleize(weightCut.band)} weight-cut risk</span>
      {weightCut.supervisionRequired ? " — qualified supervision required." : ""}
    </p>
  );
}

/** Plan nutrition prose (the legacy LLM/string fields) — fallback only. */
function NutritionProse({ plan }: { plan: StructuredPlan }) {
  const nutrition = plan.nutrition;
  const rows = [
    { label: "Summary", value: cleanText(nutrition?.summary) },
    { label: "Daily", value: cleanText(nutrition?.daily_focus) },
    { label: "Training days", value: cleanText(nutrition?.training_day_guidance) },
    { label: "Fight week", value: cleanText(nutrition?.fight_week_guidance) },
  ].filter((row) => row.value);
  const weightCut = cleanText(nutrition?.weight_cut_warning?.display_text);
  const cutRisk = cleanText(nutrition?.weight_cut_warning?.risk_level);
  const needsSupport = nutrition?.weight_cut_warning?.requires_professional_support === true;
  return (
    <>
      <ul className="sp-kv-list">
        {rows.map((row) => (
          <li key={row.label}>
            <span className="sp-kv-label">{row.label}</span>
            <span>{row.value}</span>
          </li>
        ))}
      </ul>
      {weightCut ? (
        <p className="sp-warning">
          {cutRisk && cutRisk !== "none" ? (
            <>
              <span className="sp-tag">{titleize(cutRisk)} risk</span>{" "}
            </>
          ) : null}
          {weightCut}
          {needsSupport ? " — qualified supervision required." : ""}
        </p>
      ) : null}
    </>
  );
}

type NutritionPhaseItem = {
  phase: string;
  phaseKey: string | null;
  rows: { label: string; value: string }[];
  weightCut: { band: string; supervisionRequired: boolean } | null;
};

type RecoveryPhaseItem = {
  phase: string;
  phaseKey: string | null;
  view: ReturnType<typeof recoveryPhaseView>;
  lists: { label: string; items: string[] }[];
};

/** Index of the support phase matching the viewed week (else the first phase),
 * so nutrition/recovery open on the phase the athlete is actually looking at. */
function resolveActiveSupportPhaseIndex(
  items: { phaseKey: string | null }[],
  activePhaseKey: string | null,
): number {
  if (activePhaseKey) {
    const match = items.findIndex((item) => item.phaseKey === activePhaseKey);
    if (match >= 0) {
      return match;
    }
  }
  return 0;
}

function getNutritionPhaseItems(plan: StructuredPlan): NutritionPhaseItem[] {
  return getDeterministicNutritionPhases(plan)
    .map(({ phase, entry }: { phase: string; entry: DeterministicNutritionPhase }) => {
      const rows = nutritionPhaseRows(entry);
      const weightCut = formatWeightCutBand(entry.weight_cut);
      if (rows.length === 0 && !weightCut) {
        return null;
      }
      return { phase, phaseKey: normalizeSupportPhaseKey(phase), rows, weightCut };
    })
    .filter((item): item is NutritionPhaseItem => item !== null);
}

function getRecoveryPhaseItems(plan: StructuredPlan): RecoveryPhaseItem[] {
  return getDeterministicRecoveryPhases(plan)
    .map(({ phase, entry }: { phase: string; entry: DeterministicRecoveryPhase }) => {
      const view = recoveryPhaseView(entry);
      const lists: { label: string; items: string[] }[] = [
        { label: "Core", items: view.coreStrategies },
        { label: "Phase focus", items: view.phaseFocus },
        { label: "Fatigue", items: view.fatigue },
        { label: "Age", items: view.ageAdjustments },
      ].filter((group) => group.items.length > 0);
      if (!view.sleep && lists.length === 0 && !view.weightCut) {
        return null;
      }
      return { phase, phaseKey: normalizeSupportPhaseKey(phase), view, lists };
    })
    .filter((item): item is RecoveryPhaseItem => item !== null);
}

function NutritionPhaseCard({
  item,
  defaultOpen,
  syncKey,
}: {
  item: NutritionPhaseItem;
  defaultOpen?: boolean;
  syncKey?: string | null;
}) {
  const phaseLabel = titleize(item.phase);
  return (
    <section className="sp-card sp-support-card sp-nutrition">
      <div className="sp-support-head">
        <p className="sp-eyebrow">Nutrition</p>
        <span className="sp-tag">{phaseLabel}</span>
      </div>
      <CollapsibleSection
        title={phaseLabel}
        detailLabel={`${phaseLabel} nutrition`}
        defaultOpen={defaultOpen}
        syncKey={syncKey}
        className="sp-nutrition-phase"
      >
        <ul className="sp-kv-list">
          {item.rows.map((row) => (
            <li key={row.label}>
              <span className="sp-kv-label">{row.label}</span>
              <span>{row.value}</span>
            </li>
          ))}
        </ul>
        <DeterministicWeightCutLine weightCut={item.weightCut} />
      </CollapsibleSection>
    </section>
  );
}

function RecoveryPhaseCard({
  item,
  defaultOpen,
  syncKey,
}: {
  item: RecoveryPhaseItem;
  defaultOpen?: boolean;
  syncKey?: string | null;
}) {
  const phaseLabel = titleize(item.phase);
  return (
    <section className="sp-card sp-support-card sp-recovery">
      <div className="sp-support-head">
        <p className="sp-eyebrow">Recovery</p>
        <span className="sp-tag">{phaseLabel}</span>
      </div>
      <CollapsibleSection
        title={phaseLabel}
        detailLabel={`${phaseLabel} recovery`}
        defaultOpen={defaultOpen}
        syncKey={syncKey}
        className="sp-recovery-phase"
      >
        <ul className="sp-kv-list">
          {item.view.sleep ? (
            <li>
              <span className="sp-kv-label">Sleep</span>
              <span>{item.view.sleep}</span>
            </li>
          ) : null}
          {item.lists.map((group) => (
            <li key={group.label}>
              <span className="sp-kv-label">{group.label}</span>
              <span>{group.items.join("; ")}</span>
            </li>
          ))}
        </ul>
        <DeterministicWeightCutLine weightCut={item.view.weightCut} />
      </CollapsibleSection>
    </section>
  );
}

// Owns the full nutrition details. Deterministic Stage 1 macros/hydration/fuel
// timing win when present; the legacy prose fields are the fallback only. Never
// renders coach_gated (it is stripped server-side before reaching the frontend).
export function NutritionCard({
  plan,
  activePhaseKey = null,
}: {
  plan: StructuredPlan;
  /** Normalized phase key of the week the athlete is viewing. The matching
   * phase opens by default so a taper/SPP week does not land on expanded GPP. */
  activePhaseKey?: string | null;
}) {
  const items = getNutritionPhaseItems(plan);
  if (items.length === 0 && !hasNutrition(plan)) {
    return null;
  }
  if (items.length === 0) {
    return (
      <section className="sp-card sp-nutrition">
        <p className="sp-eyebrow">Nutrition</p>
        <NutritionProse plan={plan} />
      </section>
    );
  }
  const openIndex = resolveActiveSupportPhaseIndex(items, activePhaseKey);
  return (
    <div className="sp-phase-support-grid">
      {items.map((item, index) => (
        <NutritionPhaseCard
          key={item.phase}
          item={item}
          defaultOpen={index === openIndex}
          syncKey={activePhaseKey ?? ""}
        />
      ))}
    </div>
  );
}

// Owns recovery detail (sleep / fatigue / phase focus / core actions). Renders
// deterministic Stage 1 recovery; never coach_gated. Stop/modify/report
// thresholds stay with RedFlagsCard, so this card does not repeat them.
export function RecoveryCard({
  plan,
  activePhaseKey = null,
}: {
  plan: StructuredPlan;
  activePhaseKey?: string | null;
}) {
  const items = getRecoveryPhaseItems(plan);
  if (items.length === 0) {
    return null;
  }
  const openIndex = resolveActiveSupportPhaseIndex(items, activePhaseKey);
  return (
    <div className="sp-phase-support-grid">
      {items.map((item, index) => (
        <RecoveryPhaseCard
          key={item.phase}
          item={item}
          defaultOpen={index === openIndex}
          syncKey={activePhaseKey ?? ""}
        />
      ))}
    </div>
  );
}

/** Horizontal, mobile-scrollable strip of week pills used to pick the week. */
function WeekStrip({
  weeks,
  selectedPos,
  currentPos,
  onSelect,
  completionIndex,
}: {
  weeks: StructuredWeek[];
  selectedPos: number;
  currentPos: number | null;
  onSelect: (pos: number) => void;
  completionIndex?: CompletionIndex;
}) {
  return (
    <nav className="cm-week-strip" aria-label="Camp weeks">
      {weeks.map((week, pos) => {
        const completion = weekCompletion(week, completionIndex);
        const phase = cleanText(week.phase_label);
        const index =
          typeof week.week_index === "number" && Number.isFinite(week.week_index)
            ? week.week_index
            : pos + 1;
        const selected = pos === selectedPos;
        const current = pos === currentPos;
        return (
          <button
            key={cleanText(week.week_id) || `week-${pos}`}
            type="button"
            className={`cm-week-pill${selected ? " cm-week-pill-selected" : ""}${
              current ? " cm-week-pill-current" : ""
            }`}
            aria-current={current ? "step" : undefined}
            aria-pressed={selected}
            onClick={() => onSelect(pos)}
          >
            <span className="cm-week-pill-index">W{index}</span>
            {phase ? <span className="cm-week-pill-phase">{titleize(phase)}</span> : null}
            {completion.total > 0 ? (
              <span className="cm-week-pill-completion">
                {completion.done}/{completion.total}
              </span>
            ) : null}
            {current ? <span className="cm-week-pill-now">Now</span> : null}
          </button>
        );
      })}
    </nav>
  );
}

/** The selected week's countdown/dates, load proxy and completion.
 *  The week goal is already shown in the heading via weekLabel, and the phase is
 *  already visible in the week pill, so this overview avoids repeating it. */
function WeekOverview({
  week,
  completionIndex,
}: {
  week: StructuredWeek;
  completionIndex?: CompletionIndex;
}) {
  const load = weekLoadProxy(week);
  const completion = weekCompletion(week, completionIndex);
  const sessionSummary = weekSessionSummary(week);
  const countdownStart = cleanText(week.countdown_start);
  const countdownEnd = cleanText(week.countdown_end);
  const countdownRange =
    countdownStart && countdownEnd
      ? `${countdownStart} → ${countdownEnd}`
      : countdownStart || countdownEnd;
  const startDate = cleanText(week.start_date);
  const endDate = cleanText(week.end_date);
  const dateRange =
    startDate && endDate ? `${startDate} → ${endDate}` : startDate || endDate;

  const rows = [
    { label: "Countdown", value: countdownRange },
    { label: "Dates", value: dateRange },
    { label: "Load", value: load },
    {
      label: "Training days",
      value: sessionSummary.trainingDays > 0 ? `${sessionSummary.trainingDays}` : null,
    },
    {
      label: "Sessions",
      value: sessionSummary.appSessions > 0 ? `${sessionSummary.appSessions}` : null,
    },
    {
      label: "Coach-led",
      value: sessionSummary.coachLedSessions > 0 ? `${sessionSummary.coachLedSessions}` : null,
    },
    {
      label: "Completion",
      value: completion.total > 0 ? `${completion.done}/${completion.total}` : null,
    },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value));

  return (
    <section className="sp-card cm-week-overview">
      <div className="cm-week-overview-head">
        <p className="sp-eyebrow">Week overview</p>
        <h4 className="sp-redflags-title">{weekLabel(week)}</h4>
      </div>

      {rows.length > 0 ? (
        <div className="sp-block-stats cm-week-overview-stats">
          {rows.map((row) => (
            <span key={row.label} className="sp-stat">
              <span className="sp-stat-label">{row.label}</span>
              {row.value}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function StructuredPlanRenderer({
  plan,
  today,
  focusDay,
  currentDayLabel = "Today",
  completions,
  currentTrainingDayIso,
  onLogSession,
}: {
  plan: StructuredPlan;
  today?: Date;
  /** Accepted for compatibility with callers, but not rendered on this plan view. */
  createdAt?: string | null;
  /** Accepted for compatibility with callers, but not rendered on this plan view. */
  planStatus?: string | null;
  /** Optional advance target: the next scheduled session's day, passed once
   * today is already logged. It moves ONLY the opened week + day highlight, never
   * the truthful current week marker. Omit it for the normal calendar view. */
  focusDay?: Date;
  /** Badge text for the highlighted day. Callers pass "Next session" alongside
   * `focusDay` so the advanced day is not mislabelled "Today". */
  currentDayLabel?: string;
  /** Live completion rows from /api/plans/{id}/completions. When present the
   * day cards colour every session from real logging instead of the static
   * generation-time statuses. */
  completions?: readonly TodaySessionCompletionRecord[] | null;
  /** Server-authoritative athlete-local training day (YYYY-MM-DD). */
  currentTrainingDayIso?: string | null;
  /** Opens the retro-log flow for a past, still-loggable session. */
  onLogSession?: (day: StructuredDay, session: StructuredSession, sessionId: string) => void;
}) {
  const weeks = getWeeks(plan);
  const completionIndex = useMemo(
    () => (completions ? buildCompletionIndex(completions) : undefined),
    [completions],
  );

  // Resolve "today" through the shared 04:00 training-day rollover so Plan Detail
  // and the Today tab can never disagree on the current day.
  const mountedDay = useTrainingDay();

  // The real calendar training day owns the truthful current week marker.
  // `focusDay` only advances the opened week/day highlight.
  const calendarProgress = resolvePlanProgress(plan, today ?? mountedDay);
  const resolvedFocusDay = focusDay
    ? resolveNextPlanFocusDay(plan, today ?? mountedDay, focusDay)
    : undefined;
  const focusProgress = resolvedFocusDay
    ? resolvePlanProgress(plan, resolvedFocusDay)
    : calendarProgress;

  // `selectedPos` holds ONLY an explicit manual week choice; while it is null the
  // view auto-follows the plan's current week via the fallback in `effectivePos`
  // below (so no effect is needed to sync it, and there is no render loop).
  const [selectedPos, setSelectedPos] = useState<number | null>(null);

  // A stable identity for the current plan's week structure. When the component
  // is handed a different plan without remounting — e.g. the plan viewer swaps an
  // adapted text plan for the richer structured payload — a retained manual
  // `selectedPos` could point at a week index from the OLD structure. Reset it
  // DURING render (React's recommended "reset state on prop change" pattern):
  // this drops the stale selection before anything renders, so the wrong week is
  // never briefly shown, with no extra effect/render pass.
  const weekSignature = useMemo(
    () =>
      `${weeks.length}:` +
      weeks
        .map((week) => cleanText(week.week_id) || cleanText(week.start_date) || "")
        .join("|"),
    [weeks],
  );
  const [prevWeekSignature, setPrevWeekSignature] = useState(weekSignature);
  if (weekSignature !== prevWeekSignature) {
    setPrevWeekSignature(weekSignature);
    setSelectedPos(null);
  }

  const handleSelectWeek = (pos: number) => {
    setSelectedPos(pos);
  };

  const effectivePos = selectedPos ?? focusProgress.currentWeekPos ?? 0;
  const safePos = effectivePos >= 0 && effectivePos < weeks.length ? effectivePos : 0;
  const selectedWeek = weeks[safePos];

  const progressionNotes = cleanText(plan.progression_notes);
  const rawFallback = cleanText(plan.raw_markdown_fallback);
  const hasNutritionSupport = getNutritionPhaseItems(plan).length > 0 || hasNutrition(plan);
  const hasRecoverySupport = getRecoveryPhaseItems(plan).length > 0;
  const dayList = selectedWeek ? getDays(selectedWeek) : [];
  // Open the support phase that matches the week the athlete is viewing.
  const activeSupportPhaseKey = normalizeSupportPhaseKey(selectedWeek?.phase_label);

  return (
    <div className="sp-root cm-root">
      {weeks.length > 0 ? (
        <>
          <WeekStrip
            weeks={weeks}
            selectedPos={safePos}
            currentPos={calendarProgress.currentWeekPos}
            onSelect={handleSelectWeek}
            completionIndex={completionIndex}
          />

          {selectedWeek ? (
            <WeekOverview week={selectedWeek} completionIndex={completionIndex} />
          ) : null}

          <div className="sp-weeks cm-days">
            {dayList.length > 0 ? (
              dayList.map((day, index) => {
                const isCurrent =
                  focusProgress.currentDayDate != null &&
                  cleanText(day.date)?.slice(0, 10) === focusProgress.currentDayDate;

                return (
                  <CampDayCard
                    key={cleanText(day.date) || `day-${index}`}
                    day={day}
                    fallbackLabel={`Training day ${index + 1}`}
                    isCurrent={isCurrent}
                    currentLabel={currentDayLabel}
                    defaultOpen={isCurrent || (focusProgress.currentWeekPos == null && index === 0)}
                    completionIndex={completionIndex}
                    currentTrainingDayIso={currentTrainingDayIso}
                    onLogSession={onLogSession}
                  />
                );
              })
            ) : (
              <p className="sp-muted">No days scheduled this week.</p>
            )}
          </div>
        </>
      ) : null}

            {progressionNotes ? (
        <section className="sp-card sp-progression">
          <p className="sp-eyebrow">Progression notes</p>
          <p className="sp-block-purpose">{progressionNotes}</p>
        </section>
      ) : null}

      {hasRecoverySupport ? (
        <CollapsibleSection
          title="Recovery"
          detailLabel="recovery"
          className="cm-support-section"
        >
          <RecoveryCard plan={plan} activePhaseKey={activeSupportPhaseKey} />
        </CollapsibleSection>
      ) : null}

      {hasNutritionSupport ? (
        <CollapsibleSection
          title="Nutrition"
          detailLabel="nutrition"
          className="cm-support-section"
        >
          <NutritionCard plan={plan} activePhaseKey={activeSupportPhaseKey} />
        </CollapsibleSection>
      ) : null}

      <ActiveNotesCard plan={plan} />
      <RedFlagsCard plan={plan} />

      {rawFallback ? (
        <details className="sp-collapse cm-raw-fallback">
          <summary className="sp-collapse-summary">
            <span className="sp-collapse-title">Original plan text</span>
            <span className="sp-collapse-action">Show original</span>
          </summary>
          <div className="sp-collapse-body">
            <pre className="cm-raw-pre">{rawFallback}</pre>
          </div>
        </details>
      ) : null}
    </div>
  );
}
