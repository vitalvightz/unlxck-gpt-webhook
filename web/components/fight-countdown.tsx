"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { getFightCountdown } from "@/lib/fight-countdown";
import { formatPlanFightDate } from "@/lib/plan-format";
import type { StructuredPlan } from "@/lib/types";

const COUNT_MS = 1100;

/** True once the element has scrolled into view (immediately where
 * IntersectionObserver is unavailable), so the animation plays when the athlete
 * actually sees the card rather than off-screen on load. Waits for `ready` so
 * it starts only once the plan's weeks (bar + starting count) have loaded. */
function useRevealed<T extends Element>(ready: boolean): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!ready || !node || revealed) return;
    if (typeof IntersectionObserver === "undefined") {
      const frame = requestAnimationFrame(() => setRevealed(true));
      return () => cancelAnimationFrame(frame);
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setRevealed(true);
          observer.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ready, revealed]);
  return [ref, revealed];
}

/** Ticks the day count down from the camp's length to today's value once the
 * card is revealed, in step with the bar's CSS fill. Renders the final value on
 * the server and skips the animation under reduced motion. */
function useCountdownTick(target: number, from: number | null, revealed: boolean): number {
  const [animated, setAnimated] = useState<number | null>(null);
  useLayoutEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!revealed || reduce || from === null || from <= target) {
      return;
    }
    let frame = 0;
    const start = performance.now();
    // The first frame runs before the next paint, so the count starts at `from`.
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / COUNT_MS);
      const eased = 1 - Math.pow(1 - t, 3);
      setAnimated(t < 1 ? Math.round(from - (from - target) * eased) : null);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, from, revealed]);
  return animated ?? target;
}

/**
 * Overview fight-camp countdown: days to fight night, a gold camp-progress bar
 * with the current week and phase, and the next phase change. Renders nothing
 * without a fight date (open plans) or after fight day, so the caller can drop
 * it in unconditionally.
 */
export function FightCountdown({
  fightDate,
  trainingDay,
  phase,
  plan,
}: {
  fightDate: string | null | undefined;
  trainingDay: string | null | undefined;
  phase?: string | null;
  plan?: StructuredPlan | null;
}) {
  const countdown = getFightCountdown({ fightDate, trainingDay, phase, plan });
  const [ref, revealed] = useRevealed<HTMLElement>(countdown?.pct != null);
  const shown = useCountdownTick(countdown?.daysOut ?? 0, countdown?.campDays ?? null, revealed);
  if (!countdown) {
    return null;
  }

  const { daysOut, fightDateISO, pct, weekLabel, phaseLabel, nextLabel } = countdown;
  const fightDay = daysOut === 0;
  const meta = [weekLabel, phaseLabel].filter(Boolean).join(" · ");
  const label = fightDay ? "Fight day" : `${daysOut} ${daysOut === 1 ? "day" : "days"} to fight night`;

  return (
    <section
      ref={ref}
      className="fight-countdown"
      data-revealed={revealed ? "true" : undefined}
      data-pending={pct !== null && !revealed ? "true" : undefined}
      aria-label={`Fight countdown: ${label}`}
    >
      <div className="fight-countdown-head">
        <div>
          <p className="fight-countdown-kicker">Fight camp</p>
          <p className="fight-countdown-days" aria-hidden="true">
            {fightDay ? (
              "Fight day"
            ) : (
              <>
                <span className="fight-countdown-number">{shown}</span>{" "}
                {daysOut === 1 ? "day" : "days"} to fight night
              </>
            )}
          </p>
          <p className="fight-countdown-date">{formatPlanFightDate(fightDateISO)}</p>
        </div>
        {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
      </div>
      {pct !== null ? (
        <div
          className="overview-progress-track fight-countdown-track"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Camp progress"
        >
          <span className="overview-progress-fill fight-countdown-fill" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      {nextLabel ? (
        <p className="fight-countdown-next">
          <span className="fight-countdown-next-label">Next</span> {nextLabel}
        </p>
      ) : null}
    </section>
  );
}
