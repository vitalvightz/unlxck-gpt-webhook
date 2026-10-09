"use client";

import { getFightCampCountdown, type OpenScheduleHints } from "@/lib/camp-map";
import { formatPlanFightDate } from "@/lib/plan-format";
import type { StructuredPlan, TodaySessionCompletionRecord } from "@/lib/types";

function inDays(daysAway: number): string {
  return daysAway === 1 ? "tomorrow" : `in ${daysAway} days`;
}

/**
 * Fight-camp countdown shared by Overview (full card) and Today (compact row):
 * days to fight night — or to the end of an open plan's renewable block — the
 * phase timeline with today's marker, and the next milestone. Renders nothing
 * until there's enough of a plan to count down from (see getFightCampCountdown),
 * so callers can drop it in unconditionally.
 */
export function FightCampCountdown({
  plan,
  trainingDay,
  completions,
  hints,
  variant = "today",
}: {
  plan: StructuredPlan | null | undefined;
  trainingDay: Date | null;
  completions?: readonly TodaySessionCompletionRecord[] | null;
  hints?: OpenScheduleHints | null;
  variant?: "today" | "overview";
}) {
  const countdown = getFightCampCountdown(plan, trainingDay, { completions, hints });
  if (!countdown) {
    return null;
  }

  const { mode, daysOut, headline, pct, weekLabel, phaseLabel, segments, nextMilestone, banked } = countdown;
  const rounded = Math.round(pct);
  const isFight = mode === "fight";
  const dayZero = daysOut === 0;
  const kicker = isFight ? "Fight camp" : "Training block";
  const targetPhrase = isFight ? "to fight night" : "left in this block";
  const meta = [weekLabel, phaseLabel].filter(Boolean).join(" · ");
  const nextLine = nextMilestone ? `${nextMilestone.label} ${inDays(nextMilestone.daysAway)}` : null;
  const ariaLabel = [
    isFight ? "Fight camp countdown" : "Training block countdown",
    dayZero ? headline : `${headline} ${targetPhrase}`,
    weekLabel,
    phaseLabel,
  ]
    .filter(Boolean)
    .join(", ");

  const track = (
    <div className="fight-countdown-track" aria-hidden="true">
      {segments.map((segment) => (
        <span
          key={`${segment.key}-${segment.startPct}`}
          className="fight-countdown-segment"
          data-current={segment.current ? "true" : undefined}
          data-phase={segment.key}
          style={{ left: `${segment.startPct}%`, width: `${segment.widthPct}%` }}
        />
      ))}
      <span className="fight-countdown-marker" style={{ left: `${pct}%` }} />
    </div>
  );

  if (variant === "today") {
    return (
      <div
        className="fight-countdown"
        data-variant="today"
        role="progressbar"
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel}
      >
        <div className="fight-countdown-head">
          <span className="fight-countdown-compact-days">
            {dayZero ? headline : <>{headline} <span className="fight-countdown-compact-target">{targetPhrase}</span></>}
          </span>
          {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
        </div>
        {track}
        {nextLine ? <p className="fight-countdown-next-inline">Next: {nextLine}</p> : null}
      </div>
    );
  }

  const [count, ...unitWords] = dayZero ? [headline] : headline.split(" ");
  return (
    <section
      className="fight-countdown"
      data-variant="overview"
      role="progressbar"
      aria-valuenow={rounded}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
    >
      <div className="fight-countdown-hero">
        <div>
          <p className="kicker fight-countdown-kicker">{kicker}</p>
          <p className="fight-countdown-days">
            <span className="fight-countdown-number">{count}</span>
            {unitWords.length ? (
              <span className="fight-countdown-unit">{unitWords.join(" ")} {targetPhrase}</span>
            ) : null}
          </p>
          {isFight && countdown.targetISO ? (
            <p className="fight-countdown-date">{formatPlanFightDate(countdown.targetISO)}</p>
          ) : null}
        </div>
        {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
      </div>
      {track}
      {segments.length > 1 ? (
        <div className="fight-countdown-legend" aria-hidden="true">
          {segments.map((segment) => (
            <span
              key={`${segment.key}-${segment.startPct}`}
              className="fight-countdown-legend-item"
              data-current={segment.current ? "true" : undefined}
              style={{ left: `${segment.startPct}%`, width: `${segment.widthPct}%` }}
            >
              {segment.label}
            </span>
          ))}
        </div>
      ) : null}
      <div className="fight-countdown-footer">
        {nextLine ? (
          <div className="fight-countdown-stat">
            <span className="fight-countdown-stat-label">Next up</span>
            <span className="fight-countdown-stat-value">{nextLine}</span>
          </div>
        ) : null}
        {banked ? (
          <div className="fight-countdown-stat">
            <span className="fight-countdown-stat-label">Banked</span>
            <span className="fight-countdown-stat-value">
              {banked.done} of {banked.total} sessions
            </span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
