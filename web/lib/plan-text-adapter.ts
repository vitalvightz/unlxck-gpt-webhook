// Deterministic plan_text -> StructuredPlan adapter.
//
// Pure, non-visual parsing logic extracted from components/plan-viewer.tsx so
// consumers (Plan Detail's fallback renderer, the Today hook) can share it
// without importing the whole Plan Viewer component and its UI/API/admin
// dependency graph. It adapts the approved athlete-facing plan_text into the
// structured renderer's shape without another model call; every field comes
// from the saved text, so a missing server-side structured payload can never
// force the legacy renderer.
import type {
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

/** One labelled line inside a session block ("Purpose", "Progress", …). */
export type PlanTextDetail = { label: string | null; text: string };

/** A single exercise/prescription inside a session card. */
export type PlanTextBlock = {
  name: string;
  dose: string | null;
  details: PlanTextDetail[];
  /** Block-group label (Rehab, Mobility, Activation…) shown as a tag, mirroring the structured card. */
  tag: string | null;
};

/** A dated training day rendered as a session card. */
export type PlanTextSession = {
  kind: "session";
  countdown: string | null;
  weekday: string | null;
  title: string;
  objective: string | null;
  coachNote: string | null;
  blocks: PlanTextBlock[];
  notes: string[];
};

/** Lead/Final notes, rendered as a context card. */
export type PlanTextNotes = { kind: "notes"; title: string; lines: string[] };

/** A phase/week header that owns the session cards rendered beneath it. */
export type PlanTextWeek = {
  kind: "week";
  title: string;
  phase: string | null;
  sessions: PlanTextSession[];
};

export type PlanTextGroup = PlanTextNotes | PlanTextWeek | PlanTextSession;

export function humanizeStatus(value: string) {
  return value.replace(/_/g, " ");
}

export function titleizeToken(value: string) {
  const normalized = humanizeStatus(value || "").trim();
  if (!normalized) {
    return "";
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

// Leading list/bullet markers stripped off a line before it is parsed. Includes
// the unicode bullets the rehab renderer emits ("• [Drill] — [Dose]", see
// fightcamp/stage2_payload.py) so the glyph never leaks into an exercise title.
const LEADING_BULLET_RE = /^[-*•‣▪◦·]\s+/;

function stripPlanMarkup(value: string): string {
  return value
    .replace(/^#{1,6}\s+/, "")
    .replace(LEADING_BULLET_RE, "")
    .replace(/^\d+\.\s+/, "")
    .replace(/\*\*/g, "")
    .trim();
}

function normalizePlanTextForCards(rawText: string): string {
  return rawText
    .replace(/\r\n/g, "\n")
    .replace(/(^|\n)(Lead notes|Active notes)\s+[-–—]?\s*/gi, "$1$2\n")
    .replace(/\s+(?=(?:GPP|SPP|TAPER|FIGHT[ _]WEEK|REINTEGRATION)\s*[—–\-:]\s*Week\b)/gi, "\n")
    .replace(/\s+(?=D-\d+\s*\([^)]+\)\s*[—–\-:]\s*\S)/g, "\n")
    .replace(
      /\s+(?=(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:sday)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b[^()]*\(\s*D-\d+\s*\)\s*[—–\-:]\s*\S)/gi,
      "\n",
    )
    .replace(/\s+(?=(?:Final notes|End of plan notes)\b)/gi, "\n")
    .replace(/(^|\n)(Final notes|End of plan notes)\s+[-–—]?\s*/gi, "$1$2\n");
}

// Labelled sub-lines that fall *inside* a session block. The plan text packs a
// lot of structure behind these prefixes ("Purpose: …", "Progress/regress: …",
// "Stop rule: …"), so we surface each as its own kicker+text line instead of
// flattening them into one wall of prose. Longest variants must come first so
// "Progress/regress/stop" wins over "Progress".
const SESSION_DETAIL_LABELS: { match: RegExp; label: string }[] = [
  { match: /^purpose$/i, label: "Purpose" },
  { match: /^purpose\s*&\s*why$/i, label: "Purpose" },
  { match: /^why today$/i, label: "Why" },
  { match: /^why$/i, label: "Why" },
  { match: /^duration$/i, label: "Duration" },
  { match: /^prescription$/i, label: "Prescription" },
  { match: /^output$/i, label: "Output" },
  { match: /^intensity$/i, label: "Intensity" },
  { match: /^coach call$/i, label: "Coach call" },
  { match: /^week note$/i, label: "Week note" },
  { match: /^final coach call(?:\s*\(one line\))?$/i, label: "Coach call" },
  { match: /^progress\/regress\/stop$/i, label: "Progress" },
  { match: /^progression\/regression\/stop$/i, label: "Progress" },
  { match: /^progress\/regress$/i, label: "Progress" },
  { match: /^progression\/regression$/i, label: "Progress" },
  { match: /^progression$/i, label: "Progress" },
  { match: /^progress$/i, label: "Progress" },
  { match: /^regression$/i, label: "Regress" },
  { match: /^regress$/i, label: "Regress" },
  { match: /^stop rule$/i, label: "Stop" },
  { match: /^stop$/i, label: "Stop" },
  { match: /^easier$/i, label: "Easier" },
  { match: /^swaps?$/i, label: "Swaps" },
  { match: /^rest$/i, label: "Rest" },
  { match: /^note$/i, label: "Note" },
];

const SESSION_LABEL_SPLIT_RE =
  /\b(Purpose\s*&\s*why|Purpose|Why today|Why|Duration|Prescription|Output|Intensity|Coach call|Week note|Final coach call(?:\s*\(one line\))?|Progression\/regression\/stop|Progress\/regress\/stop|Progression\/regression|Progress\/regress|Progression|Progress|Regression|Regress|Stop rule|Stop|Easier|Swaps?|Rest|Note)\s*:/gi;

function normalizeSessionLabel(raw: string): string {
  const trimmed = raw.trim();
  for (const { match, label } of SESSION_DETAIL_LABELS) {
    if (match.test(trimmed)) {
      return label;
    }
  }
  return titleizeToken(trimmed);
}

/**
 * Split a body line into its labelled segments. "Purpose: raise the base.
 * Progress/regress: add 5 min. Stop rule: stop if dizzy." becomes three
 * labelled details; an unlabelled line returns a single `label: null` segment.
 */
export function splitLabeledSegments(text: string): PlanTextDetail[] {
  const clean = text.trim();
  if (!clean) {
    return [];
  }
  const matches = [...clean.matchAll(SESSION_LABEL_SPLIT_RE)];
  if (!matches.length) {
    return [{ label: null, text: clean }];
  }
  const segments: PlanTextDetail[] = [];
  const lead = clean.slice(0, matches[0].index ?? 0).trim();
  if (lead) {
    segments.push({ label: null, text: lead });
  }
  for (let i = 0; i < matches.length; i += 1) {
    const match = matches[i];
    const start = (match.index ?? 0) + match[0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index ?? clean.length : clean.length;
    const body = clean
      .slice(start, end)
      .trim()
      .replace(/^[-–—]\s*/, "");
    if (body) {
      segments.push({ label: normalizeSessionLabel(match[1]), text: body });
    }
  }
  return segments.length ? segments : [{ label: null, text: clean }];
}

type PlanTextHeading =
  | { kind: "notes"; title: string; remainder: string | null }
  | { kind: "week"; title: string; phase: string | null }
  | { kind: "session"; countdown: string; weekday: string | null; title: string; remainder: string | null };

// Deterministic plan_text contract (mirrors fightcamp/weekly_plan_render.py +
// the stage2 validator's countdown-header rule). Phase labels are the canonical
// camp phases; the header separator is em-dash, en-dash, hyphen, or colon.
const PHASE_TOKEN = "GPP|SPP|TAPER|FIGHT[ _]WEEK|REINTEGRATION";
const WEEKDAY_TOKEN =
  "mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:sday)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?";
const HEADER_SEP = "[—–\\-:]";
const PHASE_FIRST_WEEK_RE = new RegExp(`^(${PHASE_TOKEN})\\s*${HEADER_SEP}\\s*(Week\\s+\\d+.*)$`, "i");
const BARE_WEEK_RE = /^Week\s+\d+\b/i;
const PHASE_ANYWHERE_RE = new RegExp(`\\b(${PHASE_TOKEN})\\b`, "i");
// "D-33 (Wednesday) — Aerobic support" (final/validated countdown-first form).
const SESSION_COUNTDOWN_FIRST_RE = new RegExp(
  `^D-(\\d+)\\s*\\(([^)]+)\\)\\s*${HEADER_SEP}\\s*(.+)$`,
  "i",
);
// "Wednesday (D-33) — Aerobic support" (Stage 1 deterministic weekday-first form).
const SESSION_WEEKDAY_FIRST_RE = new RegExp(
  `^(${WEEKDAY_TOKEN})[^()]*\\(\\s*D-(\\d+)\\s*\\)\\s*${HEADER_SEP}\\s*(.+)$`,
  "i",
);
// Plan-level context sections that live outside any week. Only the always-on
// note labels live here (recognised with or without a leading "#"); generic
// markdown sections like "## Nutrition" are handled by the markdown-header
// branch so a session body line such as "Recovery: light spin" is never
// mistaken for a new section.
const NOTE_SECTION_RE =
  /^(Lead notes|Final notes|Active notes|End of plan notes)(?:\s*[—–\-:]\s*(.+))?$/i;

function normalizePhaseToken(value: string): string {
  return value.replace(/_/g, " ").toUpperCase();
}

// On a run-on plan_text line the session metadata (the "Why:" objective, a
// labelled note, or a coach-led freshness note) can sit inline after the
// heading. Split it off the title so it is parsed as body instead of being
// buried in (or lost from) the title. Markers require a colon or a distinctive
// coach phrase, so ordinary title words ("Stop-and-go", a leading "Coach-led
// boxing session") are never split.
const SESSION_TITLE_BODY_MARKER =
  /\s(?=(?:Why|Purpose|Progress\/regress\/stop|Progress\/regress|Progression|Progress|Regress|Stop rule|Stop|Easier|Swaps?|Rest|Note)\s*:|No (?:extra|app) S\s?&?\s?C|Coach owns this session|Train with your coach)/i;

function splitSessionTitle(title: string): { title: string; remainder: string | null } {
  const markerIndex = title.search(SESSION_TITLE_BODY_MARKER);
  if (markerIndex > -1) {
    return { title: title.slice(0, markerIndex).trim(), remainder: title.slice(markerIndex).trim() || null };
  }
  return { title, remainder: null };
}

function classifyPlanTextHeading(line: string): PlanTextHeading | null {
  const isMarkdownHeader = /^\s*#{1,6}\s+/.test(line);
  const clean = stripPlanMarkup(line);
  if (!clean || /^#+$/.test(clean)) {
    return null;
  }

  const noteMatch = clean.match(NOTE_SECTION_RE);
  if (noteMatch) {
    return { kind: "notes", title: titleizeToken(noteMatch[1].trim()), remainder: noteMatch[2]?.trim() || null };
  }

  // Phase-prefixed week ("GPP — Week 1 (D-33 to D-27) — Build base"), or a bare
  // "Week N — …" header that may carry its phase token mid-line. Phase renders
  // as a tag, the rest as the title.
  const phaseWeek = clean.match(PHASE_FIRST_WEEK_RE);
  if (phaseWeek) {
    return { kind: "week", title: phaseWeek[2].trim(), phase: normalizePhaseToken(phaseWeek[1]) };
  }
  if (BARE_WEEK_RE.test(clean)) {
    const phase = clean.match(PHASE_ANYWHERE_RE);
    return { kind: "week", title: clean, phase: phase ? normalizePhaseToken(phase[1]) : null };
  }

  const session = clean.match(SESSION_COUNTDOWN_FIRST_RE);
  if (session) {
    const split = splitSessionTitle(session[3].trim());
    return {
      kind: "session",
      countdown: `D-${session[1]}`,
      weekday: session[2].trim() || null,
      title: split.title,
      remainder: split.remainder,
    };
  }
  const weekdaySession = clean.match(SESSION_WEEKDAY_FIRST_RE);
  if (weekdaySession) {
    const split = splitSessionTitle(weekdaySession[3].trim());
    return {
      kind: "session",
      countdown: `D-${weekdaySession[2]}`,
      weekday: titleizeToken(weekdaySession[1].trim()),
      title: split.title,
      remainder: split.remainder,
    };
  }

  // Any other markdown header (## Nutrition, ## Progression, …) opens its own
  // context card rather than being swallowed into the previous session.
  if (isMarkdownHeader) {
    return { kind: "notes", title: clean, remainder: null };
  }

  return null;
}

const COACH_LED_RE = /no (?:extra|app) s\s?&?\s?c|coach owns this session|train with your coach/i;

// Standalone session sub-headings the rehab/accessory renderer emits before a
// group of bulleted items (RULE 12 and its suppressed-heading alternatives in
// fightcamp/stage2_payload.py). On their own line these are a block-group label,
// not an exercise, so we surface them as a tag on the grouped blocks — mirroring
// the structured card's block_type chip — instead of leaking the bare word
// (e.g. "Rehab") as a stray note on the previous block.
const BLOCK_GROUP_LABELS = [
  "Rehab",
  "Prehab",
  "Activation",
  "Movement prep",
  "Mobility",
  "Warm-up",
  "Warmup",
  "Cool-down",
  "Cooldown",
  "Reset",
  "Recovery",
  "Strength",
  "Power",
  "Conditioning",
  "Skill",
  "Accessory",
] as const;
const BLOCK_GROUP_LABEL_RE = new RegExp(`^(?:${BLOCK_GROUP_LABELS.join("|")})\\s*:?\\s*$`, "i");

/** A line that is *only* a block-group label → its canonical tag, else null. */
function matchBlockGroupLabel(line: string): string | null {
  const clean = stripPlanMarkup(line);
  if (!BLOCK_GROUP_LABEL_RE.test(clean)) {
    return null;
  }
  return titleizeToken(clean.replace(/:\s*$/, ""));
}

/**
 * Parse athlete plan_text into structured groups (context notes, week sections,
 * and the session cards beneath them). This is the fallback used when no
 * machine-readable structured_plan is present, so it re-derives the same card
 * shape the structured renderer shows — weeks, dated sessions, the session
 * objective, and each exercise with its Purpose / Progress / Stop detail —
 * instead of dumping every line into one undifferentiated block.
 */
export function parsePlanText(rawText: string): PlanTextGroup[] {
  const lines = normalizePlanTextForCards(rawText).split("\n");
  const groups: PlanTextGroup[] = [];
  let currentWeek: PlanTextWeek | null = null;
  let currentSession: PlanTextSession | null = null;
  let currentNotes: PlanTextNotes | null = null;
  // The block-group label (Rehab, Mobility…) currently in effect within a
  // session, applied as a tag to the blocks beneath it until the next group
  // header or the next session.
  let currentBlockTag: string | null = null;

  const pushSession = (session: PlanTextSession) => {
    if (currentWeek) {
      currentWeek.sessions.push(session);
    } else {
      groups.push(session);
    }
  };

  const addBodyLine = (line: string) => {
    if (!currentSession) {
      return;
    }
    const session = currentSession;
    const listItem = line.match(/^([-*•‣▪◦·]|\d+\.)\s+(.+)$/);
    const wasListItem = Boolean(listItem);
    const content = stripPlanMarkup(listItem ? listItem[2] : line);
    if (!content) {
      return;
    }
    if (COACH_LED_RE.test(content) && !content.includes(" — ")) {
      session.coachNote = content;
      return;
    }
    for (const segment of splitLabeledSegments(content)) {
      const block = session.blocks[session.blocks.length - 1];
      if (segment.label === "Why" && !block && !session.objective) {
        session.objective = segment.text;
        continue;
      }
      if (segment.label) {
        if (block) {
          block.details.push(segment);
        } else {
          session.notes.push(`${segment.label}: ${segment.text}`);
        }
        continue;
      }
      // Unlabelled: an exercise heading (Name — dose), or a bulleted exercise,
      // otherwise loose detail attached to the current block / session. The
      // matched separator is always exactly " - " / " — " (3 chars).
      const dashIndex = segment.text.search(/\s[-–—]\s/);
      const colonBlock = segment.text.match(/^([^:]{2,80}):\s+(.+)$/);
      if (wasListItem && colonBlock) {
        session.blocks.push({
          name: colonBlock[1].trim(),
          dose: colonBlock[2].trim() || null,
          details: [],
          tag: currentBlockTag,
        });
      } else if (dashIndex > -1) {
        session.blocks.push({
          name: segment.text.slice(0, dashIndex).trim(),
          dose: segment.text.slice(dashIndex + 3).trim() || null,
          details: [],
          tag: currentBlockTag,
        });
      } else if (wasListItem) {
        // A bulleted line is its own exercise heading (e.g. a rehab drill whose
        // dose sits on the next line), so it always opens a new block rather than
        // folding into the previous one.
        session.blocks.push({ name: segment.text, dose: null, details: [], tag: currentBlockTag });
      } else if (block) {
        block.details.push({ label: null, text: segment.text });
      } else {
        session.notes.push(segment.text);
      }
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || /^#+$/.test(line)) {
      continue;
    }

    const heading = classifyPlanTextHeading(line);
    if (heading?.kind === "notes") {
      currentSession = null;
      currentWeek = null;
      currentNotes = { kind: "notes", title: heading.title, lines: [] };
      groups.push(currentNotes);
      if (heading.remainder) {
        currentNotes.lines.push(stripPlanMarkup(heading.remainder));
      }
      continue;
    }
    if (heading?.kind === "week") {
      currentSession = null;
      currentNotes = null;
      currentWeek = { kind: "week", title: heading.title, phase: heading.phase, sessions: [] };
      groups.push(currentWeek);
      continue;
    }
    if (heading?.kind === "session") {
      currentNotes = null;
      currentBlockTag = null;
      currentSession = {
        kind: "session",
        countdown: heading.countdown,
        weekday: heading.weekday,
        title: heading.title,
        objective: null,
        coachNote: null,
        blocks: [],
        notes: [],
      };
      pushSession(currentSession);
      // Inline metadata split off a run-on heading line is parsed as body.
      if (heading.remainder) {
        addBodyLine(heading.remainder);
      }
      continue;
    }

    if (currentSession) {
      // A standalone block-group header (e.g. "Rehab") tags the blocks beneath
      // it rather than rendering as a loose note.
      const blockGroup = matchBlockGroupLabel(line);
      if (blockGroup) {
        currentBlockTag = blockGroup;
        continue;
      }
      addBodyLine(line);
      continue;
    }
    if (currentNotes) {
      const content = stripPlanMarkup(line.replace(/^([-*]|\d+\.)\s+/, ""));
      if (content) {
        currentNotes.lines.push(content);
      }
      continue;
    }

    // Loose preamble before any heading: keep it in an intro notes card.
    const content = stripPlanMarkup(line.replace(/^([-*]|\d+\.)\s+/, ""));
    if (content) {
      currentNotes = { kind: "notes", title: "Plan", lines: [content] };
      groups.push(currentNotes);
    }
  }

  return groups;
}

function countdownDays(value: string | null): number | null {
  const match = value?.match(/^D-(\d+)$/i);
  if (!match) {
    return null;
  }
  const parsed = Number.parseInt(match[1], 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateFromCountdown(
  fightDate: string | null | undefined,
  countdown: string | null,
): string | null {
  const match = fightDate?.trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  const days = countdownDays(countdown);
  if (!match || days === null) {
    return null;
  }
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function detailText(block: PlanTextBlock, labels: string[]): string[] {
  const wanted = new Set(labels.map((label) => label.toLowerCase()));
  return block.details
    .filter((detail) => detail.label && wanted.has(detail.label.toLowerCase()))
    .map((detail) => detail.text);
}

function inferBlockType(block: PlanTextBlock): string {
  const value = `${block.tag || ""} ${block.name}`.toLowerCase();
  if (/rehab|prehab|mobility|activation|warm-?up|cool-?down|reset|recovery/.test(value)) {
    return "rehab";
  }
  if (/condition|aerobic|anaerobic|bike|run|sprint|interval/.test(value)) {
    return "conditioning";
  }
  if (/strength|power|throw|jump|plyo|lift/.test(value)) {
    return "strength_power";
  }
  if (/skill|technical|tactical|shadowbox|footwork|cue card|film|watch/.test(value)) {
    return "skill";
  }
  return block.tag?.toLowerCase().replace(/\s+/g, "_") || "training";
}

function inferSessionType(session: PlanTextSession): string {
  const blocks = session.blocks
    .map((block) => `${block.tag || ""} ${block.name}`)
    .join(" ");
  const value = `${session.title} ${blocks}`.toLowerCase();
  if (/spar|coach-led|boxing|grappling|wrestling|muay thai|kickbox/.test(value)) {
    return "skill";
  }
  if (/recover|reset|mobility|breath|rest/.test(value)) {
    return "recovery";
  }
  if (/condition|aerobic|anaerobic|bike|run|sprint|interval/.test(value)) {
    return "conditioning";
  }
  if (/strength|power|throw|jump|plyo|lift/.test(value)) {
    return "strength_power";
  }
  if (/tactical|technical|skill|shadowbox|footwork|cue|film|watch|visuali/.test(value)) {
    return "skill";
  }
  return "mixed";
}

function toStructuredBlock(block: PlanTextBlock, index: number): StructuredBlock {
  const purpose = detailText(block, ["Purpose", "Why"]).join(" ") || null;
  const progression = detailText(block, ["Progress"]).join(" ") || null;
  const regressions = detailText(block, ["Regress", "Regression", "Easier"]);
  const substitutions = detailText(block, ["Swap", "Swaps"]);
  const mappedLabels = new Set([
    "purpose",
    "why",
    "progress",
    "regress",
    "regression",
    "easier",
    "swap",
    "swaps",
  ]);
  const coachingCues = block.details
    .filter((detail) => !detail.label || !mappedLabels.has(detail.label.toLowerCase()))
    .map((detail) => (detail.label ? `${detail.label}: ${detail.text}` : detail.text));

  return {
    block_id: `text-block-${index + 1}`,
    block_type: inferBlockType(block),
    display_name: block.name,
    order_index: index,
    load: block.dose ? { display: block.dose } : null,
    purpose,
    coaching_cues: coachingCues,
    regression_options: regressions,
    substitutions,
    progression_rule: progression,
  };
}

function toStructuredSession(session: PlanTextSession, index: number): StructuredSession {
  const notes = session.notes.join(" ").trim();
  const objective = [session.objective, notes].filter(Boolean).join(" ") || null;
  return {
    session_id: `text-session-${index + 1}`,
    session_type: inferSessionType(session),
    title: session.title,
    objective,
    blocks: session.blocks.map(toStructuredBlock),
  };
}

function toStructuredDays(
  sessions: PlanTextSession[],
  fightDate: string | null | undefined,
  phase: string | null,
): StructuredDay[] {
  const grouped = new Map<string, PlanTextSession[]>();
  sessions.forEach((session, index) => {
    const key = session.countdown || `session-${index + 1}`;
    grouped.set(key, [...(grouped.get(key) || []), session]);
  });

  return [...grouped.values()].map((daySessions, dayIndex) => {
    const countdown = daySessions[0]?.countdown || null;
    const coachLed = daySessions.find((session) => session.coachNote);
    const appSessions = daySessions.filter(
      (session) => session !== coachLed || session.blocks.length > 0,
    );
    const coachOnly = Boolean(coachLed && appSessions.length === 0);
    return {
      date: dateFromCountdown(fightDate, countdown),
      countdown_label: countdown,
      phase_label: phase,
      day_type: "moderate",
      today_card: coachLed
        ? {
            headline: coachOnly ? coachLed.title : null,
            coach_led_contact: coachOnly ? null : coachLed.coachNote || coachLed.title,
          }
        : null,
      sessions: coachOnly
        ? []
        : appSessions.map((session, sessionIndex) =>
            toStructuredSession(session, dayIndex * 100 + sessionIndex),
          ),
    };
  });
}

function weekIndex(value: string, fallback: number): number {
  const match = value.match(/\bWeek\s+(\d+)\b/i);
  return match ? Number.parseInt(match[1], 10) : fallback;
}

// Week headings carry navigation metadata as well as the actual coaching goal,
// for example "Week 1 (D-53 to D-47) — Restore structural tolerance". The
// renderer already supplies "Week N", so only the meaningful trailing focus
// belongs in week_goal. Keeping the metadata here caused visible labels such as
// "Week 1 — Week 1 (D-53...)" and made synthetic fallback weeks read
// "Week 2 — Week 1".
function weekGoal(value: string, phase: string | null): string | null {
  let goal = value
    .replace(/^\s*Week\s+\d+\b/i, "")
    .replace(/^\s*\(\s*D-?\d+\s*(?:to|through|[-–—→])\s*D-?\d+\s*\)/i, "")
    .replace(/^\s*[-–—:|]+\s*/, "")
    .trim();

  if (phase) {
    const escapedPhase = phase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    goal = goal
      .replace(new RegExp(`^${escapedPhase}\\b`, "i"), "")
      .replace(/^\s*[-–—:|]+\s*/, "")
      .trim();
  }

  return goal || null;
}

function toStructuredWeek(
  week: PlanTextWeek,
  index: number,
  fightDate: string | null | undefined,
): StructuredWeek {
  const days = toStructuredDays(week.sessions, fightDate, week.phase);
  const dates = days
    .map((day) => day.date)
    .filter((date): date is string => Boolean(date))
    .sort();
  const countdowns = days
    .map((day) => day.countdown_label)
    .filter((countdown): countdown is string => Boolean(countdown));
  return {
    week_id: `text-week-${index + 1}`,
    week_index: weekIndex(week.title, index + 1),
    phase_label: week.phase,
    week_goal: weekGoal(week.title, week.phase),
    start_date: dates[0] || null,
    end_date: dates[dates.length - 1] || null,
    countdown_start: countdowns[0] || null,
    countdown_end: countdowns[countdowns.length - 1] || null,
    days,
  };
}

function noteCategory(title: string): string {
  const normalized = title.toLowerCase();
  if (normalized.includes("injur") || normalized.includes("safety")) return "injury";
  if (normalized.includes("nutrition") || normalized.includes("weight")) return "nutrition";
  if (normalized.includes("recover")) return "recovery";
  return "general";
}

/**
 * Adapt approved plan_text into the full structured renderer without another
 * model call. Every field comes from the saved athlete-facing text, so a missing
 * server-side structured payload can never force the legacy renderer.
 */
export function buildStructuredPlanFromText(
  rawText: string,
  fightDate?: string | null,
): StructuredPlan {
  const groups = parsePlanText(rawText);
  const notes = groups
    .filter((group): group is PlanTextNotes => group.kind === "notes")
    .filter((group) => group.lines.length > 0)
    .map((group) => ({
      category: noteCategory(group.title),
      label: group.title,
      text: group.lines.join(" "),
    }));
  const explicitWeeks = groups.filter(
    (group): group is PlanTextWeek => group.kind === "week",
  );
  const looseSessions = groups.filter(
    (group): group is PlanTextSession => group.kind === "session",
  );
  const weekGroups = [...explicitWeeks];
  if (looseSessions.length > 0) {
    weekGroups.push({
      kind: "week",
      title: explicitWeeks.length > 0 ? `Week ${explicitWeeks.length + 1}` : "Week 1",
      phase: null,
      sessions: looseSessions,
    });
  }
  if (weekGroups.length === 0) {
    weekGroups.push({ kind: "week", title: "Week 1", phase: null, sessions: [] });
  }

  return {
    schema_version: "text-adapter.v1",
    plan_metadata: { title: "Fight Camp", plan_type: "fight_camp", status: "ready" },
    event_context: fightDate ? { fight_date: fightDate } : null,
    plan_notes: notes,
    weeks: weekGroups.map((week, index) => toStructuredWeek(week, index, fightDate)),
    raw_markdown_fallback: rawText,
  };
}
