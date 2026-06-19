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
  getDays,
  getDisplayableRedFlags,
  getFallbackSafetyNotes,
  getPlanNotes,
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
  findDayByISO,
  getReadinessStrip,
  resolvePlanProgress,
  weekCompletion,
  weekLoadProxy,
  type Completion,
} from "@/lib/camp-map";
import { useTrainingDay } from "@/lib/use-training-day";
import { formatPlanLabel } from "@/lib/plan-labels";
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
}: {
  session: StructuredSession;
  day?: StructuredDay;
  defaultOpenBlocks?: boolean;
}) {
  const detailsId = useId();
  const [showDetails, setShowDetails] = useState(Boolean(defaultOpenBlocks));
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
  const readiness = cleanText(card?.readiness_status);
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const blocks = getBlocks(session);
  const rehabBlocks = getRehabOrMobilityBlocks(session);
  const blocksLabel = blockCountLabel(blocks.length);

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
          {readiness ? <span className="sp-tag">{titleize(readiness)}</span> : null}
          {sessionType ? <span className="sp-tag">{titleize(sessionType)}</span> : null}
          {duration ? <span className="sp-tag">{duration}</span> : null}
        </div>
      </header>
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={session.mindset_anchor} />
      <RehabSummary blocks={rehabBlocks} />
      {blocks.length > 0 ? (
        <>
          <button
            type="button"
            className="sp-more-toggle sp-session-toggle"
            aria-expanded={showDetails}
            aria-controls={detailsId}
            aria-label={showDetails ? "Show less session detail" : `Show more session detail: ${blocksLabel}`}
            onClick={() => setShowDetails((prev) => !prev)}
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
  defaultOpen,
}: {
  day: StructuredDay;
  isCurrent?: boolean;
  defaultOpen?: boolean;
}) {
  // Local open state synced via onToggle so a user toggle is not reset on
  // re-render (a bare open={defaultOpen} would force <details> back each render).
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  const sessions = getSessions(day);
  const date = cleanText(day.date);
  const weekday = weekdayLabel(date);
  const countdown = cleanText(day.countdown_label);
  const dayType = cleanText(day.day_type);
  const warning = cleanText(day.today_card?.primary_warning);
  const completion = dayCompletion(day);
  const sessionCount = sessions.length;

  return (
    <details
      className={`sp-week cm-day${isCurrent ? " cm-day-current" : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-week-summary cm-day-summary">
        <span className="cm-day-head">
          {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
          <span className="sp-week-title">{weekday || date || "Day"}</span>
        </span>
        <span className="cm-day-meta">
          {isCurrent ? <span className="sp-tag sp-accent">Today</span> : null}
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
        {warning ? <p className="sp-warning">{warning}</p> : null}
        {sessions.length > 0 ? (
          <div className="sp-sessions">
            {sessions.map((session, index) => (
              <SessionCard
                key={cleanText(session.session_id) || `session-${index}`}
                session={session}
                day={index === 0 ? day : undefined}
                defaultOpenBlocks={isCurrent}
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

export function PlanHeader({ plan }: { plan: StructuredPlan }) {
  const meta = plan.plan_metadata;
  const title = cleanText(meta?.title) || "Training Plan";
  const sport = cleanText(meta?.sport);
  const planType = cleanText(meta?.plan_type);
  const athlete = plan.athlete_context;
  const profile = cleanText(athlete?.sport_profile) || cleanText(athlete?.style_profile);
  const event = plan.event_context;
  const eventType = cleanText(event?.event_type);
  const eventDate = cleanText(event?.fight_date) || cleanText(event?.match_date);

  const tags = [sport, planType ? titleize(planType) : null, eventType ? titleize(eventType) : null]
    .filter((tag): tag is string => Boolean(tag));

  return (
    <header className="sp-header cm-command">
      <p className="sp-eyebrow">Camp map</p>
      <h3 className="sp-title">{title}</h3>
      {profile ? <p className="sp-subtitle">{profile}</p> : null}
      {tags.length > 0 || eventDate ? (
        <div className="sp-header-tags">
          {tags.map((tag, index) => (
            <span key={`${tag}-${index}`} className="sp-tag">
              {tag}
            </span>
          ))}
          {eventDate ? <span className="sp-tag sp-accent">{eventDate}</span> : null}
        </div>
      ) : null}
    </header>
  );
}

// Plan-level "active notes": the short, always-on reminders (weight cut,
// injury, nutrition, general non-negotiables) that live outside any week. Kept
// as a standalone card near the top so this context is not lost in the
// structured view the way it would be if it only existed in the raw text.
export function ActiveNotesCard({ plan }: { plan: StructuredPlan }) {
  const notes = getPlanNotes(plan);
  if (notes.length === 0) {
    return null;
  }
  return (
    <section className="sp-card sp-active-notes">
      <p className="sp-eyebrow">Active notes</p>
      <ul className="sp-note-list">
        {notes.map((note, index) => (
          <li key={`${note.category}-${index}`} className={`sp-note sp-note-${note.category}`}>
            <span className="sp-note-label">{planNoteLabel(note)}</span>
            <span className="sp-note-text">{note.text}</span>
          </li>
        ))}
      </ul>
    </section>
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
  if (rules.length === 0 && fallbackNotes.length === 0) {
    return null;
  }
  return (
    <section className="sp-card sp-redflags" aria-label="Red flags and safety actions">
      <div className="sp-redflags-head">
        <p className="sp-eyebrow">Safety priority</p>
        <h4 className="sp-redflags-title">Red flags - stop &amp; report</h4>
      </div>
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
    </section>
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

/** Compact camp-status chips: phase, "Week X of Y", D-label, event date. */
function CampStatusLine({
  plan,
  progress,
  phaseWeek,
}: {
  plan: StructuredPlan;
  progress: ReturnType<typeof resolvePlanProgress>;
  phaseWeek?: StructuredWeek;
}) {
  const phase = cleanText(phaseWeek?.phase_label);
  const eventDate =
    cleanText(plan.event_context?.fight_date) || cleanText(plan.event_context?.match_date);
  const weekPosLabel =
    progress.currentWeekPos != null
      ? `Week ${progress.currentWeekPos + 1} of ${progress.weekCount}`
      : progress.weekCount > 0
        ? `${progress.weekCount} week camp`
        : null;
  const chips = [
    phase ? titleize(phase) : null,
    weekPosLabel,
    progress.dLabel,
    eventDate ? `Fight ${eventDate}` : null,
  ].filter((chip): chip is string => Boolean(chip));
  if (chips.length === 0) {
    return null;
  }
  return (
    <div className="cm-status-line" aria-label="Camp status">
      {chips.map((chip, index) => (
        <span key={`${chip}-${index}`} className="cm-status-chip">
          {chip}
        </span>
      ))}
    </div>
  );
}

/** Compact readiness/risk strip — only cards that have data; no fake metrics. */
function ReadinessStripCards({
  plan,
  currentDay,
  focusWeek,
}: {
  plan: StructuredPlan;
  currentDay: StructuredDay | null;
  focusWeek?: StructuredWeek;
}) {
  const strip = getReadinessStrip(plan, currentDay, focusWeek);
  const cards = [
    { label: "Today call", value: strip.todayCall, risk: false },
    { label: "Focus", value: strip.focus, risk: false },
    { label: "Injury watch", value: strip.risk, risk: true },
    { label: "Load", value: strip.load, risk: false },
  ].filter((card): card is { label: string; value: string; risk: boolean } => Boolean(card.value));
  if (cards.length === 0) {
    return null;
  }
  return (
    <section className="cm-readiness" aria-label="Readiness">
      {cards.map((card) => (
        <article
          key={card.label}
          className={`cm-readiness-card${card.risk ? " cm-readiness-risk" : ""}`}
        >
          <p className="cm-readiness-label">{card.label}</p>
          <p className="cm-readiness-value">{card.value}</p>
        </article>
      ))}
    </section>
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

/** The selected week's purpose, phase, countdown/dates, load proxy, completion. */
function WeekOverview({ week }: { week: StructuredWeek }) {
  const phase = cleanText(week.phase_label);
  const goal = cleanText(week.week_goal);
  const load = weekLoadProxy(week);
  const completion = weekCompletion(week);
  const days = getDays(week);
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
  const warning = days
    .map((day) => cleanText(day.today_card?.primary_warning))
    .find((value): value is string => Boolean(value));
  const rows = [
    { label: "Phase", value: phase ? titleize(phase) : null },
    { label: "Countdown", value: countdownRange },
    { label: "Dates", value: dateRange },
    { label: "Load", value: load },
    { label: "Days", value: days.length > 0 ? `${days.length}` : null },
    {
      label: "Completed",
      value: completion.total > 0 ? `${completion.done}/${completion.total}` : null,
    },
  ].filter((row): row is { label: string; value: string } => Boolean(row.value));

  return (
    <section className="sp-card cm-week-overview">
      <div className="cm-week-overview-head">
        <p className="sp-eyebrow">This week</p>
        <h4 className="sp-redflags-title">{weekLabel(week)}</h4>
      </div>
      {goal ? <p className="sp-block-purpose">{goal}</p> : null}
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
      {warning ? <p className="sp-warning">{warning}</p> : null}
    </section>
  );
}

export function StructuredPlanRenderer({
  plan,
  today,
}: {
  plan: StructuredPlan;
  today?: Date;
}) {
  const weeks = getWeeks(plan);
  // Resolve "today" through the shared 04:00 training-day rollover so Plan Detail
  // and the Today tab can never disagree on the current day. The hook is null
  // until the client mounts (SSR-safe: no hydration mismatch) and advances
  // across the rollover on long-lived tabs. Tests pass an explicit `today`.
  const mountedDay = useTrainingDay();
  const now = today ?? mountedDay;
  const progress = resolvePlanProgress(plan, now);
  const currentDay = findDayByISO(plan, progress.currentDayDate);
  // The selected week is user-controllable; default to the current week (or the
  // first week when today falls outside the camp). `selectedPos` stays null until
  // the user picks a week so that, once the client-mounted current week resolves,
  // the view follows it instead of being stuck on the first-render default.
  const [selectedPos, setSelectedPos] = useState<number | null>(null);
  const userSelectedWeek = useRef(false);
  useEffect(() => {
    if (!userSelectedWeek.current && progress.currentWeekPos != null) {
      setSelectedPos(progress.currentWeekPos);
    }
  }, [progress.currentWeekPos]);
  const handleSelectWeek = (pos: number) => {
    userSelectedWeek.current = true;
    setSelectedPos(pos);
  };
  const effectivePos = selectedPos ?? progress.currentWeekPos ?? 0;
  // Clamp against weeks length so a stale index can never index past the array.
  const safePos = effectivePos >= 0 && effectivePos < weeks.length ? effectivePos : 0;
  const selectedWeek = weeks[safePos];
  const phaseWeek = weeks[progress.currentWeekPos ?? safePos] ?? selectedWeek;
  const focusWeek = currentDay ? weeks[progress.currentWeekPos ?? 0] : selectedWeek;

  const progressionNotes = cleanText(plan.progression_notes);
  const rawFallback = cleanText(plan.raw_markdown_fallback);
  const hasNutritionSupport = getNutritionPhaseItems(plan).length > 0 || hasNutrition(plan);
  const hasRecoverySupport = getRecoveryPhaseItems(plan).length > 0;
  const dayList = getDays(selectedWeek);

  return (
    <div className="sp-root cm-root">
      <PlanHeader plan={plan} />
      <CampStatusLine plan={plan} progress={progress} phaseWeek={phaseWeek} />
      <ReadinessStripCards plan={plan} currentDay={currentDay} focusWeek={focusWeek} />
      <ActiveNotesCard plan={plan} />
      <RedFlagsCard plan={plan} />

      {weeks.length > 0 ? (
        <>
          <WeekStrip
            weeks={weeks}
            selectedPos={safePos}
            currentPos={progress.currentWeekPos}
            onSelect={handleSelectWeek}
          />
          {selectedWeek ? <WeekOverview week={selectedWeek} /> : null}
          <div className="sp-weeks cm-days">
            {dayList.length > 0 ? (
              dayList.map((day, index) => {
                const isCurrent =
                  progress.currentDayDate != null &&
                  cleanText(day.date)?.slice(0, 10) === progress.currentDayDate;
                return (
                  <CampDayCard
                    key={cleanText(day.date) || `day-${index}`}
                    day={day}
                    isCurrent={isCurrent}
                    defaultOpen={isCurrent || (progress.currentWeekPos == null && index === 0)}
                  />
                );
              })
            ) : (
              <p className="sp-muted">No days scheduled this week.</p>
            )}
          </div>
        </>
      ) : null}

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
