"use client";

import { useState, type ReactNode } from "react";

import {
  cleanText,
  formatBlockLoad,
  formatEffort,
  formatMeasured,
  getBlocks,
  getCoachingCues,
  getDays,
  getDisplayableRedFlags,
  formatWeightCutBand,
  getDeterministicNutritionPhases,
  getDeterministicRecoveryPhases,
  getMindsetLines,
  getSessions,
  getStringList,
  getWeeks,
  hasDeterministicNutrition,
  hasDeterministicRecovery,
  hasNutrition,
  nutritionPhaseRows,
  recoveryPhaseView,
  redFlagView,
  selectBlockMetric,
  shouldShowRest,
  splitMindsetLines,
  weekLabel,
} from "@/lib/structured-plan";
import { formatPlanLabel } from "@/lib/plan-labels";
import type {
  MindsetAnchor,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

const titleize = formatPlanLabel;

function CollapsibleSection({
  title,
  defaultOpen,
  className,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  return (
    <details
      className={`sp-collapse${className ? ` ${className}` : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary">
        <span className="sp-collapse-title">{title}</span>
      </summary>
      <div className="sp-collapse-body">{children}</div>
    </details>
  );
}

export function MindsetAnchorCard({ anchor }: { anchor?: MindsetAnchor | null }) {
  const { primary, secondary } = splitMindsetLines(anchor);
  const [showMore, setShowMore] = useState(false);
  if (primary.length === 0 && secondary.length === 0) {
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
      <p className="sp-eyebrow sp-accent">Mindset</p>
      <ul className="sp-mindset-list">{primary.map(renderLine)}</ul>
      {secondary.length > 0 ? (
        <>
          {showMore ? <ul className="sp-mindset-list">{secondary.map(renderLine)}</ul> : null}
          <button
            type="button"
            className="sp-more-toggle"
            aria-expanded={showMore}
            onClick={() => setShowMore((prev) => !prev)}
          >
            {showMore ? "Less" : "More"}
          </button>
        </>
      ) : null}
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

export function SessionCard({ session }: { session: StructuredSession }) {
  const title = cleanText(session.title) || titleize(cleanText(session.session_type) || "Session");
  const sessionType = cleanText(session.session_type);
  const objective = cleanText(session.objective);
  const duration = formatMeasured(session.planned_duration);
  const blocks = getBlocks(session);

  return (
    <article className="sp-session">
      <header className="sp-session-head">
        <div>
          <h4 className="sp-session-title">{title}</h4>
          {objective ? <p className="sp-session-objective">{objective}</p> : null}
        </div>
        <div className="sp-session-meta">
          {sessionType ? <span className="sp-tag sp-accent">{titleize(sessionType)}</span> : null}
          {duration ? <span className="sp-tag">{duration}</span> : null}
        </div>
      </header>
      <MindsetAnchorCard anchor={session.mindset_anchor} />
      {blocks.length > 0 ? (
        <div className="sp-blocks">
          {blocks.map((block, index) => (
            <BlockCard key={cleanText(block.block_id) || `block-${index}`} block={block} />
          ))}
        </div>
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
        <span className="sp-tag sp-accent">{titleize(readiness)}</span>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={card?.mindset_anchor} />
    </div>
  );
}

export function DaySection({ day }: { day: StructuredDay }) {
  const date = cleanText(day.date);
  const countdown = cleanText(day.countdown_label);
  const dayType = cleanText(day.day_type);
  const sessions = getSessions(day);

  return (
    <section className="sp-day">
      <header className="sp-day-head">
        <div className="sp-day-labels">
          {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
          {date ? <span className="sp-day-date">{date}</span> : null}
        </div>
        {dayType ? <span className="sp-tag">{titleize(dayType)}</span> : null}
      </header>
      <TodayCard day={day} />
      {sessions.length > 0 ? (
        <div className="sp-sessions">
          {sessions.map((session, index) => (
            <SessionCard
              key={cleanText(session.session_id) || `session-${index}`}
              session={session}
            />
          ))}
        </div>
      ) : (
        <p className="sp-muted">Rest day.</p>
      )}
    </section>
  );
}

export function WeekSection({ week, defaultOpen }: { week: StructuredWeek; defaultOpen?: boolean }) {
  // Track open state locally and sync via onToggle so a user-opened/collapsed
  // week is not reset to defaultOpen when the parent re-renders. (A bare
  // `open={defaultOpen}` would force the native <details> back on every render.)
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  const days = getDays(week);
  const phase = cleanText(week.phase_label);
  return (
    <details
      className="sp-week"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-week-summary">
        <span className="sp-week-title">{weekLabel(week)}</span>
        {phase ? <span className="sp-tag sp-accent">{phase}</span> : null}
      </summary>
      <div className="sp-week-body">
        {days.length > 0 ? (
          days.map((day, index) => (
            <DaySection key={cleanText(day.date) || `day-${index}`} day={day} />
          ))
        ) : (
          <p className="sp-muted">No days scheduled.</p>
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
    <header className="sp-header">
      <p className="sp-eyebrow sp-accent">Structured plan</p>
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

export function RedFlagsCard({ plan }: { plan: StructuredPlan }) {
  const rules = getDisplayableRedFlags(plan);
  if (rules.length === 0) {
    return null;
  }
  return (
    <section className="sp-card sp-redflags">
      <p className="sp-eyebrow sp-accent">Red flags — stop &amp; report</p>
      <ul className="sp-redflag-list">
        {rules.map((rule, index) => {
          const { text, action, severityLabel } = redFlagView(rule);
          return (
            <li key={cleanText(rule.rule_id) || `flag-${index}`} className="sp-redflag">
              <div className="sp-redflag-head">
                <span className="sp-redflag-kicker">Red flag</span>
                {severityLabel ? (
                  <span className="sp-tag sp-redflag-badge">{severityLabel}</span>
                ) : null}
              </div>
              {text ? <span className="sp-redflag-text">{text}</span> : null}
              {action ? <p className="sp-muted">{action}</p> : null}
            </li>
          );
        })}
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

// Owns the full nutrition details. Deterministic Stage 1 macros/hydration/fuel
// timing win when present; the legacy prose fields are the fallback only. Never
// renders coach_gated (it is stripped server-side before reaching the frontend).
export function NutritionCard({ plan }: { plan: StructuredPlan }) {
  const deterministic = hasDeterministicNutrition(plan);
  if (!deterministic && !hasNutrition(plan)) {
    return null;
  }
  return (
    <section className="sp-card sp-nutrition">
      <p className="sp-eyebrow sp-accent">Nutrition</p>
      {deterministic ? (
        getDeterministicNutritionPhases(plan)
          .map(({ phase, entry }) => {
            const rows = nutritionPhaseRows(entry);
            const weightCut = formatWeightCutBand(entry.weight_cut);
            if (rows.length === 0 && !weightCut) {
              return null;
            }
            return { phase, rows, weightCut };
          })
          .filter((item): item is NonNullable<typeof item> => item !== null)
          .map((item, index) => (
            <CollapsibleSection
              key={item.phase}
              title={titleize(item.phase)}
              defaultOpen={index === 0}
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
          ))
      ) : (
        <NutritionProse plan={plan} />
      )}
    </section>
  );
}

// Owns recovery detail (sleep / fatigue / phase focus / core actions). Renders
// deterministic Stage 1 recovery; never coach_gated. Stop/modify/report
// thresholds stay with RedFlagsCard, so this card does not repeat them.
export function RecoveryCard({ plan }: { plan: StructuredPlan }) {
  if (!hasDeterministicRecovery(plan)) {
    return null;
  }
  return (
    <section className="sp-card sp-recovery">
      <p className="sp-eyebrow sp-accent">Recovery</p>
      {getDeterministicRecoveryPhases(plan)
        .map(({ phase, entry }) => {
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
          return { phase, view, lists };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null)
        .map((item, index) => (
          <CollapsibleSection
            key={item.phase}
            title={titleize(item.phase)}
            defaultOpen={index === 0}
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
        ))}
    </section>
  );
}

export function RawFallbackPanel({ rawText }: { rawText: string }) {
  const [open, setOpen] = useState(false);
  const text = rawText.trim();
  if (!text) {
    return null;
  }
  return (
    <div className="sp-raw">
      <button type="button" className="ghost-button" onClick={() => setOpen((prev) => !prev)}>
        {open ? "Hide original plan text" : "Show original plan text"}
      </button>
      {open ? <pre className="plan-text-block">{text}</pre> : null}
    </div>
  );
}

export function StructuredPlanRenderer({
  plan,
  rawFallback,
  showRawFallback = false,
}: {
  plan: StructuredPlan;
  rawFallback?: string;
  showRawFallback?: boolean;
}) {
  const weeks = getWeeks(plan);
  const progressionNotes = cleanText(plan.progression_notes);
  return (
    <div className="sp-root">
      <PlanHeader plan={plan} />
      <RedFlagsCard plan={plan} />
      <div className="sp-weeks">
        {weeks.map((week, index) => (
          <WeekSection
            key={cleanText(week.week_id) || `week-${index}`}
            week={week}
            defaultOpen={index === 0}
          />
        ))}
      </div>
      <NutritionCard plan={plan} />
      <RecoveryCard plan={plan} />
      {progressionNotes ? (
        <section className="sp-card sp-progression">
          <p className="sp-eyebrow sp-accent">Progression notes</p>
          <p className="sp-block-purpose">{progressionNotes}</p>
        </section>
      ) : null}
      {showRawFallback && rawFallback ? <RawFallbackPanel rawText={rawFallback} /> : null}
    </div>
  );
}
