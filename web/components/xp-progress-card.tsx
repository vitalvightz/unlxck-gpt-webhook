"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { Skeleton } from "@/components/skeleton";
import { useXp, type XpDailyRewardStatus } from "@/components/xp-provider";
import { XP_ACTIONS, resolveXpLevel, type XpState } from "@/lib/xp";

const XP_TOTAL_ANIMATION_MS = 640;
const numberFormatter = new Intl.NumberFormat("en-GB");

export type XpProgressCardViewProps = {
  state: XpState;
  dailyRewardStatus: XpDailyRewardStatus;
  isNewAward?: boolean;
  isNewDailyAward?: boolean;
  previousTotalXp?: number;
};

export function prefersReducedXpMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function XpProgressCardSkeleton() {
  return (
    <article className="status-card overview-command-card xp-progress-card xp-progress-card-skeleton" aria-busy="true">
      <Skeleton variant="text" width={92} height={12} />
      <Skeleton variant="text" width="58%" height={18} />
      <Skeleton variant="text" width="42%" height={38} />
      <Skeleton variant="block" width="100%" height={9} />
      <Skeleton variant="text" width="40%" height={12} />
      <div className="xp-progress-skeleton-details">
        <Skeleton variant="text" width="72%" height={38} />
        <Skeleton variant="text" width="72%" height={38} />
      </div>
    </article>
  );
}

export function XpProgressCardView({
  state,
  dailyRewardStatus,
  isNewAward = false,
  isNewDailyAward = false,
  previousTotalXp = state.totalXp,
}: XpProgressCardViewProps) {
  const progress = useMemo(() => resolveXpLevel(state.totalXp), [state.totalXp]);
  const previousProgress = useMemo(
    () => resolveXpLevel(isNewAward ? previousTotalXp : 0),
    [isNewAward, previousTotalXp],
  );
  const startPercentage = isNewAward ? previousProgress.percentage : 0;
  const [displayPercentage, setDisplayPercentage] = useState(startPercentage);
  const [displayTotal, setDisplayTotal] = useState(isNewAward ? previousTotalXp : state.totalXp);

  useEffect(() => {
    const reduceMotion = prefersReducedXpMotion();
    let cancelled = false;
    let progressFrame = 0;
    let countFrame = 0;

    queueMicrotask(() => {
      if (cancelled) return;
      if (reduceMotion) {
        setDisplayPercentage(progress.percentage);
        setDisplayTotal(state.totalXp);
        return;
      }

      setDisplayPercentage(startPercentage);
      setDisplayTotal(isNewAward ? previousTotalXp : state.totalXp);
      progressFrame = window.requestAnimationFrame(() => setDisplayPercentage(progress.percentage));
      if (!isNewAward || previousTotalXp === state.totalXp) {
        setDisplayTotal(state.totalXp);
        return;
      }

      const animationStart = performance.now();
      const count = (timestamp: number) => {
        const elapsed = Math.min(1, (timestamp - animationStart) / XP_TOTAL_ANIMATION_MS);
        const eased = 1 - Math.pow(1 - elapsed, 3);
        setDisplayTotal(Math.round(previousTotalXp + (state.totalXp - previousTotalXp) * eased));
        if (elapsed < 1) {
          countFrame = window.requestAnimationFrame(count);
        }
      };
      countFrame = window.requestAnimationFrame(count);
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(progressFrame);
      window.cancelAnimationFrame(countFrame);
    };
  }, [isNewAward, previousTotalXp, progress.percentage, startPercentage, state.totalXp]);

  const progressMaximum = progress.nextLevel ? progress.xpForNextLevel : 100;
  const progressNow = progress.nextLevel ? progress.xpWithinLevel : 100;
  const progressLabel = progress.nextLevel
    ? `${progress.xpRemaining} XP to Level ${progress.nextLevel.level}`
    : "Max level reached";
  const dailyRewardAmount = XP_ACTIONS.daily_login.xp;

  return (
    <article
      className="status-card overview-command-card xp-progress-card"
      data-new-award={isNewAward ? "true" : undefined}
    >
      <div className="xp-progress-heading">
        <p className="status-label">XP PROGRESS</p>
        <p className="xp-progress-level">
          Level {progress.currentLevel.level} <span aria-hidden="true">—</span> {progress.currentLevel.title}
        </p>
      </div>

      <p className="xp-progress-total" aria-label={`${numberFormatter.format(state.totalXp)} experience points`}>
        <span>{numberFormatter.format(displayTotal)}</span> <span className="xp-progress-unit">XP</span>
      </p>

      <div
        className="xp-progress-track"
        role="progressbar"
        aria-label={progress.nextLevel ? `XP progress to Level ${progress.nextLevel.level}` : "Maximum XP level reached"}
        aria-valuemin={0}
        aria-valuemax={progressMaximum}
        aria-valuenow={progressNow}
        aria-valuetext={progressLabel}
      >
        <span
          className="xp-progress-fill"
          style={{ "--xp-progress-width": `${displayPercentage}%` } as CSSProperties}
        >
          <span className="xp-progress-shimmer" aria-hidden="true" />
        </span>
      </div>
      <p className="xp-progress-remaining">{progressLabel}</p>

      <div className="xp-progress-details">
        <section className="xp-progress-detail" aria-labelledby="xp-daily-label">
          <p id="xp-daily-label" className="xp-progress-section-label">DAILY LOGIN</p>
          <p
            className="xp-progress-detail-value xp-progress-daily-value"
            data-new-reward={isNewDailyAward ? "true" : undefined}
          >
            {dailyRewardStatus === "earned" ? (
              <><span className="xp-progress-award">+{dailyRewardAmount} XP</span> earned today</>
            ) : dailyRewardStatus === "unavailable" ? (
              "Daily reward could not be saved"
            ) : (
              "Checking today's reward"
            )}
          </p>
        </section>

        <section className="xp-progress-detail" aria-labelledby="xp-recent-label">
          <p id="xp-recent-label" className="xp-progress-section-label">RECENT</p>
          {state.recentAwards.length ? (
            <ul className="xp-progress-recent-list">
              {state.recentAwards.slice(0, 2).map((award) => (
                <li key={award.id}>
                  <span>{XP_ACTIONS[award.action].label}</span>
                  <span className="xp-progress-award">+{numberFormatter.format(award.amount)} XP</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="xp-progress-detail-value xp-progress-empty">No XP earned yet</p>
          )}
        </section>
      </div>
    </article>
  );
}

export function XpProgressCard() {
  const xp = useXp();
  if (!xp.isHydrated) {
    return <XpProgressCardSkeleton />;
  }
  return (
    <XpProgressCardView
      state={xp.state}
      dailyRewardStatus={xp.dailyRewardStatus}
      isNewAward={xp.isNewAward}
      isNewDailyAward={xp.isNewDailyAward}
      previousTotalXp={xp.previousTotalXp}
    />
  );
}
