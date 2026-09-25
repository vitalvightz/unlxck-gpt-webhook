import type { IntervalItem, TimerItem } from "./plan";

/**
 * Session timer state machine.
 *
 * Every phase is anchored to wall-clock timestamps rather than a decrementing
 * counter, so a locked phone, a backgrounded tab or a throttled interval never
 * makes the clock drift: the next `advance` simply replays whatever transitions
 * fell due while nothing was ticking.
 *
 * Phases:
 * - ready: an exercise is queued; the athlete taps Start.
 * - work:  a round, a timed hold, or an untimed set the athlete ends with "Set done".
 * - rest:  between rounds or sets. Untimed only when the plan gave no rest.
 *          A ranged rest (90–120 s) stays in rest until its maximum: at the
 *          minimum it only signals "ready", and the next set begins when the
 *          athlete taps Start set or the maximum runs out, never earlier.
 * - done:  every item finished.
 */
export type TimerPhase = "ready" | "work" | "rest" | "done";

export type TimerState = {
  items: TimerItem[];
  index: number;
  phase: TimerPhase;
  /** 1-based round or set currently in progress (or next up during rest). */
  unit: number;
  /** Rounds / sets completed per item. */
  completed: number[];
  phaseStartedAt: number | null;
  /** Length of a timed phase; null for an untimed one. */
  phaseMs: number | null;
  /** Ranged rest only: when the minimum rest is reached, until announced. */
  readyAt: number | null;
  pausedAt: number | null;
  startedAt: number | null;
  endedAt: number | null;
};

export type TimerEvent =
  | "round_start"
  | "round_end"
  | "rest_start"
  | "hold_start"
  | "hold_end"
  | "set_start"
  | "rest_ready"
  | "rest_end"
  | "item_complete"
  | "session_complete";

export type TimerStep = { state: TimerState; events: TimerEvent[] };

export function createTimerState(items: TimerItem[]): TimerState {
  return {
    items,
    index: 0,
    phase: items.length ? "ready" : "done",
    unit: 1,
    completed: items.map(() => 0),
    phaseStartedAt: null,
    phaseMs: null,
    readyAt: null,
    pausedAt: null,
    startedAt: null,
    endedAt: null,
  };
}

export function currentItem(state: TimerState): TimerItem | null {
  return state.items[state.index] ?? null;
}

function setPhase(
  state: TimerState,
  phase: TimerPhase,
  at: number,
  phaseMs: number | null,
  patch: Partial<TimerState> = {},
): TimerState {
  return { ...state, phase, phaseStartedAt: at, phaseMs, readyAt: null, ...patch };
}

function bumpCompleted(state: TimerState): number[] {
  return state.completed.map((count, index) => (index === state.index ? count + 1 : count));
}

function completeItem(state: TimerState, at: number, events: TimerEvent[]): TimerState {
  if (state.index + 1 < state.items.length) {
    events.push("item_complete");
    return {
      ...state,
      index: state.index + 1,
      phase: "ready",
      unit: 1,
      phaseStartedAt: null,
      phaseMs: null,
      readyAt: null,
    };
  }
  events.push("session_complete");
  return {
    ...state,
    phase: "done",
    phaseStartedAt: null,
    phaseMs: null,
    readyAt: null,
    endedAt: at,
  };
}

function beginWork(state: TimerState, at: number, events: TimerEvent[]): TimerState {
  const item = currentItem(state);
  if (!item) {
    return state;
  }
  if (item.kind === "interval") {
    events.push("round_start");
    return setPhase(state, "work", at, item.workSec * 1000);
  }
  if (item.kind === "sets" && item.holdSec) {
    events.push("hold_start");
    return setPhase(state, "work", at, item.holdSec * 1000);
  }
  events.push("set_start");
  return setPhase(state, "work", at, null);
}

/** The ready screen's Start: begins the queued exercise. */
export function startItem(state: TimerState, now: number): TimerStep {
  if (state.phase !== "ready" || state.pausedAt !== null) {
    return { state, events: [] };
  }
  const events: TimerEvent[] = [];
  const next = beginWork({ ...state, unit: 1, startedAt: state.startedAt ?? now }, now, events);
  return { state: next, events };
}

/** A finished set (tapped, or a hold that ran out) moves to rest or the next item. */
function finishSet(state: TimerState, at: number, events: TimerEvent[]): TimerState {
  const item = currentItem(state);
  if (!item || item.kind !== "sets") {
    return state;
  }
  const completed = bumpCompleted(state);
  const done = completed[state.index];
  const withCount = { ...state, completed };
  if (item.sets && done >= item.sets.max) {
    return completeItem(withCount, at, events);
  }
  events.push("rest_start");
  const rest = item.restSec;
  return setPhase(withCount, "rest", at, rest ? rest.max * 1000 : null, {
    unit: done + 1,
    readyAt: rest && rest.max > rest.min ? at + rest.min * 1000 : null,
  });
}

/** One timed phase reaching zero at `at`. */
function expirePhase(state: TimerState, at: number, events: TimerEvent[]): TimerState {
  const item = currentItem(state);
  if (!item) {
    return state;
  }
  if (item.kind === "interval") {
    if (state.phase === "work") {
      const completed = bumpCompleted(state);
      events.push("round_end");
      const withCount = { ...state, completed };
      if (completed[state.index] >= item.rounds) {
        return completeItem(withCount, at, events);
      }
      if (item.restSec > 0) {
        events.push("rest_start");
        return setPhase(withCount, "rest", at, item.restSec * 1000, { unit: state.unit + 1 });
      }
      return beginWork({ ...withCount, unit: state.unit + 1 }, at, events);
    }
    return beginWork(state, at, events);
  }
  if (item.kind === "sets") {
    if (state.phase === "work") {
      events.push("hold_end");
      return finishSet(state, at, events);
    }
    events.push("rest_end");
    return beginWork(state, at, events);
  }
  return state;
}

export function phaseEndsAt(state: TimerState): number | null {
  if (state.phaseStartedAt === null || state.phaseMs === null) {
    return null;
  }
  return state.phaseStartedAt + state.phaseMs;
}

/** Replay every transition due by `now`. A paused timer never advances. */
export function advance(state: TimerState, now: number): TimerStep {
  if (state.pausedAt !== null || state.phase === "ready" || state.phase === "done") {
    return { state, events: [] };
  }
  const events: TimerEvent[] = [];
  let next = state;
  // Bounded so a corrupt persisted state can never spin forever.
  for (let guard = 0; guard < 500; guard += 1) {
    // The minimum of a ranged rest always falls before its maximum.
    if (next.readyAt !== null && now >= next.readyAt) {
      events.push("rest_ready");
      next = { ...next, readyAt: null };
      continue;
    }
    const endsAt = phaseEndsAt(next);
    if (endsAt !== null && now >= endsAt && (next.phase === "work" || next.phase === "rest")) {
      next = expirePhase(next, endsAt, events);
      continue;
    }
    break;
  }
  return { state: next, events };
}

/** "Set done" on a rep set, or ending a hold early. */
export function completeSet(state: TimerState, now: number): TimerStep {
  const item = currentItem(state);
  if (state.phase !== "work" || state.pausedAt !== null || item?.kind !== "sets") {
    return { state, events: [] };
  }
  const events: TimerEvent[] = [];
  return { state: finishSet(state, now, events), events };
}

/** Start the next set without waiting out the rest (or from an untimed rest). */
export function skipRest(state: TimerState, now: number): TimerStep {
  if (state.phase !== "rest" || state.pausedAt !== null) {
    return { state, events: [] };
  }
  const events: TimerEvent[] = [];
  return { state: beginWork(state, now, events), events };
}

/** End the current round now; it still counts as a round done. */
export function endRound(state: TimerState, now: number): TimerStep {
  const item = currentItem(state);
  if (state.phase !== "work" || state.pausedAt !== null || item?.kind !== "interval") {
    return { state, events: [] };
  }
  const events: TimerEvent[] = [];
  return { state: expirePhase(state, now, events), events };
}

/** Finish the current exercise (task done, set range met, or moving on early). */
export function finishItem(state: TimerState, now: number): TimerStep {
  if (state.phase === "done") {
    return { state, events: [] };
  }
  const item = currentItem(state);
  const events: TimerEvent[] = [];
  let next = { ...state, pausedAt: null };
  if (item?.kind === "task" && next.completed[next.index] === 0) {
    next = { ...next, completed: bumpCompleted(next) };
  }
  return { state: completeItem(next, now, events), events };
}

/** End the whole session from anywhere. */
export function endSession(state: TimerState, now: number): TimerState {
  return {
    ...state,
    phase: "done",
    phaseStartedAt: null,
    phaseMs: null,
    readyAt: null,
    pausedAt: null,
    endedAt: now,
  };
}

/** Give an untimed rest a length (the rest presets when the plan had none). */
export function setRestLength(state: TimerState, seconds: number, now: number): TimerState {
  if (state.phase !== "rest" || seconds <= 0) {
    return state;
  }
  return { ...state, phaseStartedAt: state.pausedAt ?? now, phaseMs: seconds * 1000 };
}

export function addTime(state: TimerState, seconds: number): TimerState {
  if (state.phaseMs === null || (state.phase !== "work" && state.phase !== "rest")) {
    return state;
  }
  return { ...state, phaseMs: state.phaseMs + seconds * 1000 };
}

export function pause(state: TimerState, now: number): TimerState {
  if (state.pausedAt !== null || (state.phase !== "work" && state.phase !== "rest")) {
    return state;
  }
  return { ...state, pausedAt: now };
}

export function resume(state: TimerState, now: number): TimerState {
  if (state.pausedAt === null) {
    return state;
  }
  const pausedFor = Math.max(0, now - state.pausedAt);
  return {
    ...state,
    pausedAt: null,
    phaseStartedAt: state.phaseStartedAt === null ? null : state.phaseStartedAt + pausedFor,
    readyAt: state.readyAt === null ? null : state.readyAt + pausedFor,
  };
}

/** Adjust a queued round item before it starts (ready screen steppers). */
export function updateIntervalItem(
  state: TimerState,
  patch: Partial<Pick<IntervalItem, "rounds" | "workSec" | "restSec">>,
): TimerState {
  const item = currentItem(state);
  if (state.phase !== "ready" || item?.kind !== "interval") {
    return state;
  }
  const next: IntervalItem = {
    ...item,
    rounds: Math.min(30, Math.max(1, patch.rounds ?? item.rounds)),
    workSec: Math.min(3600, Math.max(5, patch.workSec ?? item.workSec)),
    restSec: Math.min(1800, Math.max(0, patch.restSec ?? item.restSec)),
    needsSetup: false,
  };
  return { ...state, items: state.items.map((entry, index) => (index === state.index ? next : entry)) };
}

export type TimerView = {
  /** Time left in a timed phase; null when the phase is untimed. */
  remainingMs: number | null;
  /** Time spent in the current phase. */
  elapsedMs: number;
  /** Ranged rest only: time left until the minimum rest (0 once ready). */
  readyRemainingMs: number | null;
  paused: boolean;
};

export function viewAt(state: TimerState, now: number): TimerView {
  const clock = state.pausedAt ?? now;
  const endsAt = phaseEndsAt(state);
  const item = currentItem(state);
  const rest = item?.kind === "sets" ? item.restSec : null;
  const ranged = state.phase === "rest" && rest !== null && rest.max > rest.min;
  const elapsedMs = state.phaseStartedAt === null ? 0 : Math.max(0, clock - state.phaseStartedAt);
  return {
    remainingMs: endsAt === null ? null : Math.max(0, endsAt - clock),
    elapsedMs,
    readyRemainingMs: ranged && rest ? Math.max(0, rest.min * 1000 - elapsedMs) : null,
    paused: state.pausedAt !== null,
  };
}

/**
 * The countdown the warning cues lead into: the minimum of a ranged rest
 * while it is still ahead (that is when the athlete is ready), otherwise the
 * end of the phase.
 */
export function cueRemainingMs(view: TimerView): number | null {
  return view.readyRemainingMs !== null && view.readyRemainingMs > 0
    ? view.readyRemainingMs
    : view.remainingMs;
}

export type TimerCue = "ten_seconds" | "count_3" | "count_2" | "count_1";

/**
 * Warning cues crossed between two ticks of the same phase. The ten-second
 * clapper only fires on phases long enough for it to be a warning, and the
 * 3-2-1 count only leads into work (the end of a rest).
 */
export function crossedCues(
  phase: TimerPhase,
  phaseMs: number | null,
  previousRemainingMs: number | null,
  remainingMs: number | null,
): TimerCue[] {
  if (previousRemainingMs === null || remainingMs === null || phaseMs === null) {
    return [];
  }
  const crossed = (mark: number) => previousRemainingMs > mark && remainingMs <= mark && remainingMs > 0;
  const cues: TimerCue[] = [];
  if (phase === "work" && phaseMs >= 30_000 && crossed(10_000)) {
    cues.push("ten_seconds");
  }
  if (phase === "rest") {
    if (crossed(3_000)) cues.push("count_3");
    if (crossed(2_000)) cues.push("count_2");
    if (crossed(1_000)) cues.push("count_1");
  }
  return cues;
}

/** True when every item reached its planned minimum. */
export function metPlan(state: TimerState): boolean {
  return state.items.every((item, index) => {
    const done = state.completed[index] ?? 0;
    if (item.kind === "interval") return done >= item.rounds;
    if (item.kind === "sets") return item.sets ? done >= item.sets.min : done > 0;
    return done > 0;
  });
}

/** A short plain-text record of what the timer logged, for the session notes. */
export function summarizeRun(state: TimerState): string {
  const lines = state.items.flatMap((item, index) => {
    const done = state.completed[index] ?? 0;
    if (item.kind === "interval") {
      return done > 0 ? [`${item.title}: ${done}/${item.rounds} rounds`] : [];
    }
    if (item.kind === "sets") {
      if (done === 0) return [];
      if (item.sets && item.sets.min === item.sets.max) {
        return [`${item.title}: ${done}/${item.sets.min} sets`];
      }
      const plan = item.sets ? ` (plan ${item.sets.min}–${item.sets.max})` : "";
      return [`${item.title}: ${done} ${done === 1 ? "set" : "sets"}${plan}`];
    }
    return done > 0 ? [`${item.title}: done`] : [];
  });
  return lines.length ? `Timer: ${lines.join(" · ")}` : "";
}

/**
 * The one sound for a batch of events from a single tick. A tick can carry
 * several transitions (a round ending straight into rest, or a phone waking
 * after minutes locked), and stacking their sounds would be noise: the most
 * significant one wins.
 */
export function soundForEvents(
  events: TimerEvent[],
): "finish" | "triple_bell" | "bell" | "go" | "chime" | "soft_chime" | null {
  if (events.includes("session_complete")) return "finish";
  if (events.includes("round_end")) return "triple_bell";
  if (events.includes("round_start")) return "bell";
  if (events.includes("rest_end") || events.includes("hold_start")) return "go";
  if (events.includes("hold_end") || events.includes("item_complete")) return "chime";
  if (events.includes("rest_ready")) return "soft_chime";
  return null;
}

/** Optional spoken callout for the same batch of events. */
export function calloutForEvents(events: TimerEvent[], state: TimerState): string | null {
  const item = currentItem(state);
  if (events.includes("session_complete")) return "Session complete";
  if (events.includes("round_start") && item?.kind === "interval") {
    return state.unit >= item.rounds && item.rounds > 1 ? "Last round" : `Round ${state.unit}`;
  }
  if (events.includes("rest_start")) return "Rest";
  if (events.includes("rest_ready")) return "Ready";
  if (events.includes("item_complete") && item) return `Next: ${item.title}`;
  if (events.includes("rest_end") && item?.kind === "sets") return `Set ${state.unit}`;
  return null;
}
