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

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** Ticks the day count down from the camp's length to today's value once the
 * card is revealed, in step with the bar's CSS fill. From reveal until the last
 * frame it shows the animated value (starting at `from`), so today's count
 * never flashes before the tick-down. Renders the final value on the server and
 * skips the animation under reduced motion. Plays once per mount. */
function useCountdownTick(target: number, from: number | null, revealed: boolean): number {
  const [animated, setAnimated] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const willAnimate = from !== null && from > target && !prefersReducedMotion();
  useLayoutEffect(() => {
    if (!revealed || done || !willAnimate || from === null) {
      return;
    }
    let frame = 0;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / COUNT_MS);
      const eased = 1 - Math.pow(1 - t, 3);
      if (t < 1) {
        setAnimated(Math.round(from - (from - target) * eased));
        frame = requestAnimationFrame(step);
      } else {
        setDone(true);
      }
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, from, revealed, done, willAnimate]);
  if (revealed && willAnimate && !done) {
    return animated ?? from;
  }
  return target;
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

/** Placeholder text block: shimmer sized by its (invisible) text. */
function Bone({ children }: { children: string }) {
  return <span className="skeleton skeleton-text fight-countdown-bone">{children}</span>;
}

/** Placeholder shown in the countdown's slot while the plan calendar loads
 * (like the XP card's skeleton), so Overview lays out once and the card fills
 * in place instead of popping in later. It reuses the card's own markup with
 * invisible stand-in text, so it is the card's exact size at every width. */
export function FightCountdownSkeleton() {
  return (
    <section className="fight-countdown fight-countdown-skeleton" aria-busy="true" aria-label="Fight countdown loading">
      <div className="fight-countdown-head">
        <div>
          <p className="fight-countdown-kicker"><Bone>Fight camp</Bone></p>
          <p className="fight-countdown-days">
            <span className="fight-countdown-number"><Bone>00</Bone></span> <Bone>days to fight night</Bone>
          </p>
          <p className="fight-countdown-date"><Bone>Sat 00 Nov 0000</Bone></p>
        </div>
        <span className="fight-countdown-meta"><Bone>Week 0 of 0 · General prep</Bone></span>
      </div>
      <div className="overview-progress-track fight-countdown-track" aria-hidden="true" />
      <p className="fight-countdown-next"><Bone>Next Specific prep starts in 00 days</Bone></p>
    </section>
  );
}
