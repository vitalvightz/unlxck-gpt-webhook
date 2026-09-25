"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { useSessionTimer, type SessionTimerController } from "@/components/session-timer/use-session-timer";
import { timerAudio } from "@/lib/session-timer/audio";
import {
  addTime,
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
  type TimerState,
  type TimerView,
} from "@/lib/session-timer/engine";
import { ROUND_PRESETS } from "@/lib/session-timer/contact";
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
};

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
  if (state.phase === "done") return "Session complete";
  if (state.phase === "ready") return "Up next";
  if (view.paused) return "Paused";
  if (state.phase === "rest") return "Rest";
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
    <ol className="st-dots" aria-hidden="true">
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
      <div className="st-stepper-row">
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

function ReadyPanel({ timer, item }: { timer: SessionTimerController; item: TimerItem }) {
  if (item.kind !== "interval") {
    return <p className="st-plan-line">{describeItem(item)}</p>;
  }
  return (
    <div className="st-setup">
      {item.needsSetup ? (
        <p className="st-setup-note">
          Round length isn&apos;t in your plan. Match what your coach is running.
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
                onClick={() =>
                  timer.update((s) =>
                    updateIntervalItem(s, { workSec: preset.workSec, restSec: preset.restSec }),
                  )
                }
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      ) : null}
      <div className="st-steppers">
        <Stepper
          label="Rounds"
          value={String(item.rounds)}
          onDown={() => timer.update((s) => updateIntervalItem(s, { rounds: item.rounds - 1 }))}
          onUp={() => timer.update((s) => updateIntervalItem(s, { rounds: item.rounds + 1 }))}
        />
        <Stepper
          label="Round length"
          value={formatClock(item.workSec)}
          onDown={() => timer.update((s) => updateIntervalItem(s, { workSec: item.workSec - 15 }))}
          onUp={() => timer.update((s) => updateIntervalItem(s, { workSec: item.workSec + 15 }))}
        />
        <Stepper
          label="Rest"
          value={formatClock(item.restSec)}
          onDown={() => timer.update((s) => updateIntervalItem(s, { restSec: item.restSec - 15 }))}
          onUp={() => timer.update((s) => updateIntervalItem(s, { restSec: item.restSec + 15 }))}
        />
      </div>
    </div>
  );
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
}: {
  timer: SessionTimerController;
  item: TimerItem | null;
  canFinishItem: boolean;
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
        Done
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
}) {
  const timer = useSessionTimer({ items, storageKey, audible: visible });
  const { state, now } = timer;
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const item = currentItem(state);
  const view = viewAt(state, now);
  const tone = toneFor(state, view);
  const nextItem = state.items[state.index + 1] ?? null;
  const done = state.completed[state.index] ?? 0;
  const canFinishItem =
    item?.kind === "sets" ? (item.sets ? done >= item.sets.min : done > 0) : false;
  const timed = view.remainingMs !== null;
  const clockSeconds = timed ? Math.ceil((view.remainingMs ?? 0) / 1000) : Math.floor(view.elapsedMs / 1000);

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
    onFinish({ complete: metPlan(state), notes: summarizeRun(state) });

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

  const togglePause = () => {
    if (state.phase !== "work" && state.phase !== "rest") return;
    timerAudio().unlock();
    timer.update(state.pausedAt === null ? pause : resume);
  };

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
      <header className="st-top">
        <button type="button" className="st-icon" onClick={onMinimize} aria-label="Minimise timer">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
        </button>
        <p className="st-session">
          {sessionTitle}
          {state.items.length > 1 && state.phase !== "done" ? (
            <span>
              {" "}
              · {state.index + 1}/{state.items.length}
            </span>
          ) : null}
        </p>
        <button
          type="button"
          className="st-icon"
          onClick={() => setSettingsOpen((open) => !open)}
          aria-label="Sound settings"
          aria-expanded={settingsOpen}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M4 10v4h4l5 4V6L8 10H4zm12.5 2a4.5 4.5 0 00-2.5-4v8a4.5 4.5 0 002.5-4z"
              fill="currentColor"
            />
          </svg>
        </button>
      </header>

      {settingsOpen ? <SettingsSheet timer={timer} onClose={() => setSettingsOpen(false)} /> : null}

      {state.phase === "done" ? (
        <main className="st-main st-done">
          <p className="st-phase">Session complete</p>
          <ul className="st-summary">
            {state.items.map((entry, index) => (
              <li key={entry.id}>
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
        <main className="st-main">
          <p className="st-phase" aria-live="polite">
            {phaseLabel(state, item, view)}
          </p>
          <h2 className="st-title">{item?.title}</h2>
          {item?.detail ? <p className="st-detail">{item.detail}</p> : null}

          {state.phase === "ready" && item ? (
            <ReadyPanel timer={timer} item={item} />
          ) : (
            <>
              <button
                type="button"
                className="st-clock"
                onClick={togglePause}
                aria-label={view.paused ? "Resume timer" : "Pause timer"}
                data-counting={timed ? "down" : "up"}
              >
                <span className="st-clock-digits" role="timer">
                  {formatClock(clockSeconds)}
                </span>
                {!timed ? <span className="st-clock-caption">elapsed</span> : null}
              </button>
              {counterLabel(state, item) ? <p className="st-counter">{counterLabel(state, item)}</p> : null}
              {view.windowRemainingMs !== null && state.phase === "work" ? (
                <p className="st-window">
                  Ready. Go now, or take up to {formatClock(Math.ceil(view.windowRemainingMs / 1000))} more rest.
                </p>
              ) : null}
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
              {canFinishItem && item?.kind === "sets" && item.sets && item.sets.min !== item.sets.max ? (
                <p className="st-window">
                  Minimum hit. Only add sets if you&apos;re moving well.
                </p>
              ) : null}
            </>
          )}
          <Progress state={state} item={item} />
        </main>
      )}

      {state.phase !== "done" ? (
        <footer className="st-controls">
          <PrimaryAction timer={timer} item={item} canFinishItem={canFinishItem} />
          <div className="st-secondary">
            {/* Pause is the primary action during a round, and Resume is primary
                whenever paused, so it only repeats here for sets and rest. */}
            {(state.phase === "rest" || (state.phase === "work" && item?.kind !== "interval")) &&
            !view.paused ? (
              <button type="button" onClick={togglePause}>
                Pause
              </button>
            ) : null}
            {timed && !view.paused ? (
              <button type="button" onClick={() => timer.update((s) => addTime(s, 30))}>
                +30s
              </button>
            ) : null}
            {state.phase === "work" && item?.kind === "interval" && !view.paused ? (
              <button type="button" onClick={() => timer.run(endRound)}>
                End round
              </button>
            ) : null}
            {canFinishItem ? (
              <button type="button" data-emphasis="true" onClick={() => timer.run(finishItem)}>
                Finish exercise
              </button>
            ) : state.phase !== "ready" || state.index + 1 < state.items.length ? (
              <button type="button" onClick={() => timer.run(finishItem)}>
                {state.index + 1 < state.items.length ? "Next exercise" : "Finish"}
              </button>
            ) : null}
          </div>
          {nextItem ? (
            <p className="st-next">
              <span>Next</span> {nextItem.title} · {describeItem(nextItem)}
            </p>
          ) : null}
          {confirmEnd ? (
            <div className="st-confirm" role="alertdialog" aria-label="End session">
              <span>End the session now?</span>
              <button
                type="button"
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
            <button type="button" className="st-link" onClick={() => setConfirmEnd(true)}>
              End session
            </button>
          )}
        </footer>
      ) : null}
    </div>
    </ToBody>
  );
}
