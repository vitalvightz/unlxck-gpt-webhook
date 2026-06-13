"use client";

import { useState } from "react";

import {
  cleanText,
  formatBlockLoad,
  formatEffort,
  formatMeasured,
  getBlocks,
  getCoachingCues,
  getDays,
  getDisplayableRedFlags,
  getMindsetLines,
  getSessions,
  getWeeks,
  hasNutrition,
  selectBlockMetric,
  shouldShowRest,
  weekLabel,
} from "@/lib/structured-plan";
import type {
  MindsetAnchor,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

function titleize(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function MindsetAnchorCard({ anchor }: { anchor?: MindsetAnchor | null }) {
  const lines = getMindsetLines(anchor);
  if (lines.length === 0) {
    return null;
  }
  return (
    <div className="sp-mindset">
      <p className="sp-eyebrow sp-accent">Mindset</p>
      <ul className="sp-mindset-list">
        {lines.map((line) => (
          <li key={line.label}>
            <span className="sp-mindset-label">{line.label}</span>
            <span>{line.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function BlockCard({ block }: { block: StructuredBlock }) {
  const title = cleanText(block.display_name) || "Block";
  const blockType = cleanText(block.block_type);
  const load = formatBlockLoad(block.load);
  const metric = selectBlockMetric(block);
  const rest = shouldShowRest(block.rest) ? formatMeasured(block.rest) : null;
  const effort = formatEffort(block);
  const purpose = cleanText(block.purpose);
  const cues = getCoachingCues(block);

  return (
    <div className="sp-block">
      <div className="sp-block-head">
        <span className="sp-block-title">{title}</span>
        {blockType ? <span className="sp-tag">{titleize(blockType)}</span> : null}
      </div>
      {metric || load || rest || effort ? (
        <div className="sp-block-stats">
          {metric ? (
            <span className="sp-stat">
              <span className="sp-stat-label">{metric.label}</span>
              {metric.value}
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
  if (!headline && !readiness && !warning && !nutrition && !weightCut) {
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
  const days = getDays(week);
  const phase = cleanText(week.phase_label);
  return (
    <details className="sp-week" open={defaultOpen}>
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
          const text = cleanText(rule.display_text);
          const action = cleanText(rule.action);
          const severity = cleanText(rule.severity);
          return (
            <li key={cleanText(rule.rule_id) || `flag-${index}`} className="sp-redflag">
              <span className="sp-redflag-text">{text}</span>
              {severity ? <span className="sp-tag">{titleize(severity)}</span> : null}
              {action ? <p className="sp-muted">{action}</p> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function NutritionCard({ plan }: { plan: StructuredPlan }) {
  if (!hasNutrition(plan)) {
    return null;
  }
  const nutrition = plan.nutrition;
  const rows = [
    { label: "Summary", value: cleanText(nutrition?.summary) },
    { label: "Daily", value: cleanText(nutrition?.daily_focus) },
    { label: "Training days", value: cleanText(nutrition?.training_day_guidance) },
    { label: "Fight week", value: cleanText(nutrition?.fight_week_guidance) },
  ].filter((row) => row.value);
  const weightCut = cleanText(nutrition?.weight_cut_warning?.display_text);

  return (
    <section className="sp-card sp-nutrition">
      <p className="sp-eyebrow sp-accent">Nutrition</p>
      <ul className="sp-kv-list">
        {rows.map((row) => (
          <li key={row.label}>
            <span className="sp-kv-label">{row.label}</span>
            <span>{row.value}</span>
          </li>
        ))}
      </ul>
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
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
      {showRawFallback && rawFallback ? <RawFallbackPanel rawText={rawFallback} /> : null}
    </div>
  );
}
