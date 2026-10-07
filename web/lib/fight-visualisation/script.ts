/**
 * Guided Fight Visualisation: turns the plan's visualisation session into a
 * spoken script with timed silence.
 *
 * The prescription itself (why, steps, cue, pre-bout line) comes verbatim from
 * the planner's Fight Visualisation bank via the session card. This module only
 * adds the delivery around it: a short breathing settle, the silence the athlete
 * needs to actually run each picture, and a close. The silence is the point; a
 * voice that talks the whole time does the rehearsal for them.
 */
import { cleanText } from "../structured-plan";
import { measuredSeconds } from "../session-timer/plan";
import type { StructuredBlock, StructuredSession } from "../types";

export type FightVisualisation = {
  /** The bank entry's name, e.g. "Tactical Picture". */
  name: string;
  why: string | null;
  steps: string[];
  cue: string | null;
  preBout: string | null;
  /** The prescribed dose, in seconds. */
  durationSec: number;
};

export type GuidePhase = "settle" | "frame" | "rehearse" | "anchor" | "close";

export type GuideSegment =
  | { kind: "say"; text: string; phase: GuidePhase; estimateSec: number }
  | { kind: "hold"; seconds: number; phase: GuidePhase };

export type GuideScript = {
  visualisation: FightVisualisation;
  segments: GuideSegment[];
  /** Planned length: spoken estimates plus every hold. */
  totalSec: number;
};

const VISUALISATION_TITLE_RE = /\bfight\s+visuali[sz]ation\b/i;
const VISUALISATION_ID_RE = /fight-visuali[sz]ation$/i;
const DEFAULT_DURATION_SEC = 5 * 60;

/** True for the planner's locked Fight Visualisation session. */
export function isFightVisualisationSession(
  session: StructuredSession | null | undefined,
): boolean {
  if (!session) return false;
  return (
    VISUALISATION_TITLE_RE.test(cleanText(session.title) ?? "") ||
    VISUALISATION_ID_RE.test(cleanText(session.session_id) ?? "")
  );
}

function prefixed(line: string, prefix: string): string | null {
  const match = line.match(new RegExp(`^${prefix}\\s*:\\s*(.+)$`, "i"));
  return match ? match[1].trim() : null;
}

/**
 * The visualisation a session prescribes, or null when the session is not a
 * Fight Visualisation or carries no steps to guide. The locked merge writes the
 * bank's instructions into the block's `coaching_cues`, followed by
 * "Cue: ..." and, on fight day, "Pre-bout: ...".
 */
export function fightVisualisationFromSession(
  session: StructuredSession | null | undefined,
): FightVisualisation | null {
  if (!session || !isFightVisualisationSession(session)) return null;
  const block: StructuredBlock | undefined = (session.blocks ?? []).find(
    (item) => (item.coaching_cues ?? []).some((cue) => cleanText(cue)),
  );
  if (!block) return null;

  const steps: string[] = [];
  let cue: string | null = null;
  let preBout: string | null = null;
  for (const raw of block.coaching_cues ?? []) {
    const line = cleanText(raw);
    if (!line) continue;
    const cueText = prefixed(line, "cue");
    const preBoutText = prefixed(line, "pre-?bout");
    if (cueText) cue ??= cueText;
    else if (preBoutText) preBout ??= preBoutText;
    else steps.push(line);
  }
  if (steps.length === 0) return null;

  return {
    name: cleanText(block.display_name) || "Fight Visualisation",
    why: cleanText(block.purpose) || cleanText(session.objective),
    steps,
    cue: cue ?? (cleanText(session.mindset_anchor?.confidence_anchor) || null),
    preBout,
    durationSec:
      measuredSeconds(block.duration) ?? measuredSeconds(session.planned_duration) ?? DEFAULT_DURATION_SEC,
  };
}

/** Rough spoken length at the narrator's slow, calm rate (~140 wpm). */
export function estimateSpeechSec(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(1.5, Math.round((words / 2.3) * 10) / 10);
}

/** Shortest silence that still lets the athlete see a step once. */
const MIN_STEP_GAP_SEC = 5;
/** Longest single silence: beyond this attention drifts rather than deepens. */
const MAX_STEP_GAP_SEC = 75;
/** At this length and above there is room for a full real-time run-through. */
const RUN_THROUGH_MIN_SEC = 4 * 60;
/** Share of the rehearsal time given to that run-through. */
const RUN_THROUGH_SHARE = 0.35;
const MAX_RUN_THROUGH_SEC = 150;

function sentence(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function buildGuideScript(visualisation: FightVisualisation): GuideScript {
  const short = visualisation.durationSec < 3 * 60;
  const runThrough = visualisation.durationSec >= RUN_THROUGH_MIN_SEC;
  const segments: GuideSegment[] = [];
  const say = (text: string, phase: GuidePhase) =>
    segments.push({ kind: "say", text, phase, estimateSec: estimateSpeechSec(text) });
  const hold = (seconds: number, phase: GuidePhase) =>
    segments.push({ kind: "hold", seconds: Math.max(1, Math.round(seconds)), phase });

  // Settle: the breath slows the athlete down before the picture starts.
  say("Find somewhere quiet. Sit or lie down, and close your eyes.", "settle");
  hold(3, "settle");
  say("Breathe in through your nose.", "settle");
  hold(4, "settle");
  say("And out, slowly.", "settle");
  hold(6, "settle");
  if (!short) {
    say("Again. In.", "settle");
    hold(4, "settle");
    say("And out.", "settle");
    hold(6, "settle");
  }

  if (visualisation.why) {
    say(sentence(visualisation.why), "frame");
    hold(2, "frame");
  }

  // Everything except the rehearsal gaps is fixed; the rest of the dose is
  // silence for the athlete to run the picture.
  const closing = [
    ...(visualisation.cue ? [`Your cue. ${sentence(visualisation.cue)}`, sentence(visualisation.cue)] : []),
    ...(visualisation.preBout ? [`Before you walk out. ${sentence(visualisation.preBout)}`] : []),
    "Let the picture go. When you're ready, open your eyes.",
  ];
  const runThroughLine = "Now run it all again, start to finish, in real time.";
  const spokenSoFar = segments.reduce(
    (sum, item) => sum + (item.kind === "say" ? item.estimateSec : item.seconds),
    0,
  );
  const stepSpeech = visualisation.steps.reduce((sum, step) => sum + estimateSpeechSec(step), 0);
  const closingSec =
    closing.reduce((sum, line) => sum + estimateSpeechSec(line), 0) + 3 * closing.length;
  const fixedSec =
    spokenSoFar + stepSpeech + closingSec + (runThrough ? estimateSpeechSec(runThroughLine) : 0);
  const stepCount = visualisation.steps.length;
  const pool = Math.max(visualisation.durationSec - fixedSec, stepCount * MIN_STEP_GAP_SEC);
  let runThroughSec = runThrough ? Math.min(pool * RUN_THROUGH_SHARE, MAX_RUN_THROUGH_SEC) : 0;
  let stepGap = (pool - runThroughSec) / stepCount;
  if (stepGap > MAX_STEP_GAP_SEC) {
    // Overflow goes to the run-through when there is one; otherwise the dose
    // simply ends a little early rather than leaving minutes of dead air.
    if (runThrough) {
      runThroughSec = Math.min(
        runThroughSec + (stepGap - MAX_STEP_GAP_SEC) * stepCount,
        MAX_RUN_THROUGH_SEC,
      );
    }
    stepGap = MAX_STEP_GAP_SEC;
  }

  for (const step of visualisation.steps) {
    say(sentence(step), "rehearse");
    hold(Math.max(stepGap, MIN_STEP_GAP_SEC), "rehearse");
  }
  if (runThrough) {
    say(runThroughLine, "rehearse");
    hold(runThroughSec, "rehearse");
  }

  closing.forEach((line, index) => {
    const phase: GuidePhase = index === closing.length - 1 ? "close" : "anchor";
    say(line, phase);
    hold(3, phase);
  });

  const totalSec = segments.reduce(
    (sum, item) => sum + (item.kind === "say" ? item.estimateSec : item.seconds),
    0,
  );
  return { visualisation, segments, totalSec: Math.round(totalSec) };
}

/** Planned seconds elapsed before segment `index` starts. */
export function elapsedBefore(script: GuideScript, index: number): number {
  return script.segments
    .slice(0, index)
    .reduce((sum, item) => sum + (item.kind === "say" ? item.estimateSec : item.seconds), 0);
}
