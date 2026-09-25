import { classifySessionlessDay, cleanText, getCoachLedContactView } from "../structured-plan";
import type { StructuredDay } from "../types";
import type { IntervalItem } from "./plan";

/**
 * Coach-led combat the athlete declared in onboarding (hard sparring days) or
 * the planner downgraded (light / technical). It has no app session to start,
 * so the round timer is launched from the day itself.
 */
export type ContactKind = "sparring" | "light_combat" | "technical" | "coach_led";

export type ContactTimerTarget = {
  kind: ContactKind;
  /** The plan's own wording for the day's contact work. */
  headline: string;
};

const CONTACT_KINDS = new Set<string>(["sparring", "light_combat", "technical", "coach_led"]);

const CONTACT_TITLES: Record<ContactKind, string> = {
  sparring: "Hard sparring",
  light_combat: "Light sparring",
  technical: "Technical rounds",
  coach_led: "Contact rounds",
};

/**
 * Today's coach-led contact, from the deterministic `coach_led_contact` field
 * when the day also carries app work, else from a session-less day's headline.
 * Null when the day has no contact work to time.
 */
export function contactTimerTarget(day: StructuredDay | null | undefined): ContactTimerTarget | null {
  if (!day) {
    return null;
  }
  const contact = getCoachLedContactView(day);
  if (contact && CONTACT_KINDS.has(contact.kind)) {
    return { kind: contact.kind as ContactKind, headline: contact.title };
  }
  if ((day.sessions ?? []).length > 0) {
    return null;
  }
  const sessionless = classifySessionlessDay(day);
  if (!CONTACT_KINDS.has(sessionless.kind)) {
    return null;
  }
  return {
    kind: sessionless.kind as ContactKind,
    headline: cleanText(day.today_card?.headline) || sessionless.title,
  };
}

type ParsedRounds = { rounds: number | null; workSec: number | null; restSec: number | null };

function toSeconds(value: string, unit: string): number {
  return Math.round(Number(value) * (/^s/i.test(unit) ? 1 : 60));
}

/**
 * Round structure written into the plan's contact line, e.g. "6 x 3 min",
 * "5 rounds of 3 min, 1 min rest", "4×2min". Anything not stated stays null.
 */
export function parseRoundsFromText(text: string): ParsedRounds {
  const unit = "(s|sec|secs|seconds?|m|min|mins|minutes?)\\b";
  const structure = text.match(
    new RegExp(`(\\d{1,2})\\s*(?:x|×|rounds?\\s*(?:of|x|×)?)\\s*(\\d+(?:\\.\\d+)?)\\s*${unit}`, "i"),
  );
  const roundsOnly = text.match(/(\d{1,2})\s*rounds?\b/i);
  const rest =
    text.match(new RegExp(`(\\d+(?:\\.\\d+)?)\\s*${unit}\\s*(?:rest|recovery|between)`, "i")) ||
    text.match(new RegExp(`rest\\s*:?\\s*(\\d+(?:\\.\\d+)?)\\s*${unit}`, "i"));
  const rounds = structure ? Number(structure[1]) : roundsOnly ? Number(roundsOnly[1]) : null;
  return {
    rounds: rounds && rounds > 0 && rounds <= 30 ? rounds : null,
    workSec: structure ? toSeconds(structure[2], structure[3]) : null,
    restSec: rest ? toSeconds(rest[1], rest[2]) : null,
  };
}

/** Where the athlete's last picked contact round format is remembered. */
export const CONTACT_FORMAT_MEMORY_KEY = "unlxck.session-timer.contact-format";

export type RoundFormat = { workSec: number; restSec: number };

/** The last round format the athlete picked, or null (never throws). */
export function savedRoundFormat(key: string | null | undefined): RoundFormat | null {
  if (!key || typeof window === "undefined") {
    return null;
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) ?? "null") as Partial<RoundFormat> | null;
    const workSec = Number(parsed?.workSec);
    const restSec = Number(parsed?.restSec);
    if (Number.isFinite(workSec) && workSec >= 5 && workSec <= 3600 && Number.isFinite(restSec) && restSec >= 0 && restSec <= 1800) {
      return { workSec, restSec };
    }
  } catch {
    // Storage blocked or corrupt: fall back to the defaults.
  }
  return null;
}

export function rememberRoundFormat(key: string | null | undefined, format: RoundFormat): void {
  if (!key || typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(format));
  } catch {
    // A convenience only: the timer works without it.
  }
}

/** The display name for the day's contact work, e.g. "Hard sparring". */
export function contactTitle(target: ContactTimerTarget): string {
  return CONTACT_TITLES[target.kind];
}

/**
 * The rounds item for today's contact. This is the athlete's own gym work, so
 * the plan deliberately carries no round structure: the gym sets it. Unless the
 * plan states one, the item opens on the format the athlete last used (or
 * boxing rounds) with the presets to match what their gym is running.
 */
export function contactRoundsItem(
  target: ContactTimerTarget,
  saved: RoundFormat | null = null,
): IntervalItem {
  const parsed = parseRoundsFromText(target.headline);
  const title = CONTACT_TITLES[target.kind];
  const planned = parsed.workSec !== null;
  return {
    kind: "interval",
    id: `contact-${target.kind}`,
    title,
    detail: target.headline.toLowerCase() === title.toLowerCase() ? null : target.headline,
    blockType: "sparring",
    rounds: parsed.rounds ?? 5,
    workSec: parsed.workSec ?? saved?.workSec ?? 180,
    restSec: parsed.restSec ?? (planned ? null : saved?.restSec) ?? 60,
    sparring: true,
    needsSetup: !planned && !saved,
    setupNote: "Match your gym's rounds. Pick a format.",
    presets: true,
    formatMemoryKey: planned ? null : CONTACT_FORMAT_MEMORY_KEY,
  };
}

/** The plain round timer: no plan, pick a round format. */
export function freeRoundsItem(): IntervalItem {
  return {
    kind: "interval",
    id: "free-rounds",
    title: "Rounds",
    detail: null,
    blockType: null,
    rounds: 3,
    workSec: 180,
    restSec: 60,
    sparring: false,
    needsSetup: false,
    presets: true,
  };
}

/** Common fight round formats, offered on the ready screen. */
export const ROUND_PRESETS: Array<{ label: string; workSec: number; restSec: number }> = [
  { label: "Boxing 3/1", workSec: 180, restSec: 60 },
  { label: "Amateur 2/1", workSec: 120, restSec: 60 },
  { label: "Muay Thai 3/2", workSec: 180, restSec: 120 },
  { label: "MMA 5/1", workSec: 300, restSec: 60 },
];
