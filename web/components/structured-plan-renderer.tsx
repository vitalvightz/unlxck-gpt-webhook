"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import {
  classifySessionlessDay,
  cleanText,
  formatBlockLoad,
  formatEffort,
  formatMeasured,
  getBlocks,
  getCoachingCues,
  getActiveNotesExcludingRedFlags,
  getDays,
  getDisplayableRedFlags,
  getFallbackSafetyNotes,
  getRehabOrMobilityBlocks,
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
  dayCompletion,
  resolveNextPlanFocusDay,
  resolvePlanProgress,
  weekCompletion,
  weekLoadProxy,
  weekSessionSummary,
  type Completion,
} from "@/lib/camp-map";
import { useTrainingDay } from "@/lib/use-training-day";
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
} from "@/lib/types";

const titleize = formatPlanLabel;

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
  className,
  children,
}: {
  title: string;
  detailLabel?: string;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
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
          <span className="sp-stat-label">Progress</span>
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
}: {
  session: StructuredSession;
  day?: StructuredDay;
  defaultOpenBlocks?: boolean;
  /** When false, day-level context like warnings/nutrition/mindset is rendered by
   * the parent day card instead, so the same information does not repeat inside
   * every session. */
  showDayContext?: boolean;
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
  const dayType = cleanText(day?.day_type);
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
              {date ? <span className="sp-day-date">{date}</span> : null}
            </div>
          ) : null}
          <h4 className="sp-session-title">{title}</h4>
          {objective ? <p className="sp-session-objective">{objective}</p> : null}
        </div>
        <div className="sp-session-meta">
          {dayType ? <span className="sp-tag">{titleize(dayType)}</span> : null}
          {sessionType ? <span className="sp-tag">{titleize(sessionType)}</span> : null}
          {duration ? <span className="sp-tag">{duration}</span> : null}
        </div>
      </header>

      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}

      <MindsetAnchorCard anchor={sessionMindset} />
      <RehabSummary blocks={rehabBlocks} />

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
  const dayType = cleanText(day.day_type);
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
              {date ? <span className="sp-day-date">{date}</span> : null}
            </div>
          ) : null}
          <h4 className="sp-session-title">{title}</h4>
        </div>
        <div className="sp-session-meta">
          {dayType ? <span className="sp-tag">{titleize(dayType)}</span> : null}
          {tag ? <span className="sp-tag sp-accent">{tag}</span> : null}
        </div>
      </header>
      {coachLed ? (
        <p className="sp-today-note">No app S&amp;C today — train with your coach and keep freshness priority.</p>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={card?.mindset_anchor} />
      {isRest ? <p className="sp-muted">Rest day.</p> : null}
    </article>
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
  isCurrent,
  currentLabel = "Today",
  defaultOpen,
}: {
  day: StructuredDay;
  isCurrent?: boolean;
  /** Badge text for the highlighted day — "Today" normally, "Next session" once
   * the view has advanced past a logged today's session. */
  currentLabel?: string;
  defaultOpen?: boolean;
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
  const dayType = cleanText(day.day_type);
  const card = day.today_card;
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const hasDayContext = Boolean(warning || nutrition || weightCut);
  const completion = dayCompletion(day);
  const sessionCount = sessions.length;

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
          <span className="sp-week-title">{weekday || date || "Day"}</span>
        </span>

        <span className="cm-day-meta">
          {isCurrent ? <span className="sp-tag sp-accent">{currentLabel}</span> : null}
          {dayType ? <span className="sp-tag">{titleize(dayType)}</span> : null}
          {sessionCount > 0 ? (
            <span className="sp-tag">
              {sessionCount} session{sessionCount === 1 ? "" : "s"}
            </span>
          ) : null}
          <CompletionTag completion={completion} />
        </span>
      </summary>

      <div className="sp-week-body">
        {sessions.length > 0 && hasDayContext ? (
          <div className="cm-day-context">
            {warning ? <p className="sp-warning">{warning}</p> : null}
            {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
            {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
          </div>
        ) : null}

        {sessions.length > 0 ? (
          <div className="sp-sessions">
            {sessions.map((session, index) => (
              <SessionCard
                key={cleanText(session.session_id) || `session-${index}`}
                session={session}
                day={index === 0 ? day : undefined}
                defaultOpenBlocks={isCurrent}
                showDayContext={false}
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

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * Format an ISO date/timestamp's date portion as "11 Jun 2026", or null.
 * Parses the YYYY-MM-DD prefix directly (no Date) so the output is timezone- and
 * locale-stable — renderToStaticMarkup must produce the same string everywhere.
 */
function formatGeneratedDate(value: string | null | undefined): string | null {
  const iso = cleanText(value)?.slice(0, 10);
  const match = iso ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso) : null;
  if (!match) {
    return null;
  }
  const [, year, month, day] = match;
  const monthName = MONTH_ABBR[Number(month) - 1];
  if (!monthName) {
    return null;
  }
  return `${Number(day)} ${monthName} ${year}`;
}

// Statuses that mean a saved plan is genuinely publishable/ready get the calm
// success tone; every other lifecycle state (awaiting review, safety hold,
// archived, still processing) stays a neutral pill so an unsafe or in-progress
// plan never reads as "good to go".
const SUCCESS_STATUS_TOKENS = new Set(["ready", "publishable_with_flags"]);

function statusTagClass(status: string): string {
  const token = status.toLowerCase().replace(/[\s-]+/g, "_");
  return SUCCESS_STATUS_TOKENS.has(token) ? "sp-tag sp-done" : "sp-tag";
}

export function PlanHeader({
  plan,
  createdAt,
  planStatus,
}: {
  plan: StructuredPlan;
  /** ISO date/timestamp the plan was generated (from the plan record), shown as
   * "Generated <date>". Omitted in contexts without a record (e.g. previews). */
  createdAt?: string | null;
  /** The saved plan record's authoritative lifecycle status. This wins; the
   * structured plan_metadata.status is only a fallback for preview/test contexts
   * that have no record, because it uses a different vocabulary
   * (draft/active/completed/archived) that must not override the record's
   * ready/held_for_review/publishable_with_flags states. */
  planStatus?: string | null;
}) {
  const meta = plan.plan_metadata;
  const title = cleanText(meta?.title) || "Training Plan";
  const sport = cleanText(meta?.sport);
  const planType = cleanText(meta?.plan_type);
  const athlete = plan.athlete_context;
  const profile = cleanText(athlete?.sport_profile) || cleanText(athlete?.style_profile);
  const event = plan.event_context;
  const eventType = cleanText(event?.event_type);
  const eventDate = cleanText(event?.fight_date) || cleanText(event?.match_date);
  // The saved-plan record status is authoritative; plan_metadata.status is only a
  // fallback for record-less preview/test contexts.
  const status = cleanText(planStatus) || cleanText(meta?.status);
  const generatedOn = formatGeneratedDate(createdAt);

  const tags = [sport, planType ? titleize(planType) : null, eventType ? titleize(eventType) : null]
    .filter((tag): tag is string => Boolean(tag));

  return (
    <header className="sp-header cm-command">
      <p className="sp-eyebrow">Camp map</p>
      <h3 className="sp-title">{title}</h3>
      {profile ? <p className="sp-subtitle">{profile}</p> : null}
      {tags.length > 0 || eventDate || status ? (
        <div className="sp-header-tags">
          {status ? <span className={statusTagClass(status)}>{titleize(status)}</span> : null}
          {tags.map((tag, index) => (
            <span key={`${tag}-${index}`} className="sp-tag">
              {tag}
            </span>
          ))}
          {eventDate ? <span className="sp-tag sp-accent">{eventDate}</span> : null}
        </div>
      ) : null}
      {generatedOn ? <p className="sp-header-meta">Generated {generatedOn}</p> : null}
    </header>
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
          return (
            <li key={cleanText(rule.rule_id) || `flag-${index}`} className="sp-redflag">
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
        }) : fallbackNotes.map((note, index) => (
          <li key={`${note.category}-${index}`} className="sp-redflag">
            <div className="sp-redflag-head">
              <span className="sp-redflag-kicker">Safety note</span>
              <span className="sp-tag sp-redflag-badge">{planNoteLabel(note)}</span>
            </div>
            <span className="sp-redflag-text">{note.text}</span>
          </li>
        ))}
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
}: {
  item: NutritionPhaseItem;
  defaultOpen?: boolean;
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
}: {
  item: RecoveryPhaseItem;
  defaultOpen?: boolean;
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
export function NutritionCard({ plan }: { plan: StructuredPlan }) {
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
  return (
    <div className="sp-phase-support-grid">
      {items.map((item, index) => (
        <NutritionPhaseCard key={item.phase} item={item} defaultOpen={index === 0} />
      ))}
    </div>
  );
}

// Owns recovery detail (sleep / fatigue / phase focus / core actions). Renders
// deterministic Stage 1 recovery; never coach_gated. Stop/modify/report
// thresholds stay with RedFlagsCard, so this card does not repeat them.
export function RecoveryCard({ plan }: { plan: StructuredPlan }) {
  const items = getRecoveryPhaseItems(plan);
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="sp-phase-support-grid">
      {items.map((item, index) => (
        <RecoveryPhaseCard key={item.phase} item={item} defaultOpen={index === 0} />
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
}: {
  weeks: StructuredWeek[];
  selectedPos: number;
  currentPos: number | null;
  onSelect: (pos: number) => void;
}) {
  return (
    <nav className="cm-week-strip" aria-label="Camp weeks">
      {weeks.map((week, pos) => {
        const completion = weekCompletion(week);
        const phase = cleanText(week.phase_label);
        const index = typeof week.week_index === "number" ? week.week_index : pos + 1;
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
function WeekOverview({ week }: { week: StructuredWeek }) {
  const load = weekLoadProxy(week);
  const completion = weekCompletion(week);
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
}) {
  const weeks = getWeeks(plan);

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

  const [selectedPos, setSelectedPos] = useState<number | null>(null);
  const userSelectedWeek = useRef(false);

  useEffect(() => {
    if (!userSelectedWeek.current && focusProgress.currentWeekPos != null) {
      setSelectedPos(focusProgress.currentWeekPos);
    }
  }, [focusProgress.currentWeekPos]);

  const handleSelectWeek = (pos: number) => {
    userSelectedWeek.current = true;
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

  return (
    <div className="sp-root cm-root">
      {weeks.length > 0 ? (
        <>
          <WeekStrip
            weeks={weeks}
            selectedPos={safePos}
            currentPos={calendarProgress.currentWeekPos}
            onSelect={handleSelectWeek}
          />

          {selectedWeek ? <WeekOverview week={selectedWeek} /> : null}

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
                    isCurrent={isCurrent}
                    currentLabel={currentDayLabel}
                    defaultOpen={isCurrent || (focusProgress.currentWeekPos == null && index === 0)}
                  />
                );
              })
            ) : (
              <p className="sp-muted">No days scheduled this week.</p>
            )}
          </div>
        </>
      ) : null}

      <ActiveNotesCard plan={plan} />
      <RedFlagsCard plan={plan} />

      {hasRecoverySupport || hasNutritionSupport ? (
        <section className="sp-card cm-support" aria-label="Support">
          <p className="sp-eyebrow">Support</p>

          {hasRecoverySupport ? (
            <CollapsibleSection title="Recovery" detailLabel="recovery">
              <RecoveryCard plan={plan} />
            </CollapsibleSection>
          ) : null}

          {hasNutritionSupport ? (
            <CollapsibleSection title="Nutrition" detailLabel="nutrition">
              <NutritionCard plan={plan} />
            </CollapsibleSection>
          ) : null}
        </section>
      ) : null}

      {progressionNotes ? (
        <section className="sp-card sp-progression">
          <p className="sp-eyebrow">Progression notes</p>
          <p className="sp-block-purpose">{progressionNotes}</p>
        </section>
      ) : null}

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