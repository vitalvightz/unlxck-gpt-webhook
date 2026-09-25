import { getSourcePrescriptionRangeOverrides } from "../block-display-guardrails";
import { cleanText, finitePositiveNumber, formatBlockLoad, formatEffort } from "../structured-plan";
import type {
  MeasuredValue,
  SparringPlannedIntensity,
  StructuredBlock,
  StructuredSession,
} from "../types";

/** An inclusive dose range. `min === max` is an exact prescription. */
export type DoseRange = { min: number; max: number };

type TimerItemBase = {
  id: string;
  title: string;
  /** Reps / load / effort line shown under the exercise name. */
  detail: string | null;
  blockType: string | null;
};

/**
 * Work/rest rounds: sparring, conditioning intervals, pad rounds, timed blocks.
 * `needsSetup` marks a round block whose length the plan did not carry, so the
 * ready screen asks the athlete to confirm it instead of silently timing a
 * made-up dose.
 */
export type IntervalItem = TimerItemBase & {
  kind: "interval";
  rounds: number;
  workSec: number;
  restSec: number;
  sparring: boolean;
  /** Sparring only: the block's planned intensity, when its structured field states one. */
  plannedIntensity?: SparringPlannedIntensity | null;
  needsSetup: boolean;
  /** Ready-screen line shown while `needsSetup`; defaults to the plan-block copy. */
  setupNote?: string | null;
  /** Offer the common fight round formats on the ready screen. */
  presets?: boolean;
  /** Remember the athlete's picked round format under this key for next time. */
  formatMemoryKey?: string | null;
};

/**
 * Sets with rest between them. `sets` null means the plan gave no usable set
 * count, so the athlete decides when the exercise is finished. `holdSec` turns
 * each set into a timed hold; otherwise the athlete taps "Set done". `restSec`
 * null means no usable rest, so rest is picked from presets.
 */
export type SetsItem = TimerItemBase & {
  kind: "sets";
  sets: DoseRange | null;
  holdSec: number | null;
  restSec: DoseRange | null;
};

/** A block with no timeable dose (e.g. a mobility circuit): one tap to finish. */
export type TaskItem = TimerItemBase & { kind: "task" };

export type TimerItem = IntervalItem | SetsItem | TaskItem;

/** Blocks the timer never runs: they are guidance, not executable work. */
const UNTIMED_BLOCK_TYPES = new Set(["nutrition", "mindset"]);
const ROUND_BLOCK_TYPES = new Set(["sparring", "conditioning", "skill"]);

/** A round length above this is read as a whole-block total, not per round. */
const MAX_PER_ROUND_SEC = 300;

const DEFAULT_ROUND_SEC = 180;
const DEFAULT_ROUND_REST_SEC = 60;

const UNIT_SECONDS: Record<string, number> = {
  s: 1,
  sec: 1,
  secs: 1,
  second: 1,
  seconds: 1,
  m: 60,
  min: 60,
  mins: 60,
  minute: 60,
  minutes: 60,
  h: 3600,
  hr: 3600,
  hrs: 3600,
  hour: 3600,
  hours: 3600,
};

function unitSeconds(unit: string | null | undefined): number | null {
  const key = (unit ?? "").trim().toLowerCase();
  return key in UNIT_SECONDS ? UNIT_SECONDS[key] : null;
}

/** Seconds for a measured time value, or null when it is not a usable time. */
export function measuredSeconds(measured: MeasuredValue | null | undefined): number | null {
  if (!measured || !finitePositiveNumber(measured.value)) {
    return null;
  }
  const scale = unitSeconds(measured.unit);
  return scale === null ? null : Math.round(measured.value * scale);
}

/** "3-5" / "3–5" / "4" as a range, or null. */
export function parseCountRange(text: string | null | undefined): DoseRange | null {
  const match = (text ?? "").trim().match(/^(\d+)(?:\s*[-–—]\s*(\d+))?$/);
  if (!match) {
    return null;
  }
  const min = Number(match[1]);
  const max = match[2] ? Number(match[2]) : min;
  if (min <= 0 || max < min) {
    return null;
  }
  return { min, max };
}

/** "90-120 s" / "2-3 min" / "45s" / "1:30" as a range of seconds, or null. */
export function parseDurationRange(text: string | null | undefined): DoseRange | null {
  const raw = (text ?? "").trim().toLowerCase();
  const clock = raw.match(/^(\d{1,2}):(\d{2})$/);
  if (clock) {
    const seconds = Number(clock[1]) * 60 + Number(clock[2]);
    return seconds > 0 ? { min: seconds, max: seconds } : null;
  }
  const match = raw.match(/^(\d+(?:\.\d+)?)(?:\s*[-–—]\s*(\d+(?:\.\d+)?))?\s*([a-z]+)$/);
  if (!match) {
    return null;
  }
  const scale = unitSeconds(match[3]);
  if (scale === null) {
    return null;
  }
  const min = Math.round(Number(match[1]) * scale);
  const max = Math.round(Number(match[2] ?? match[1]) * scale);
  if (min <= 0 || max < min) {
    return null;
  }
  return { min, max };
}

function repsText(block: StructuredBlock): string | null {
  if (typeof block.reps === "number") {
    return finitePositiveNumber(block.reps) ? String(block.reps) : null;
  }
  return cleanText(block.reps);
}

function describeReps(reps: string | null): string | null {
  if (!reps) {
    return null;
  }
  return /^\d+(?:\s*[-–—]\s*\d+)?$/.test(reps) ? `${reps.replace(/\s*[-–—]\s*/, "–")} reps` : reps;
}

function joinDetail(parts: Array<string | null>): string | null {
  const shown = parts.filter((part): part is string => Boolean(part));
  return shown.length ? shown.join(" · ") : null;
}

const PLANNED_INTENSITY_BY_FIELD: Record<string, SparringPlannedIntensity> = {
  hard: "hard",
  high: "hard",
  light: "light",
  low: "light",
  technical: "technical",
  moderate: "contact",
  medium: "contact",
};

/**
 * The planned intensity from a sparring block's structured ``intensity`` field.
 * Exact vocabulary only (e.g. "hard", "light", "technical"): free-text wording
 * is not guessed at, so anything else is null and the log starts unselected.
 */
export function plannedSparringIntensity(block: StructuredBlock): SparringPlannedIntensity | null {
  const value = cleanText(block.intensity)?.toLowerCase() ?? "";
  return PLANNED_INTENSITY_BY_FIELD[value] ?? null;
}

function isHoldName(name: string): boolean {
  return /\b(hold|isometric|plank|carry)\b/i.test(name);
}

/**
 * Convert one structured block into a timer item, or null for guidance-only
 * blocks. Never invents a dose: a range stays a range, and a missing count or
 * rest is carried as null so the timer asks rather than guesses.
 */
export function blockToTimerItem(
  block: StructuredBlock,
  position: number,
  options: { sourceText?: string | null; countdown?: string | null } = {},
): TimerItem | null {
  const blockType = cleanText(block.block_type)?.toLowerCase() ?? null;
  if (blockType && UNTIMED_BLOCK_TYPES.has(blockType)) {
    return null;
  }
  const title = cleanText(block.display_name) || "Block";
  const id = cleanText(block.block_id) || `block-${position}`;
  const source = getSourcePrescriptionRangeOverrides(options.sourceText, title, options.countdown);

  const rounds = finitePositiveNumber(block.rounds) ? Math.round(block.rounds) : null;
  const sets = finitePositiveNumber(block.sets) ? Math.round(block.sets) : null;
  const work = measuredSeconds(block.work);
  const rest = measuredSeconds(block.rest);
  const duration = measuredSeconds(block.duration);
  const reps = repsText(block);
  const repsAsTime = parseDurationRange(reps);
  const load = formatBlockLoad(block.load);
  const effort = source.effort || formatEffort(block);
  const isRoundType = blockType !== null && ROUND_BLOCK_TYPES.has(blockType);

  // Rounds: an explicit round count or work interval, or a round-type block
  // (sparring / conditioning / skill) that is timed rather than counted in reps.
  if (rounds || work || (isRoundType && !reps && (duration || blockType === "sparring"))) {
    let workSec = work;
    if (!workSec && duration) {
      workSec = rounds && duration > MAX_PER_ROUND_SEC ? Math.round(duration / rounds) : duration;
    }
    const roundCount = rounds ?? sets ?? 1;
    return {
      kind: "interval",
      id,
      title,
      detail: joinDetail([describeReps(reps), load, effort]),
      blockType,
      rounds: roundCount,
      workSec: workSec ?? DEFAULT_ROUND_SEC,
      restSec: rest ?? (roundCount > 1 && !workSec ? DEFAULT_ROUND_REST_SEC : 0),
      sparring: blockType === "sparring",
      plannedIntensity: blockType === "sparring" ? plannedSparringIntensity(block) : null,
      needsSetup: !workSec,
      presets: !workSec,
    };
  }

  const setRange = parseCountRange(source.sets) ?? (sets ? { min: sets, max: sets } : null);
  const restRange =
    parseDurationRange(source.rest) ?? (rest ? { min: rest, max: rest } : null);

  if (setRange || reps) {
    let holdSec: number | null = null;
    if (repsAsTime) {
      holdSec = repsAsTime.min;
    } else if (duration && (!reps || (reps === "1" && isHoldName(title)))) {
      holdSec = duration;
    }
    return {
      kind: "sets",
      id,
      title,
      detail: joinDetail([holdSec ? null : describeReps(reps), load, effort]),
      blockType,
      sets: setRange,
      holdSec,
      restSec: restRange,
    };
  }

  if (duration) {
    return {
      kind: "interval",
      id,
      title,
      detail: joinDetail([load, effort]),
      blockType,
      rounds: 1,
      workSec: duration,
      restSec: 0,
      sparring: false,
      needsSetup: false,
    };
  }

  return { kind: "task", id, title, detail: joinDetail([load, effort]), blockType };
}

/** The ordered timer items for the given sessions (normally today's). */
export function buildTimerItems(
  sessions: StructuredSession[],
  options: { sourceText?: string | null; countdown?: string | null } = {},
): TimerItem[] {
  const items: TimerItem[] = [];
  const seen = new Set<string>();
  sessions.forEach((session, sessionPos) => {
    (session.blocks ?? []).forEach((block, blockPos) => {
      const item = blockToTimerItem(block, items.length, options);
      if (!item) {
        return;
      }
      // Block ids are optional presentation identity and may repeat across
      // sessions; the timer needs a unique key per item.
      const id = seen.has(item.id) ? `${item.id}-${sessionPos}-${blockPos}` : item.id;
      seen.add(id);
      items.push({ ...item, id });
    });
  });
  return items;
}

/**
 * The one structured session the backend is completing, matched on its
 * explicit session id. Completion is written against a single session, so the
 * timer must never merge a multi-session day. A day with exactly one session
 * that carries no id of its own (legacy plans key completion on the date) is
 * still unambiguous; anything else that does not match returns null, and no
 * planned-session timer is offered.
 */
export function timerSessionFor(
  sessions: StructuredSession[],
  sessionId: string | null | undefined,
): StructuredSession | null {
  const target = (sessionId ?? "").trim();
  if (!target) {
    return null;
  }
  const matched = sessions.filter((session) => cleanText(session.session_id) === target);
  if (matched.length === 1) {
    return matched[0];
  }
  if (matched.length === 0 && sessions.length === 1 && !cleanText(sessions[0].session_id)) {
    return sessions[0];
  }
  return null;
}

/**
 * Timer items for a whole training day. The athlete logs a day as one session
 * (the backend writes that one log to every session the card schedules), so
 * starting it times every timeable block of the day in card order, provided the
 * session being logged is one of that day's. [] when it is not, or when the day
 * has nothing timeable.
 */
export function dayTimerItems(
  sessions: StructuredSession[],
  sessionId: string | null | undefined,
  options: { sourceText?: string | null; countdown?: string | null } = {},
): TimerItem[] {
  return timerSessionFor(sessions, sessionId) ? buildTimerItems(sessions, options) : [];
}

export function formatRange(range: DoseRange, format: (value: number) => string = String): string {
  return range.min === range.max ? format(range.min) : `${format(range.min)}–${format(range.max)}`;
}

/** 185 → "3:05"; 45 → "0:45". */
export function formatClock(totalSeconds: number): string {
  const safe = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** 90 → "90s"; 120 → "2 min"; 150 → "2:30". */
export function formatShortDuration(totalSeconds: number): string {
  if (totalSeconds < 120) {
    return `${totalSeconds}s`;
  }
  return totalSeconds % 60 === 0 ? `${totalSeconds / 60} min` : formatClock(totalSeconds);
}
