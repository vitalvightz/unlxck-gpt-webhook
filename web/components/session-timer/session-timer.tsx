"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useSessionTimer, type SessionTimerController } from "@/components/session-timer/use-session-timer";
import { timerAudio } from "@/lib/session-timer/audio";
import {
  addTime,
  adjustItem,
  currentItem,
  endRound,
  endSession,
  finishItem,
  metPlan,
  pause,
  resume,
  setRestLength,
  skipRest,
  startItem,
  completeSet,
  summarizeRun,
  updateIntervalItem,
  viewAt,
  type ItemAdjustment,
  type TimerState,
  type TimerView,
} from "@/lib/session-timer/engine";
import { rememberRoundFormat, ROUND_PRESETS } from "@/lib/session-timer/contact";
import type { SparringPlannedIntensity } from "@/lib/types";
import {
  formatClock,
  formatRange,
  formatShortDuration,
  type TimerItem,
} from "@/lib/session-timer/plan";

export type SessionTimerSummary = {
  /** Every item reached its planned minimum. */
  complete: boolean;
  /** Plain-text record of the run for the session notes. */
  notes: string;
  /** Sparring rounds the run completed (for the sparring log), or null. */
  sparring: {
    rounds: number;
    roundSeconds: number | null;
    /** From the first sparring block's structured intensity, when stated. */
    plannedIntensity: SparringPlannedIntensity | null;
  } | null;
};

/** Completed sparring rounds across the run's sparring items. */
export function sparringSummary(state: TimerState): SessionTimerSummary["sparring"] {
  let rounds = 0;
  let roundSeconds: number | null = null;
  let plannedIntensity: SparringPlannedIntensity | null = null;
  let hasSparring = false;
  state.items.forEach((item, index) => {
    if (item.kind === "interval" && item.sparring) {
      hasSparring = true;
      rounds += state.completed[index] ?? 0;
      roundSeconds ??= item.workSec;
      plannedIntensity ??= item.plannedIntensity ?? null;
    }
  });
  return hasSparring ? { rounds, roundSeconds, plannedIntensity } : null;
}

const REST_PRESETS = [60, 90, 120, 180];
/** The last stretch of a timed phase, when the screen turns amber. */
const WARN_MS = 10_000;

type Tone = "ready" | "work" | "rest" | "warn" | "paused" | "done" | "open";

function toneFor(state: TimerState, view: TimerView): Tone {
  if (state.phase === "done") return "done";
  if (state.phase === "ready") return "ready";
  if (view.paused) return "paused";
  if (view.remainingMs !== null && state.phaseMs !== null && state.phaseMs > WARN_MS * 2 && view.remainingMs <= WARN_MS) {
    return "warn";
  }
  if (state.phase === "rest") return "rest";
  return view.remainingMs === null ? "open" : "work";
}

function describeItem(item: TimerItem): string {
  if (item.kind === "interval") {
    const round = `${item.rounds} × ${formatClock(item.workSec)}`;
    return item.restSec > 0 ? `${round} · ${formatClock(item.restSec)} rest` : round;
  }
  if (item.kind === "sets") {
    const parts = [
      item.sets ? `${formatRange(item.sets)} sets` : "Sets as needed",
      item.holdSec ? `${formatShortDuration(item.holdSec)} hold` : null,
      item.restSec ? `${formatRange(item.restSec, formatShortDuration)} rest` : null,
    ];
    return parts.filter(Boolean).join(" · ");
  }
  return "Tap done when finished";
}

function phaseLabel(state: TimerState, item: TimerItem | null, view: TimerView): string {
  if (state.phase === "done") return metPlan(state) ? "Session complete" : "Session ended";
  if (state.phase === "ready") return "Up next";
  if (view.paused) return "Paused";
  if (state.phase === "rest") return view.readyRemainingMs === 0 ? "Ready" : "Rest";
  if (item?.kind === "interval") return item.sparring ? "Spar" : "Work";
  if (item?.kind === "sets") return item.holdSec ? "Hold" : "Lift";
  return "Go";
}

function counterLabel(state: TimerState, item: TimerItem | null): string | null {
  if (!item || state.phase === "ready" || state.phase === "done") return null;
  if (item.kind === "interval") {
    if (item.rounds <= 1) return null;
    const label = state.phase === "rest" ? "Next: round" : "Round";
    return `${label} ${state.unit} / ${item.rounds}`;
  }
  if (item.kind === "sets") {
    const target = item.sets
      ? item.sets.min === item.sets.max
        ? ` of ${item.sets.min}`
        : ` · target ${formatRange(item.sets)}`
      : "";
    return state.phase === "rest" ? `Next: set ${state.unit}${target}` : `Set ${state.unit}${target}`;
  }
  return null;
}

function doneLabel(item: TimerItem, done: number): string {
  if (done === 0) return "Skipped";
  if (item.kind === "interval") return `${done}/${item.rounds} rounds`;
  if (item.kind === "sets") {
    if (item.sets && item.sets.min === item.sets.max) return `${done}/${item.sets.min} sets`;
    const count = `${done} ${done === 1 ? "set" : "sets"}`;
    return item.sets ? `${count} · plan ${formatRange(item.sets)}` : count;
  }
  return "Done";
}

function Progress({ state, item }: { state: TimerState; item: TimerItem | null }) {
  if (!item || item.kind === "task") return null;
  const total = item.kind === "interval" ? item.rounds : item.sets?.max ?? null;
  if (!total || total > 20) return null;
  const done = state.completed[state.index] ?? 0;
  const min = item.kind === "sets" && item.sets ? item.sets.min : total;
  return (
    <ol className="st-segments" aria-hidden="true">
      {Array.from({ length: total }, (_, index) => (
        <li
          key={index}
          data-state={index < done ? "done" : index === done && state.phase !== "ready" ? "current" : "todo"}
          data-optional={index >= min ? "true" : undefined}
        />
      ))}
    </ol>
  );
}

/** How far through the current countdown the ring is (0..1), or null when untimed. */
function ringProgress(state: TimerState, item: TimerItem | null, view: TimerView): number | null {
  if (view.remainingMs === null || state.phaseMs === null || state.phaseMs <= 0) return null;
  const rest = item?.kind === "sets" ? item.restSec : null;
  if (view.readyRemainingMs !== null && rest && rest.max > rest.min) {
    // A ranged rest fills once to its minimum, then again across the optional window.
    const minMs = rest.min * 1000;
    return view.readyRemainingMs > 0
      ? 1 - view.readyRemainingMs / minMs
      : 1 - (view.remainingMs ?? 0) / (rest.max * 1000 - minMs);
  }
  return 1 - view.remainingMs / state.phaseMs;
}

function Ring({ progress, children }: { progress: number | null; children: ReactNode }) {
  const clamped = progress === null ? 1 : Math.min(1, Math.max(0, progress));
  return (
    <div className="st-ring" data-timed={progress === null ? "false" : "true"}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle className="st-ring-track" cx="60" cy="60" r="55" />
        <circle
          className="st-ring-fill"
          cx="60"
          cy="60"
          r="55"
          pathLength={100}
          strokeDasharray="100"
          strokeDashoffset={100 - clamped * 100}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="st-ring-inner">{children}</div>
    </div>
  );
}

type IconName = "pause" | "play" | "plus" | "skip" | "next" | "flag" | "chevron" | "sound" | "check" | "sliders";

const ICON_PATHS: Record<IconName, ReactNode> = {
  pause: <path d="M8 5v14M16 5v14" />,
  play: <path d="M7 5l12 7-12 7z" fill="currentColor" stroke="none" />,
  plus: <path d="M12 6v12M6 12h12" />,
  skip: <path d="M6 5l9 7-9 7zM18 5v14" />,
  next: <path d="M9 6l6 6-6 6" />,
  flag: <path d="M6 20V5M6 5h11l-2 4 2 4H6" />,
  chevron: <path d="M6 9l6 6 6-6" />,
  sound: <path d="M4 10v4h4l5 4V6L8 10H4zM16 9a4 4 0 010 6M18.5 6.5a7.5 7.5 0 010 11" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  sliders: <path d="M4 8h9M17 8h3M4 16h3M11 16h9M15 6v4M9 14v4" />,
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg className="st-glyph" viewBox="0 0 24 24" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        {ICON_PATHS[name]}
      </g>
    </svg>
  );
}

/** Exercise progress across the session, under the header. */
function StepBar({ state }: { state: TimerState }) {
  if (state.items.length < 2) return null;
  return (
    <ol className="st-steps" aria-hidden="true">
      {state.items.map((entry, index) => (
        <li
          key={entry.id}
          data-state={
            state.phase === "done" || index < state.index ? "done" : index === state.index ? "current" : "todo"
          }
        />
      ))}
    </ol>
  );
}

function Stepper({
  label,
  value,
  onDown,
  onUp,
}: {
  label: string;
  value: string;
  onDown: () => void;
  onUp: () => void;
}) {
  return (
    <div className="st-stepper">
      <span className="st-stepper-label">{label}</span>
      <div className="st-stepper-control">
        <button type="button" onClick={onDown} aria-label={`Decrease ${label.toLowerCase()}`}>
          −
        </button>
        <span className="st-stepper-value">{value}</span>
        <button type="button" onClick={onUp} aria-label={`Increase ${label.toLowerCase()}`}>
          +
        </button>
      </div>
    </div>
  );
}

function ReadyPanel({
  timer,
  item,
  onAdjust,
}: {
  timer: SessionTimerController;
  item: TimerItem;
  onAdjust: () => void;
}) {
  if (item.kind !== "interval") {
    return <p className="st-plan-line">{describeItem(item)}</p>;
  }
  // One line, not a wall of controls: the plan's format, plus quick presets
  // when the plan left it open. Everything else lives behind Adjust.
  return (
    <div className="st-setup">
      <button type="button" className="st-plan-summary" onClick={onAdjust} aria-label="Edit rounds and timing">
        <span>{item.rounds}</span> × <span>{formatClock(item.workSec)}</span>
        {item.restSec > 0 ? (
          <>
            {" "}
            · <span>{formatClock(item.restSec)}</span> rest
          </>
        ) : null}
      </button>
      {item.needsSetup ? (
        <p className="st-setup-note">
          {item.setupNote || "Round length isn't set in your plan. Pick a format."}
        </p>
      ) : null}
      {item.presets ? (
        <div className="st-round-presets" role="group" aria-label="Round format">
          {ROUND_PRESETS.map((preset) => {
            const active = preset.workSec === item.workSec && preset.restSec === item.restSec;
            return (
              <button
                key={preset.label}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  rememberRoundFormat(item.formatMemoryKey, {
                    workSec: preset.workSec,
                    restSec: preset.restSec,
                  });
                  timer.update((s) =>
                    updateIntervalItem(s, { workSec: preset.workSec, restSec: preset.restSec }),
                  );
                }}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/** The current exercise's numbers, adjustable at any point (behind the header icon). */
function AdjustSheet({ timer }: { timer: SessionTimerController }) {
  const item = currentItem(timer.state);
  if (!item || item.kind === "task") return null;
  // run(), not update(): lowering a target to what is done completes the
  // exercise, and that transition plays its sound like any other.
  const adjust = (patch: ItemAdjustment) => timer.run((s, at) => adjustItem(s, patch, at));
  return (
    <div className="st-sheet st-adjust" role="group" aria-label="Adjust timer">
      <div className="st-steppers">
        {item.kind === "interval" ? (
          <>
            <Stepper
              label="Rounds"
              value={String(item.rounds)}
              onDown={() => adjust({ rounds: item.rounds - 1 })}
              onUp={() => adjust({ rounds: item.rounds + 1 })}
            />
            <Stepper
              label="Round length"
              value={formatClock(item.workSec)}
              onDown={() => adjust({ workSec: item.workSec - 15 })}
              onUp={() => adjust({ workSec: item.workSec + 15 })}
            />
            <Stepper
              label="Rest"
              value={formatClock(item.restSec)}
              onDown={() => adjust({ restSec: item.restSec - 15 })}
              onUp={() => adjust({ restSec: item.restSec + 15 })}
            />
          </>
        ) : (
          <>
            <Stepper
              label="Sets"
              value={item.sets ? formatRange(item.sets) : "–"}
              onDown={() => adjust({ sets: (item.sets?.min ?? 2) - 1 })}
              onUp={() => adjust({ sets: (item.sets?.max ?? 0) + 1 })}
            />
            <Stepper
              label="Rest"
              value={item.restSec ? formatRange(item.restSec, formatClock) : "–"}
              onDown={() => adjust({ restSec: (item.restSec?.min ?? 90) - 15 })}
              onUp={() => adjust({ restSec: (item.restSec?.max ?? 75) + 15 })}
            />
          </>
        )}
      </div>
    </div>
  );
}

const ADJUST_HINT_KEY = "st-adjust-hint-seen";

/** Whether the one-time "you can edit these" hint should show. Hidden on the
 * server (and when storage is blocked), so it never flashes for returning users. */
function useAdjustHint(): [boolean, () => void] {
  const [dismissed, setDismissed] = useState(false);
  const unseen = useSyncExternalStore(
    () => () => undefined,
    () => {
      try {
        return window.localStorage.getItem(ADJUST_HINT_KEY) === null;
      } catch {
        return false;
      }
    },
    () => false,
  );
  const dismiss = () => {
    setDismissed(true);
    try {
      window.localStorage.setItem(ADJUST_HINT_KEY, "1");
    } catch {
      // Nothing to remember it in.
    }
  };
  return [unseen && !dismissed, dismiss];
}

function SettingsSheet({ timer, onClose }: { timer: SessionTimerController; onClose: () => void }) {
  const { settings, setSettings } = timer;
  return (
    <div className="st-sheet" role="group" aria-label="Timer sound settings">
      <label className="st-toggle">
        <input
          type="checkbox"
          checked={settings.sound}
          onChange={(event) => setSettings({ ...settings, sound: event.target.checked })}
        />
        <span>Bell and beeps</span>
      </label>
      <label className="st-range">
        <span>Volume</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={settings.volume}
          onChange={(event) => setSettings({ ...settings, volume: Number(event.target.value) })}
          onPointerUp={() => timerAudio().play("bell")}
        />
      </label>
      <label className="st-toggle">
        <input
          type="checkbox"
          checked={settings.voice}
          onChange={(event) => setSettings({ ...settings, voice: event.target.checked })}
        />
        <span>Voice callouts (&ldquo;Round 3&rdquo;, &ldquo;Rest&rdquo;)</span>
      </label>
      <label className="st-toggle">
        <input
          type="checkbox"
          checked={settings.vibrate}
          onChange={(event) => setSettings({ ...settings, vibrate: event.target.checked })}
        />
        <span>Vibrate (Android)</span>
      </label>
      <p className="st-sheet-note">
        Keep this screen open: the clock stays exact if your phone locks, but the bell can&apos;t ring
        while the screen is off.
      </p>
      <button type="button" className="st-link" onClick={onClose}>
        Close settings
      </button>
    </div>
  );
}

function PrimaryAction({
  timer,
  item,
  canFinishItem,
  readyRemainingMs,
}: {
  timer: SessionTimerController;
  item: TimerItem | null;
  canFinishItem: boolean;
  /** Ranged rest only: time until the minimum rest, when the next set unlocks. */
  readyRemainingMs: number | null;
}) {
  const { state } = timer;
  if (!item || state.phase === "done") return null;
  const unlockThen = (fn: () => void) => () => {
    timerAudio().unlock();
    fn();
  };
  if (state.phase === "ready") {
    return (
      <button type="button" className="st-primary" onClick={unlockThen(() => timer.run(startItem))}>
        {item.kind === "interval" && item.rounds > 1 ? "Start round 1" : "Start"}
      </button>
    );
  }
  if (state.pausedAt !== null) {
    return (
      <button type="button" className="st-primary" onClick={unlockThen(() => timer.update(resume))}>
        Resume
      </button>
    );
  }
  if (state.phase === "work" && item.kind === "sets") {
    return (
      <button type="button" className="st-primary" onClick={() => timer.run(completeSet)}>
        {item.holdSec ? "End hold" : `Set ${state.unit} done`}
      </button>
    );
  }
  if (state.phase === "work" && item.kind === "task") {
    return (
      <button type="button" className="st-primary" onClick={() => timer.run(finishItem)}>
        Complete
      </button>
    );
  }
  if (state.phase === "rest" && readyRemainingMs !== null && readyRemainingMs > 0) {
    return (
      <button type="button" className="st-primary" data-variant="ghost" disabled>
        Set {state.unit} unlocks in {formatClock(Math.ceil(readyRemainingMs / 1000))}
      </button>
    );
  }
  if (state.phase === "rest") {
    return (
      <button type="button" className="st-primary" data-variant="ghost" onClick={() => timer.run(skipRest)}>
        {item.kind === "sets" ? `Start set ${state.unit}` : "Skip rest"}
      </button>
    );
  }
  return (
    <button type="button" className="st-primary" data-variant="ghost" onClick={() => timer.update(pause)}>
      Pause
    </button>
  );
}

/** Portal to <body> so a transformed ancestor card can never trap the
 * fixed-position overlay; server rendering (tests) renders in place. */
function ToBody({ children }: { children: ReactNode }) {
  return typeof document === "undefined" ? <>{children}</> : createPortal(children, document.body);
}

/**
 * Full-screen session timer. Rounds for sparring / conditioning, sets with
 * auto rest for strength, holds and rest for rehab. Minimising keeps the clock
 * running (silently) and shows a mini bar; closing only ever minimises, so an
 * accidental tap never loses a session.
 */
export function SessionTimer({
  items,
  storageKey,
  sessionTitle,
  visible,
  finishLabel = "Log session",
  onMinimize,
  onExpand,
  onFinish,
  onClose,
}: {
  items: TimerItem[];
  storageKey: string;
  sessionTitle: string;
  visible: boolean;
  /** The done screen's button: logging a planned session, or just closing. */
  finishLabel?: string;
  onMinimize: () => void;
  onExpand: () => void;
  onFinish: (summary: SessionTimerSummary) => void;
  /** Closes a timer that was never started, without logging anything. */
  onClose: () => void;
}) {
  const timer = useSessionTimer({ items, storageKey, audible: visible });
  const { state, now } = timer;
  const [sheet, setSheet] = useState<"sound" | "adjust" | null>(null);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [adjustHint, dismissAdjustHint] = useAdjustHint();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const item = currentItem(state);
  const view = viewAt(state, now);
  const tone = toneFor(state, view);
  const nextItem = state.items[state.index + 1] ?? null;
  const done = state.completed[state.index] ?? 0;
  const canFinishItem =
    item?.kind === "sets" ? (item.sets ? done >= item.sets.min : done > 0) : false;
  const timed = view.remainingMs !== null;
  // A ranged rest counts down to its minimum first, then to its maximum.
  const countdownMs =
    view.readyRemainingMs !== null && view.readyRemainingMs > 0 ? view.readyRemainingMs : view.remainingMs;
  const clockSeconds = timed ? Math.ceil((countdownMs ?? 0) / 1000) : Math.floor(view.elapsedMs / 1000);

  useEffect(() => {
    if (!visible) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onMinimize();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [visible, onMinimize]);

  const finish = () =>
    onFinish({ complete: metPlan(state), notes: summarizeRun(state), sparring: sparringSummary(state) });

  if (!visible) {
    if (state.phase === "done") return null;
    return (
      <ToBody>
        <button type="button" className="st-mini" data-tone={tone} onClick={onExpand}>
          <span className="st-mini-phase">{phaseLabel(state, item, view)}</span>
          <span className="st-mini-title">{item?.title}</span>
          <span className="st-mini-clock">{state.phase === "ready" ? "Open" : formatClock(clockSeconds)}</span>
        </button>
      </ToBody>
    );
  }

  const canAdjust = state.phase !== "done" && !!item && item.kind !== "task";
  const toggleAdjust = () => {
    dismissAdjustHint();
    setSheet((open) => (open === "adjust" ? null : "adjust"));
  };
  // Never started: ending just closes, there is nothing to log or call complete.
  const started = state.startedAt !== null;

  const togglePause = () => {
    if (state.phase !== "work" && state.phase !== "rest") return;
    timerAudio().unlock();
    timer.update(state.pausedAt === null ? pause : resume);
  };

  const phaseText = phaseLabel(state, item, view);
  const counter = counterLabel(state, item);
  const sessionElapsed =
    state.startedAt !== null ? formatClock(Math.floor(((state.endedAt ?? now) - state.startedAt) / 1000)) : null;
  const restNote =
    view.readyRemainingMs !== null && item?.kind === "sets" && item.restSec
      ? view.readyRemainingMs > 0
        ? `Minimum rest. Up to ${formatShortDuration(item.restSec.max - item.restSec.min)} more is allowed after this.`
        : `Go when ready. Set ${state.unit} starts itself in ${formatClock(Math.ceil((view.remainingMs ?? 0) / 1000))}.`
      : canFinishItem && item?.kind === "sets" && item.sets && item.sets.min !== item.sets.max && state.phase === "rest"
        ? "Minimum hit. Only add sets if you're moving well."
        : null;

  return (
    <ToBody>
    <div
      ref={dialogRef}
      className="st-root"
      data-tone={tone}
      role="dialog"
      aria-modal="true"
      aria-label={`${sessionTitle} timer`}
      tabIndex={-1}
    >
      <div className="st-glow" aria-hidden="true" />
      <header className="st-top">
        <button type="button" className="st-icon" onClick={onMinimize} aria-label="Minimise timer">
          <Icon name="chevron" />
        </button>
        <div className="st-heading">
          <p className="st-session">{sessionTitle}</p>
          <p className="st-meta">
            {state.items.length > 1 && state.phase !== "done"
              ? `Exercise ${state.index + 1} of ${state.items.length}`
              : null}
            {state.items.length > 1 && state.phase !== "done" && sessionElapsed ? " · " : null}
            {sessionElapsed ? <span className="st-meta-clock">{sessionElapsed}</span> : null}
          </p>
        </div>
        <div className="st-top-actions">
          {canAdjust ? (
            <button
              type="button"
              className="st-icon"
              onClick={toggleAdjust}
              aria-label="Adjust timer"
              aria-expanded={sheet === "adjust"}
              data-active={sheet === "adjust" ? "true" : undefined}
            >
              <Icon name="sliders" />
            </button>
          ) : null}
          <button
            type="button"
            className="st-icon"
            onClick={() => setSheet((open) => (open === "sound" ? null : "sound"))}
            aria-label="Sound settings"
            aria-expanded={sheet === "sound"}
            data-active={sheet === "sound" ? "true" : undefined}
          >
            <Icon name="sound" />
          </button>
        </div>
        {canAdjust && adjustHint && sheet === null ? (
          <button type="button" className="st-hint" onClick={dismissAdjustHint}>
            Tap to edit rounds &amp; timing
            <span aria-hidden="true">×</span>
          </button>
        ) : null}
      </header>
      <StepBar state={state} />

      {sheet === "sound" ? <SettingsSheet timer={timer} onClose={() => setSheet(null)} /> : null}
      {sheet === "adjust" ? <AdjustSheet timer={timer} /> : null}
      {/* Tapping anywhere off an open sheet closes it. */}
      {sheet !== null ? <div className="st-scrim" aria-hidden="true" onClick={() => setSheet(null)} /> : null}

      {state.phase === "done" ? (
        <main className="st-main st-done">
          <div className="st-done-badge" aria-hidden="true">
            <Icon name="check" />
          </div>
          <p className="st-done-title">{metPlan(state) ? "Session complete" : "Session ended"}</p>
          {sessionElapsed ? <p className="st-done-time">{sessionElapsed} total</p> : null}
          <ul className="st-summary">
            {state.items.map((entry, index) => (
              <li key={entry.id} data-skipped={(state.completed[index] ?? 0) === 0 ? "true" : undefined}>
                <span>{entry.title}</span>
                <span>{doneLabel(entry, state.completed[index] ?? 0)}</span>
              </li>
            ))}
          </ul>
          <div className="st-actions">
            <button type="button" className="st-primary" onClick={finish}>
              {finishLabel}
            </button>
          </div>
        </main>
      ) : (
        <main className="st-main" data-phase={state.phase}>
          <p className="st-phase" aria-live="polite">
            <span className="st-phase-dot" aria-hidden="true" />
            {phaseText}
          </p>
          <h2 className="st-title">{item?.title}</h2>
          {item?.detail ? <p className="st-detail">{item.detail}</p> : null}

          {state.phase === "ready" && item ? (
            <ReadyPanel
              timer={timer}
              item={item}
              onAdjust={() => {
                dismissAdjustHint();
                setSheet("adjust");
              }}
            />
          ) : (
            <>
              <button
                type="button"
                className="st-clock"
                onClick={togglePause}
                aria-label={view.paused ? "Resume timer" : "Pause timer"}
              >
                <Ring progress={ringProgress(state, item, view)}>
                  <span className="st-clock-digits" role="timer">
                    {formatClock(clockSeconds)}
                  </span>
                  <span className="st-clock-caption">
                    {view.paused ? "Tap to resume" : counter ?? (timed ? "remaining" : "elapsed")}
                  </span>
                </Ring>
              </button>
              {restNote ? <p className="st-note">{restNote}</p> : null}
              {state.phase === "rest" && state.phaseMs === null && !view.paused ? (
                <div className="st-presets" role="group" aria-label="Rest length">
                  <span>No rest in your plan. Pick one:</span>
                  {REST_PRESETS.map((seconds) => (
                    <button
                      key={seconds}
                      type="button"
                      onClick={() => timer.update((s, at) => setRestLength(s, seconds, at))}
                    >
                      {formatShortDuration(seconds)}
                    </button>
                  ))}
                </div>
              ) : null}
            </>
          )}
          <Progress state={state} item={item} />
        </main>
      )}

      {state.phase !== "done" ? (
        <footer className="st-controls">
          <PrimaryAction
            timer={timer}
            item={item}
            canFinishItem={canFinishItem}
            readyRemainingMs={view.readyRemainingMs}
          />
          <div className="st-secondary">
            {/* Pause is the primary action during a round, and Resume is primary
                whenever paused, so it only repeats here for sets and rest. */}
            {(state.phase === "rest" || (state.phase === "work" && item?.kind !== "interval")) &&
            !view.paused ? (
              <button type="button" onClick={togglePause}>
                <Icon name="pause" />
                Pause
              </button>
            ) : null}
            {timed && !view.paused ? (
              <button type="button" onClick={() => timer.update((s) => addTime(s, 30))}>
                <Icon name="plus" />
                30s
              </button>
            ) : null}
            {state.phase === "work" && item?.kind === "interval" && !view.paused ? (
              <button type="button" onClick={() => timer.run(endRound)}>
                <Icon name="skip" />
                End round
              </button>
            ) : null}
            {/* Only ever moves to the next exercise. Nothing here can end the
                session: that is End session, which asks first. Highlighted once
                a set range's minimum is met, as the natural way on. */}
            {state.index + 1 < state.items.length ? (
              <button
                type="button"
                data-emphasis={canFinishItem ? "true" : undefined}
                onClick={() => timer.run(finishItem)}
              >
                <Icon name="next" />
                Next exercise
              </button>
            ) : null}
          </div>
          {nextItem ? (
            <div className="st-next">
              <span className="st-next-label">Up next</span>
              <span className="st-next-title">{nextItem.title}</span>
              <span className="st-next-plan">{describeItem(nextItem)}</span>
            </div>
          ) : null}
          {confirmEnd ? (
            <div className="st-confirm" role="alertdialog" aria-label="End session">
              <span>End the session now?</span>
              <button
                type="button"
                data-danger="true"
                onClick={() => {
                  setConfirmEnd(false);
                  timer.update(endSession);
                }}
              >
                End
              </button>
              <button type="button" onClick={() => setConfirmEnd(false)}>
                Keep going
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="st-link"
              onClick={() => (started ? setConfirmEnd(true) : onClose())}
            >
              {started ? "End session" : "Close timer"}
            </button>
          )}
        </footer>
      ) : null}
    </div>
    </ToBody>
  );
}
