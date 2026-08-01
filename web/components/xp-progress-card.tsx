"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { Skeleton } from "@/components/skeleton";
import { useXp, type XpDailyRewardStatus } from "@/components/xp-provider";
import { XP_ACTIONS, resolveXpLevel, type XpState } from "@/lib/xp";

const XP_TOTAL_ANIMATION_MS = 640;
const numberFormatter = new Intl.NumberFormat("en-GB");

type XpLedgerRow = {
  key: "today" | "recent" | "next";
  label: string;
  value: string;
  /** Gold — reserved for XP actually earned. */
  isAward?: boolean;
  /** An em dash standing in for a value that does not exist in this state. */
  isPlaceholder?: boolean;
};

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

/* Mirrors the ledger structure exactly so hydration swaps content into a row
   that is already the right height. */
export function XpProgressCardSkeleton() {
  return (
    <article className="status-card overview-command-card xp-progress-card xp-progress-card-skeleton" aria-busy="true">
      <div className="xp-progress-heading">
        <Skeleton variant="text" width={92} height={12} />
        <Skeleton variant="block" width={74} height={20} style={{ borderRadius: 999 }} />
      </div>
      <div className="xp-progress-figure">
        <Skeleton variant="text" width="36%" height={44} />
        <Skeleton variant="text" width="32%" height={26} />
      </div>
      <div className="xp-progress-skeleton-track">
        <Skeleton variant="block" width="100%" height={8} style={{ borderRadius: 999 }} />
      </div>
      <div className="xp-progress-ledger xp-progress-skeleton-ledger">
        <Skeleton variant="text" width="100%" height={15} />
        <Skeleton variant="text" width="100%" height={15} />
        <Skeleton variant="text" width="100%" height={15} />
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

  /* Three rows, always. A fixed row count keeps the card's height stable as
     awards come and go, and the ledger reads as a ruled column rather than a
     list that grows. Today's claimed daily login is dropped from the recent
     row so the same award is never printed twice. */
  const ledgerRows = useMemo<XpLedgerRow[]>(() => {
    const todayRow: XpLedgerRow =
      dailyRewardStatus === "earned"
        ? { key: "today", label: "Today's reward", value: `+${dailyRewardAmount} XP`, isAward: true }
        : dailyRewardStatus === "unavailable"
          ? { key: "today", label: "Daily reward could not be saved", value: "—", isPlaceholder: true }
          : { key: "today", label: "Checking today's reward", value: "—", isPlaceholder: true };

    const remainingAwards = [...state.recentAwards];
    if (dailyRewardStatus === "earned") {
      const claimedToday = remainingAwards.findIndex((award) => award.action === "daily_login");
      if (claimedToday !== -1) {
        remainingAwards.splice(claimedToday, 1);
      }
    }
    const [latest] = remainingAwards;
    const recentRow: XpLedgerRow = latest
      ? {
          key: "recent",
          label: XP_ACTIONS[latest.action].label,
          value: `+${numberFormatter.format(latest.amount)} XP`,
          isAward: true,
        }
      : { key: "recent", label: "No other XP yet", value: "—", isPlaceholder: true };

    const nextRow: XpLedgerRow = progress.nextLevel
      ? {
          key: "next",
          label: `To Level ${progress.nextLevel.level}`,
          value: `${numberFormatter.format(progress.xpRemaining)} XP`,
        }
      : { key: "next", label: "Max level reached", value: "—", isPlaceholder: true };

    return [todayRow, recentRow, nextRow];
  }, [dailyRewardAmount, dailyRewardStatus, progress.nextLevel, progress.xpRemaining, state.recentAwards]);

  return (
    <article
      className="status-card overview-command-card xp-progress-card"
      data-new-award={isNewAward ? "true" : undefined}
    >
      <div className="xp-progress-heading">
        <p className="status-label">XP PROGRESS</p>
        <p className="xp-progress-rank">{progress.currentLevel.title}</p>
      </div>

      <div className="xp-progress-figure">
        <p className="xp-progress-total" aria-label={`${numberFormatter.format(state.totalXp)} experience points`}>
          <span className="xp-progress-number">{numberFormatter.format(displayTotal)}</span>
          <span className="xp-progress-unit">XP</span>
        </p>
        <dl className="xp-progress-stats">
          <div>
            <dt>Level</dt>
            <dd>{String(progress.currentLevel.level).padStart(2, "0")}</dd>
          </div>
          <div>
            <dt>Next</dt>
            <dd>
              {progress.nextLevel ? numberFormatter.format(progress.nextLevel.threshold) : "—"}
            </dd>
          </div>
        </dl>
      </div>

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
      <ul className="xp-progress-ledger">
        {ledgerRows.map((row) => (
          <li
            key={row.key}
            className="xp-progress-ledger-row"
            data-new-reward={row.key === "today" && isNewDailyAward ? "true" : undefined}
          >
            <span className="xp-progress-ledger-label">{row.label}</span>
            <span className="xp-progress-leader" aria-hidden="true" />
            <span
              className={`xp-progress-ledger-value${row.isAward ? " xp-progress-award" : ""}`}
              aria-hidden={row.isPlaceholder ? "true" : undefined}
            >
              {row.value}
            </span>
          </li>
        ))}
      </ul>
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
