"use client";

import { getFightCampCountdown, type FightCampCountdown as Countdown, type OpenScheduleHints } from "@/lib/camp-map";
import { formatPlanFightDate } from "@/lib/plan-format";
import type { StructuredPlan, TodaySessionCompletionRecord } from "@/lib/types";

function inDays(daysAway: number): string {
  return daysAway === 1 ? "tomorrow" : `in ${daysAway} days`;
}

/** Gold timeline: filled up to today, phase boundaries as hairlines, key
 * milestones (last hard spar, weigh-in) as pins and fight night as the end cap. */
function CountdownTrack({ countdown, showPins }: { countdown: Countdown; showPins: boolean }) {
  const { pct, segments, milestones, mode } = countdown;
  const pins = showPins
    ? milestones.filter(
        (milestone) =>
          !milestone.label.endsWith(" begins") &&
          milestone.label !== "Fight night" &&
          // Too close to the end cap to read as its own point.
          milestone.pct < 96,
      )
    : [];
  return (
    <div className="fight-countdown-track" aria-hidden="true">
      <span className="fight-countdown-fill" style={{ width: `${pct}%` }} />
      {segments.slice(1).map((segment) => (
        <span
          key={`${segment.key}-${segment.startPct}`}
          className="fight-countdown-divider"
          data-passed={segment.startPct <= pct ? "true" : undefined}
          style={{ left: `${segment.startPct}%` }}
        />
      ))}
      {pins.map((pin) => (
        <span
          key={`${pin.label}-${pin.iso}`}
          className="fight-countdown-pin"
          data-passed={pin.passed ? "true" : undefined}
          style={{ left: `${pin.pct}%` }}
        />
      ))}
      <span className="fight-countdown-marker" style={{ left: `${pct}%` }} />
      {mode === "fight" ? <span className="fight-countdown-endcap" /> : null}
    </div>
  );
}

/**
 * Fight-camp countdown shared by Overview (full card) and Today (compact row):
 * days to fight night — or to the end of an open plan's renewable block — the
 * gold camp timeline with today's position, and the next milestone. Renders
 * nothing until there's enough of a plan to count down from (see
 * getFightCampCountdown), so callers can drop it in unconditionally.
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
  const targetPhrase = isFight ? "to fight night" : "left in this block";
  const meta = [weekLabel, phaseLabel].filter(Boolean).join(" · ");
  const ariaLabel = [
    isFight ? "Fight camp countdown" : "Training block countdown",
    dayZero ? headline : `${headline} ${targetPhrase}`,
    weekLabel,
    phaseLabel,
  ]
    .filter(Boolean)
    .join(", ");
  const progressProps = {
    role: "progressbar" as const,
    "aria-valuenow": rounded,
    "aria-valuemin": 0,
    "aria-valuemax": 100,
    "aria-label": ariaLabel,
  };

  if (variant === "today") {
    return (
      <div className="fight-countdown" data-variant="today" {...progressProps}>
        <div className="fight-countdown-head">
          <span className="fight-countdown-compact-days">
            {dayZero ? (
              <span className="fight-countdown-gold">{headline}</span>
            ) : (
              <>
                <span className="fight-countdown-gold">{headline}</span>{" "}
                <span className="fight-countdown-compact-target">{targetPhrase}</span>
              </>
            )}
          </span>
          {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
        </div>
        <CountdownTrack countdown={countdown} showPins={false} />
        {nextMilestone ? (
          <p className="fight-countdown-next-inline">
            <span className="fight-countdown-next-label">Next</span>
            {nextMilestone.label}
            <span className="fight-countdown-gold"> {inDays(nextMilestone.daysAway)}</span>
          </p>
        ) : null}
      </div>
    );
  }

  const [count, ...unitWords] = dayZero ? [headline] : headline.split(" ");
  const unit = unitWords.length ? `${unitWords.join(" ")} ${targetPhrase}` : null;
  return (
    <section className="fight-countdown" data-variant="overview" {...progressProps}>
      <div className="fight-countdown-hero">
        <div className="fight-countdown-hero-copy">
          <p className="fight-countdown-kicker">{isFight ? "Fight camp" : "Training block"}</p>
          <p className="fight-countdown-number">{count}</p>
          {unit ? <p className="fight-countdown-unit">{unit}</p> : null}
        </div>
        <div className="fight-countdown-hero-side">
          {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
          {isFight && countdown.targetISO ? (
            <span className="fight-countdown-date">{formatPlanFightDate(countdown.targetISO)}</span>
          ) : null}
        </div>
      </div>

      <div className="fight-countdown-timeline">
        <CountdownTrack countdown={countdown} showPins />
        {segments.length > 1 ? (
          <div className="fight-countdown-legend" aria-hidden="true">
            {segments.map((segment) => (
              <span
                key={`${segment.key}-${segment.startPct}`}
                className="fight-countdown-legend-item"
                data-current={segment.current ? "true" : undefined}
                data-passed={!segment.current && segment.startPct + segment.widthPct <= pct ? "true" : undefined}
                style={{ left: `${segment.startPct}%`, width: `${segment.widthPct}%` }}
              >
                {segment.label}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="fight-countdown-stats">
        {nextMilestone ? (
          <div className="fight-countdown-stat" data-emphasis="true">
            <span className="fight-countdown-stat-label">Next up</span>
            <span className="fight-countdown-stat-value">{nextMilestone.label}</span>
            <span className="fight-countdown-stat-sub">{inDays(nextMilestone.daysAway)}</span>
          </div>
        ) : null}
        {banked ? (
          <div className="fight-countdown-stat">
            <span className="fight-countdown-stat-label">Banked</span>
            <span className="fight-countdown-stat-value">
              {banked.done}
              <span className="fight-countdown-stat-of"> / {banked.total}</span>
            </span>
            <span className="fight-countdown-stat-sub">sessions trained</span>
          </div>
        ) : null}
        <div className="fight-countdown-stat">
          <span className="fight-countdown-stat-label">{isFight ? "Camp" : "Block"}</span>
          <span className="fight-countdown-stat-value">{rounded}%</span>
          <span className="fight-countdown-stat-sub">complete</span>
        </div>
      </div>
    </section>
  );
}
