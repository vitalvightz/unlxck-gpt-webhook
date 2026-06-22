"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  approveAndResumeGeneration,
  approvePlanForRelease,
  archivePlan,
  deletePlan,
  getActivePlan,
  getPlan,
  isRetryableApiFailure,
  permanentlyDeletePlan,
  rejectApprovedPlan,
  renamePlan,
  setActivePlan,
  submitManualStage2,
} from "@/lib/api";
import { canSetActivePlan } from "@/lib/plan-active";
import { clearCompletedGenerationForDeletedPlan } from "@/lib/completed-generation";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";
import { QuickBuildRefinementBanner } from "@/components/quick-build-refinement-banner";
import { StructuredPlanRenderer } from "@/components/structured-plan-renderer";
import { WhyTooltip } from "@/components/why-tooltip";
import { useGenerationController } from "@/lib/generation-controller";
import { canUseAdminPlanControls, isAdminRole } from "@/lib/plan-admin-controls";
import { STAGE2_HARD_BLOCKER_CODE_SET } from "@/lib/stage2-policy";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import { selectInjuryRiskAdvisory } from "@/lib/sparring-advisory";
import { explainRiskBand } from "@/lib/sparring-reason-codes";
import {
  buildBlockedInjuryContextSummary,
  buildBlockedWhy,
  type BlockedInjuryContextSummary,
} from "@/lib/triage-block-reasons";
import type { PlanAdvisory, PlanDetail, UserRole } from "@/lib/types";
import { hasTriageResumeApproval, shouldShowTriageBlockedState } from "@/lib/triage-view";

const TRIAGE_RESUME_FETCH_ATTEMPTS = 5;
const TRIAGE_RESUME_FETCH_DELAY_MS = 800;
const APPROVE_RECOVERY_FETCH_ATTEMPTS = 3;
const APPROVE_RECOVERY_FETCH_DELAY_MS = 800;
const STRUCTURED_PLAN_POLL_INTERVAL_MS = 2500;
// Background structuring can take up to ~2 minutes for a full camp. We never make
// the athlete wait for it: the template card (parsed from plan_text) is shown
// immediately, and we poll quietly in the background to swap in the richer
// structured card the moment it lands. The poll window covers the backend Stage 2
// conversion timeout (UNLXCK_STAGE2_TIMEOUT_SECONDS, default 210s) plus a small
// buffer; once it elapses we simply stop polling and the template card stays.
const STRUCTURED_PLAN_UPGRADE_POLL_WINDOW_MS = 220_000;
const STRUCTURED_PLAN_RECENT_PLAN_THRESHOLD_MS = 5 * 60_000;

const ATHLETE_VISIBLE_STATUSES = new Set(["ready", "publishable_with_flags"]);

/**
 * A plan counts as released to the athlete once it lands in an athlete-visible
 * status with non-empty plan_text. Used both to render the published state and
 * to confirm an approval that may have completed server-side after a network
 * timeout on the approve request.
 */
export function isPlanReleasedToAthlete(
  plan: Pick<PlanDetail, "status" | "outputs">,
): boolean {
  const status = (plan.status || "").trim().toLowerCase();
  return ATHLETE_VISIBLE_STATUSES.has(status) && Boolean(plan.outputs.plan_text.trim());
}

/**
 * Decide whether a freshly published plan is still expecting its richer
 * structured card to land in the background. When true, the athlete is shown the
 * template card (parsed from plan_text) right away while we poll quietly and swap
 * in the structured card once it arrives — there is no waiting screen and no
 * "fallback" notice. We only await an upgrade for plans that can still produce
 * one. We never await for:
 *  - legacy/old plans (created outside the recent-plan window), which may simply
 *    never have a structured_plan,
 *  - plans without an access token (we cannot poll for the structured card),
 *  - triage-blocked plans,
 *  - plans whose background poll window has already elapsed,
 *  - plans that already have a structured_plan.
 */
export function shouldAwaitStructuredPlanUpgrade(params: {
  hasPublishedPlan: boolean;
  hasStructuredPlan: boolean;
  pollWindowExpired: boolean;
  hasAccessToken: boolean;
  isRecentPlan: boolean;
  isTriageBlocked?: boolean;
}): boolean {
  return (
    params.hasPublishedPlan &&
    !params.hasStructuredPlan &&
    !params.pollWindowExpired &&
    params.hasAccessToken &&
    params.isRecentPlan &&
    params.isTriageBlocked !== true
  );
}

/**
 * A plan is "recent" if it was created within the recent-plan window. Used to
 * avoid holding the structured-card finalising state for legacy plans that were
 * created long before structured plans existed (or never produced one).
 */
export function isRecentlyCreatedPlan(
  plan: Pick<PlanDetail, "created_at">,
  now: number = Date.now(),
): boolean {
  const createdAt = Date.parse(plan.created_at || "");
  if (Number.isNaN(createdAt)) {
    return false;
  }
  return now - createdAt <= STRUCTURED_PLAN_RECENT_PLAN_THRESHOLD_MS;
}

/**
 * Whether the background upgrade poll should run for this plan.
 *
 * Unlike the visible "enhancing" hint (shouldAwaitStructuredPlanUpgrade), this is
 * deliberately NOT gated on plan recency. A published plan that is still missing
 * its structured card should keep trying to pick one up whenever its view is
 * open — including an older plan whose card was only built later (e.g. after a
 * held blocker cleared or a backfill ran), which the 5-minute recency gate would
 * otherwise leave stuck on the template card until a manual reload. The
 * mount-scoped poll window (pollWindowExpired) still bounds the cost so we never
 * poll a legacy cardless plan forever, and the swap happens silently for
 * non-recent plans (no misleading hint).
 */
export function shouldPollForStructuredPlanUpgrade(params: {
  hasPublishedPlan: boolean;
  hasStructuredPlan: boolean;
  pollWindowExpired: boolean;
  hasAccessToken: boolean;
  isTriageBlocked?: boolean;
}): boolean {
  return (
    params.hasPublishedPlan &&
    !params.hasStructuredPlan &&
    !params.pollWindowExpired &&
    params.hasAccessToken &&
    params.isTriageBlocked !== true
  );
}

function getApprovalSuccessMessage(plan: Pick<PlanDetail, "outputs">): string {
  return shouldRenderStructuredPlan(plan.outputs)
    ? "Plan approved and released to the athlete view."
    : "Plan approved and released. The athlete sees their plan now; the full card view follows automatically once it finishes building.";
}

/**
 * Recover from a flaky approve request. The backend commits the approval before
 * any slow post-processing, so a retryable network/timeout error is frequently a
 * false negative — the plan is already released. For those errors only, re-fetch
 * the plan a few times and return it once it reads as released to the athlete.
 * Returns `null` when the error is not retryable or the plan never becomes
 * released within the recovery window, so the caller surfaces the original error.
 */
export async function resolveApprovalAfterError(params: {
  error: unknown;
  fetchPlan: () => Promise<PlanDetail>;
  attempts?: number;
  wait?: (attempt: number) => Promise<void>;
}): Promise<PlanDetail | null> {
  if (!isRetryableApiFailure(params.error)) {
    return null;
  }
  const attempts = params.attempts ?? APPROVE_RECOVERY_FETCH_ATTEMPTS;
  const wait =
    params.wait ?? ((attempt: number) => sleep(APPROVE_RECOVERY_FETCH_DELAY_MS * (attempt + 1)));
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const refreshedPlan = await params.fetchPlan();
      if (isPlanReleasedToAthlete(refreshedPlan)) {
        return refreshedPlan;
      }
    } catch {
      // Ignore transient fetch failures during the recovery window.
    }
    if (attempt < attempts - 1) {
      await wait(attempt);
    }
  }
  return null;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

type ValidatorIssue = Record<string, unknown>;
type ReviewIssue = {
  code: string;
  title: string;
  message: string;
  severity: "error" | "warning";
  context?: string;
  snippet?: string;
};

type InjuryTriageView = {
  mode?: string;
  reasons: string[];
  red_flags: string[];
  matched_high_risk_categories: string[];
  routing_reasons: string[];
  urgent_flags: string[];
  sparring_risk_band?: string;
  clinician_clearance_required?: boolean;
};

const FRACTURE_CATEGORY_SET = new Set([
  "fracture",
  "stress_fracture",
  "hairline_fracture",
  "rib_fracture",
  "broken_rib",
]);

type RiskBandTone = "green" | "amber" | "red" | "black";

const BLOCKING_WARNING_CODES = STAGE2_HARD_BLOCKER_CODE_SET;
const NON_PUBLISHABLE_STAGE2_STATUSES = new Set([
  "triage_blocked",
  "triage_resume_approved",
  "medical_hold",
  "restricted_rehab_only",
]);
const TRIAGE_BLOCKED_STUB_MARKERS = [
  "## Injury Triage: Restricted Rehab Only",
  "Normal fight-camp planning is intentionally suspended",
  "Clinician clearance is required",
];

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

const ISSUE_TITLES: Record<string, string> = {
  restriction_violation: "Restriction violation",
  missing_required_element: "Missing phase-critical element",
  phase_section_missing: "Missing phase section",
  weak_anchor_session: "Weak anchor session",
  support_takeover_before_anchor: "Support work took over too early",
  conditional_conditioning_choice: "Conditioning is still unresolved",
  too_many_fallbacks: "Too many fallback branches",
  unresolved_access_fallback: "Fallback does not match real access needs",
  template_like_session_render: "Session still reads like a template",
  taper_option_overload: "Taper is too noisy",
  equipment_incongruent_selection: "Equipment mismatch",
  missing_week_session_role: "Week structure is missing a session",
  late_camp_session_incomplete: "Late-camp week is incomplete",
  weekly_session_overage: "Too many sessions in a week",
  weekly_rhythm_broken: "Weekly rhythm broke",
  missing_weight_cut_acknowledgement: "Weight-cut stress is missing",
  high_pressure_weight_cut_underaddressed: "High-pressure cut is underaddressed",
  sport_language_leak: "Cross-sport wording leaked in",
  overstyled_drill_name: "Naming still needs cleanup",
  gimmick_name: "Naming still needs cleanup",
};

function humanizeStatus(value: string) {
  return value.replace(/_/g, " ");
}

function titleizeToken(value: string) {
  const normalized = humanizeStatus(value || "").trim();
  if (!normalized) {
    return "";
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatStructuredValue(value: unknown, fallback: string) {
  if (value == null) {
    return fallback;
  }
  if (typeof value === "string") {
    return value.trim() || fallback;
  }
  if (typeof value === "object") {
    const entries = Array.isArray(value) ? value : Object.keys(value as Record<string, unknown>);
    if (!entries.length) {
      return fallback;
    }
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function buildArtifactFilename(plan: PlanDetail, suffix: string) {
  const base =
    (plan.full_name || "athlete-plan")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "athlete-plan";
  return `${base}-${suffix}.txt`;
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
  { match: /^why today$/i, label: "Why" },
  { match: /^why$/i, label: "Why" },
  { match: /^progress\/regress\/stop$/i, label: "Progress" },
  { match: /^progress\/regress$/i, label: "Progress" },
  { match: /^progression$/i, label: "Progress" },
  { match: /^progress$/i, label: "Progress" },
  { match: /^regress$/i, label: "Regress" },
  { match: /^stop rule$/i, label: "Stop" },
  { match: /^stop$/i, label: "Stop" },
  { match: /^easier$/i, label: "Easier" },
  { match: /^swaps?$/i, label: "Swaps" },
  { match: /^rest$/i, label: "Rest" },
  { match: /^note$/i, label: "Note" },
];

const SESSION_LABEL_SPLIT_RE =
  /\b(Purpose|Why today|Why|Progress\/regress\/stop|Progress\/regress|Progression|Progress|Regress|Stop rule|Stop|Easier|Swaps?|Rest|Note)\s*:/gi;

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
  /\s(?=(?:Why|Purpose|Progress\/regress\/stop|Progress\/regress|Progression|Progress|Regress|Stop rule|Stop|Easier|Swaps?|Rest|Note)\s*:|No app S|Coach owns this session|Train with your coach)/i;

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

const COACH_LED_RE = /no app s\s?&?\s?c|coach owns this session|train with your coach/i;

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
      if (dashIndex > -1) {
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

function PlanTextNotesCard({ notes }: { notes: PlanTextNotes }) {
  return (
    <section className="sp-card sp-active-notes legacy-plan-notes">
      <p className="sp-eyebrow">{notes.title}</p>
      {notes.lines.map((line, index) => (
        <p key={`${notes.title}-${index}`} className="sp-block-purpose">
          {line}
        </p>
      ))}
    </section>
  );
}

function PlanTextBlockCard({ block }: { block: PlanTextBlock }) {
  return (
    <div className="sp-block">
      <div className="sp-block-head">
        <span className="sp-block-title">{block.name}</span>
        {block.tag ? <span className="sp-tag">{block.tag}</span> : null}
      </div>
      {block.dose ? (
        <div className="sp-block-stats">
          <span className="sp-stat">
            <span className="sp-stat-label">Dose</span>
            {block.dose}
          </span>
        </div>
      ) : null}
      {block.details.map((detail, index) =>
        detail.label ? (
          <p key={`${block.name}-${index}`} className="sp-block-aside">
            <span className="sp-stat-label">{detail.label}</span>
            {detail.text}
          </p>
        ) : (
          <p key={`${block.name}-${index}`} className="sp-block-purpose">
            {detail.text}
          </p>
        ),
      )}
    </div>
  );
}

function PlanTextSessionCard({ session }: { session: PlanTextSession }) {
  return (
    <article className="sp-session legacy-plan-card">
      <header className="sp-session-head">
        <div>
          {session.countdown || session.weekday ? (
            <div className="sp-day-labels sp-session-day-labels">
              {session.countdown ? (
                <span className="sp-countdown sp-accent">{session.countdown}</span>
              ) : null}
              {session.weekday ? <span className="sp-day-date">{session.weekday}</span> : null}
            </div>
          ) : null}
          <h4 className="sp-session-title">{session.title}</h4>
          {session.objective ? <p className="sp-session-objective">{session.objective}</p> : null}
        </div>
      </header>
      {session.coachNote ? <p className="sp-today-note">{session.coachNote}</p> : null}
      {session.blocks.length ? (
        <div className="sp-blocks">
          {session.blocks.map((block, index) => (
            <PlanTextBlockCard key={`${block.name}-${index}`} block={block} />
          ))}
        </div>
      ) : null}
      {session.notes.map((note, index) => (
        <p key={`note-${index}`} className="sp-block-purpose">
          {note}
        </p>
      ))}
    </article>
  );
}

function PlanTextWeekSection({ week, defaultOpen }: { week: PlanTextWeek; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details className="sp-week" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="sp-week-summary">
        <span className="sp-week-title">{week.title}</span>
        {week.phase ? <span className="sp-tag sp-accent">{week.phase}</span> : null}
      </summary>
      <div className="sp-week-body">
        {week.sessions.length ? (
          week.sessions.map((session, index) => (
            <PlanTextSessionCard key={`${session.countdown}-${index}`} session={session} />
          ))
        ) : (
          <p className="sp-muted">No sessions scheduled.</p>
        )}
      </div>
    </details>
  );
}

function PlanTextCards({ text }: { text: string }) {
  const groups = parsePlanText(text);

  if (!groups.length) {
    return (
      <section className="sp-root legacy-plan-root">
        <article className="sp-session legacy-plan-card">
          <header className="sp-session-head">
            <div>
              <p className="sp-eyebrow">Saved plan</p>
              <h4 className="sp-session-title">No plan cards available</h4>
            </div>
          </header>
          <p className="sp-session-objective">This saved plan does not contain athlete-facing plan content.</p>
        </article>
      </section>
    );
  }

  const firstWeekIndex = groups.findIndex((group) => group.kind === "week");
  return (
    <section className="sp-root legacy-plan-root" aria-label="Saved plan cards">
      <header className="sp-header legacy-plan-header">
        <p className="sp-eyebrow">Saved plan</p>
        <h3 className="sp-title">Training plan</h3>
      </header>
      <div className="legacy-plan-card-stack">
        {groups.map((group, index) => {
          if (group.kind === "notes") {
            return <PlanTextNotesCard key={`notes-${index}`} notes={group} />;
          }
          if (group.kind === "week") {
            return (
              <PlanTextWeekSection
                key={`week-${index}`}
                week={group}
                defaultOpen={index === firstWeekIndex}
              />
            );
          }
          return <PlanTextSessionCard key={`session-${index}`} session={group} />;
        })}
      </div>
    </section>
  );
}

// Shown above the template card while the richer structured card is still being
// built in the background. It is intentionally a light, positive hint — the plan
// is already usable below, and the view upgrades itself the moment the card
// lands. This is NOT a fallback/error state, so it never blocks or replaces the
// plan content.
function StructuredPlanUpgradingNotice() {
  return (
    <div className="quick-build-refine-banner" role="status" aria-live="polite">
      <div className="quick-build-refine-banner__body">
        <p className="quick-build-refine-banner__kicker">
          Enhancing your plan view
          <span className="loading-title-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
        </p>
        <h2 className="quick-build-refine-banner__title">Your plan is ready below</h2>
        <p className="quick-build-refine-banner__copy">
          We&apos;re building the full structured card in the background. Your plan is shown below
          now and this view will upgrade to the richer card automatically — no need to wait or
          refresh.
        </p>
      </div>
    </div>
  );
}

export type StructuredCardDebug = { status: string; errors: string[] };

/**
 * The structured-card conversion outcome recorded on the plan's validator report
 * ({status, errors}; see api/stage2_automation._record_structured_outcome).
 *
 * Returned for ANY recorded status because the only place this is shown is over
 * the plan_text fallback (card not rendering), where each status is diagnostic:
 *  - `invalid_fallback_used` → the converted card was rejected (faithfulness /
 *    schema drift) so no card was persisted,
 *  - `valid` / `repair_attempted_valid` → a card WAS built and validated but is
 *    not the one showing, i.e. it was lost on a later write or no longer decodes
 *    at read time (the "card built then lost" signal),
 *  - `not_attempted` → structured generation never ran for this plan.
 * Returns null only when there is no recorded outcome at all.
 */
export function readStructuredCardDebug(
  plan: Pick<PlanDetail, "admin_outputs">,
): StructuredCardDebug | null {
  const report = plan.admin_outputs?.stage2_validator_report;
  const debug =
    report && typeof report === "object"
      ? (report as Record<string, unknown>).structured_plan
      : null;
  if (!debug || typeof debug !== "object") {
    return null;
  }
  const record = debug as Record<string, unknown>;
  const status = typeof record.status === "string" ? record.status.trim() : "";
  if (!status) {
    return null;
  }
  // Coerce defensively: a null/undefined entry must not surface as the literal
  // strings "null"/"undefined", and whitespace-only reasons are dropped.
  const errors = Array.isArray(record.errors)
    ? record.errors.map((entry) => (entry != null ? String(entry).trim() : "")).filter(Boolean)
    : [];
  return { status, errors };
}

/**
 * Admin-only explainer shown over the plan_text fallback so the reason a
 * structured card is missing is visible instead of the card silently
 * disappearing. Messaging differs by recorded status: a rejected conversion
 * lists the drift reasons; a `valid` status here means the card was built but
 * lost (the athlete is still on the fallback).
 */
function StructuredCardDiagnostic({ debug }: { debug: StructuredCardDebug }) {
  const wasBuilt = debug.status === "valid" || debug.status === "repair_attempted_valid";
  const notAttempted = debug.status === "not_attempted";
  const heading = wasBuilt ? "Structured card built but not shown" : "Structured card not built";
  const copy = wasBuilt
    ? "A structured card was built and validated for this plan, but it is not the card showing — it was most likely overwritten on a later write or no longer decodes at read time, so the athlete is on the text fallback."
    : notAttempted
      ? "Structured generation never ran for this plan, so the athlete is on the text fallback."
      : "The athlete is seeing the text fallback because the converted structured card was rejected, so no card was saved. Approving the plan does not rebuild it; the reasons below show how the card drifted from the saved plan text.";
  return (
    <section className="support-panel" role="status">
      <div className="form-section-header">
        <p className="kicker">Admin diagnostic</p>
        <h3>
          {heading} — {humanizeStatus(debug.status)}
        </h3>
      </div>
      <p className="muted">{copy}</p>
      {debug.errors.length ? (
        <ul className="summary-list">
          {debug.errors.map((reason, index) => (
            <li key={`${reason}-${index}`}>{reason}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function getPlanDisplayName(plan: Pick<PlanDetail, "plan_name" | "fight_date">) {
  return plan.plan_name?.trim() || plan.fight_date || "Open plan";
}

function formatRiskBandLabel(riskBand: NonNullable<PlanAdvisory["risk_band"]>) {
  const normalized = humanizeStatus(riskBand || "").trim();
  if (!normalized) {
    return "Unknown";
  }
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

export function readInjuryTriage(plan: PlanDetail): InjuryTriageView | null {
  const whyLogTriage =
    plan.admin_outputs?.why_log && typeof plan.admin_outputs.why_log === "object"
      ? (plan.admin_outputs.why_log as Record<string, unknown>).injury_triage
      : null;
  const adminOutputsRecord = plan.admin_outputs as Record<string, unknown> | undefined;
  const planRecord = plan as Record<string, unknown>;
  const source = whyLogTriage ?? adminOutputsRecord?.injury_triage ?? planRecord.injury_triage;

  if (source && typeof source === "object") {
    const triage = source as Record<string, unknown>;
    const mode = typeof triage.mode === "string" ? triage.mode : undefined;
    const reasons = Array.isArray(triage.reasons) ? triage.reasons.map(String) : [];
    const redFlags = Array.isArray(triage.red_flags) ? triage.red_flags.map(String) : [];
    const matchedCategories = Array.isArray(triage.matched_high_risk_categories)
      ? triage.matched_high_risk_categories.map(String)
      : [];
    const routingReasons = Array.isArray(triage.routing_reasons) ? triage.routing_reasons.map(String) : [];
    const urgentFlags = Array.isArray(triage.urgent_flags) ? triage.urgent_flags.map(String) : [];

    const hasStructuredSignal = Boolean(
      mode || reasons.length || redFlags.length || matchedCategories.length || routingReasons.length || urgentFlags.length,
    );
    if (!hasStructuredSignal) {
      return null;
    }

    return {
      mode,
      reasons,
      red_flags: redFlags,
      matched_high_risk_categories: matchedCategories,
      routing_reasons: routingReasons,
      urgent_flags: urgentFlags,
      sparring_risk_band:
        typeof triage.sparring_risk_band === "string" ? triage.sparring_risk_band : undefined,
      clinician_clearance_required:
        typeof triage.clinician_clearance_required === "boolean"
          ? triage.clinician_clearance_required
          : undefined,
    };
  }

  if (plan.status === "triage_blocked" || plan.admin_outputs?.stage2_status === "triage_blocked") {
    return {
      mode: "needs_review",
      reasons: ["Protected planner state was triggered before finalization."],
      red_flags: [],
      matched_high_risk_categories: [],
      routing_reasons: [],
      urgent_flags: [],
      sparring_risk_band: undefined,
      clinician_clearance_required: undefined,
    };
  }

  return null;
}

export function readRawTriageMode(plan: PlanDetail): string | null {
  const whyLog = plan.admin_outputs?.why_log;
  const whyLogTriage =
    whyLog && typeof whyLog === "object"
      ? (whyLog as Record<string, unknown>).injury_triage
      : null;

  const adminOutputsRecord = plan.admin_outputs as Record<string, unknown> | undefined;
  const planRecord = plan as Record<string, unknown>;

  const sources = [whyLogTriage, adminOutputsRecord?.injury_triage, planRecord.injury_triage];

  for (const source of sources) {
    if (source && typeof source === "object") {
      const mode = (source as Record<string, unknown>).mode;
      if (typeof mode === "string" && mode.trim()) {
        return mode.trim();
      }
    }
  }

  return null;
}


export function shouldShowProtectedResumeAdminReview(input: {
  isTriageBlocked: boolean;
  isProtectedTriageResumePending: boolean;
  hasResumeApproval: boolean;
}): boolean {
  return input.isTriageBlocked || input.isProtectedTriageResumePending || input.hasResumeApproval;
}

export function getAdminReviewHeading(input: {
  showProtectedResumeAdminReview: boolean;
  hasResumeApproval: boolean;
}): string {
  if (!input.showProtectedResumeAdminReview) {
    return "Manual Stage 2 actions";
  }
  return input.hasResumeApproval ? "Resume generation required" : "Planning blocked before Stage 2";
}

export function canRetryResumeGenerationForPlan(input: {
  isAdmin: boolean;
  isProtectedTriageResumePending: boolean;
  injuryTriageMode?: string | null;
  rawTriageMode?: string | null;
  planStatus?: string | null;
}): boolean {
  const normalize = (val?: string | null) => String(val || "").trim().toLowerCase();
  if (
    normalize(input.injuryTriageMode) === "medical_hold" ||
    normalize(input.rawTriageMode) === "medical_hold" ||
    normalize(input.planStatus) === "medical_hold"
  ) {
    return false;
  }

  return (
    input.isAdmin &&
    input.isProtectedTriageResumePending &&
    (isResumableTriageMode(input.injuryTriageMode) ||
      isResumableTriageMode(input.rawTriageMode) ||
      isResumableTriageMode(input.planStatus))
  );
}

function BlockedPlanDecisionCard({
  triage,
  injuryContext,
  isAdmin,
}: {
  triage: InjuryTriageView;
  injuryContext?: BlockedInjuryContextSummary | null;
  isAdmin: boolean;
}) {
  const isMedicalHold = triage.mode === "medical_hold";
  const isRestricted = triage.mode === "restricted_rehab_only";
  const [injuryDetailsOpen, setInjuryDetailsOpen] = useState(false);
  const capturedInjuries = injuryContext?.capturedInjuries ?? [];
  const legacyInjuryText = injuryContext?.legacyInjuryText?.trim() || "";
  const pauseReasons = injuryContext?.pauseReasons ?? [];
  const hasCapturedDetail = capturedInjuries.length > 0 || Boolean(legacyInjuryText);

  const title = isMedicalHold
    ? "Medical hold"
    : isRestricted
      ? "Clearance required"
      : "Planning paused";

  const intro = isMedicalHold
    ? "No training plan was released. This intake contains urgent or medically disqualifying signals that require review before planning can continue."
    : isRestricted
      ? "Normal fight-camp release has been paused. This intake contains structural injury signals that require clinician clearance before loading or sparring resumes."
      : "Normal fight-camp release has been paused. This intake triggered a protected planner state before finalization.";

  const signalTokens = [...triage.matched_high_risk_categories, ...triage.red_flags]
    .map(titleizeToken)
    .filter(Boolean)
    .slice(0, 6);

  const triageRiskBand =
    triage.sparring_risk_band &&
    ["green", "amber", "red", "black"].includes(triage.sparring_risk_band)
      ? (triage.sparring_risk_band as RiskBandTone)
      : null;
  const displayedRiskBand = isMedicalHold
    ? triageRiskBand === "black"
      ? "black"
      : null
    : triageRiskBand;
  const riskBandLabel = displayedRiskBand
    ? formatRiskBandLabel(displayedRiskBand as NonNullable<PlanAdvisory["risk_band"]>)
    : null;

  return (
    <section
      className={`support-panel sparring-advisory-card ${
        isMedicalHold ? "support-panel-alert" : "sparring-advisory-convert"
      }`}
    >
      <div className="plan-header-row">
        <div>
          <p className="kicker">Planner decision</p>
          <h3>{title}</h3>
        </div>
        <div className="sparring-advisory-badges">
          <span className="badge">PROTECTED</span>
          <span className="badge">STAGE 2 SKIPPED</span>
          {riskBandLabel && displayedRiskBand ? (
            <span
              className={`sparring-risk-chip sparring-risk-${displayedRiskBand}`}
              aria-label={`Injury risk ${riskBandLabel}`}
            >
              <span className="sparring-risk-dot" aria-hidden="true" />
              <span>Sparring risk: {riskBandLabel}</span>
              {(() => {
                const riskExplanation = explainRiskBand(displayedRiskBand);
                const blockedExplanation = buildBlockedWhy(triage);
                return (
                  <WhyTooltip
                    title={blockedExplanation.title}
                    body={`${blockedExplanation.body}${riskExplanation ? ` ${riskExplanation.body}` : ""}`}
                  />
                );
              })()}
            </span>
          ) : null}
        </div>
      </div>

      <p>{intro}</p>

      {injuryContext?.capturedInjury ? (
        <div className="blocked-context-line">
          <div>
            <strong>Captured injury:</strong> {injuryContext.capturedInjury}
          </div>
        </div>
      ) : null}

      {injuryContext?.blockedTrigger ? (
        <div className="blocked-context-line">
          <div>
            <strong>Blocked trigger:</strong> {injuryContext.blockedTrigger}
          </div>
        </div>
      ) : null}

      {hasCapturedDetail ? (
        <div className="blocked-context-line">
          <button
            type="button"
            className="ghost-button"
            onClick={() => setInjuryDetailsOpen((open) => !open)}
            aria-expanded={injuryDetailsOpen}
          >
            {injuryDetailsOpen ? "Hide injury details" : "Show injury details"}
          </button>
          {injuryDetailsOpen ? (
            capturedInjuries.length ? (
              <ul className="summary-list">
                {capturedInjuries.map((injury, index) => (
                  <li key={`${injury.headline}-${index}`}>
                    <div>
                      <strong>{injury.headline}</strong>
                    </div>
                    {injury.meta.length ? (
                      <div className="plan-card-meta">
                        {injury.meta.map((entry) => (
                          <span key={entry} className="badge status-badge-neutral">
                            {entry}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {injury.flags.length ? (
                      <div className="plan-card-meta">
                        {injury.flags.map((flag) => (
                          <span key={flag} className="badge">
                            {flag}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {injury.notes ? (
                      <div>
                        <em>Athlete notes:</em> {injury.notes}
                      </div>
                    ) : null}
                    {injury.avoid ? (
                      <div>
                        <em>Avoid:</em> {injury.avoid}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <div>
                <strong>Captured injury:</strong> {legacyInjuryText}
              </div>
            )
          ) : null}
        </div>
      ) : null}

      {isAdmin && pauseReasons.length ? (
        <div className="blocked-context-line">
          <strong>Why this was paused</strong>
          <ul className="summary-list">
            {pauseReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {isAdmin && signalTokens.length ? (
        <div className="plan-card-meta">
          {signalTokens.map((token) => (
            <span key={token} className="badge status-badge-neutral">
              {token}
            </span>
          ))}
        </div>
      ) : null}

      <ul className="summary-list">
        <li>Stage 2 was skipped intentionally.</li>
        <li>
          {isMedicalHold
            ? "Medical review is required before any plan can be released."
            : "Only already-approved rehab or clinician-led guidance should continue until clearance."}
        </li>
        {triage.clinician_clearance_required ? (
          <li>Clinician clearance is required before return to loading or sparring.</li>
        ) : null}
      </ul>
    </section>
  );
}

function SparringAdvisoryCard({ advisory }: { advisory: PlanAdvisory }) {
  // Surfaced only for advisories carrying a real injury-risk band (see
  // selectInjuryRiskAdvisory). The directive leads; generated rationale is
  // intentionally omitted because it is too noisy for the athlete view.
  const directive = (advisory.replacement || advisory.suggestion || "").trim();
  const daysLabel = (advisory.days || []).join(", ").trim();
  const riskBandLabel = advisory.risk_band ? formatRiskBandLabel(advisory.risk_band) : null;
  const explanation = advisory.risk_band ? explainRiskBand(advisory.risk_band) : null;

  return (
    <section
      className={`support-panel sparring-advisory-card sparring-advisory-${advisory.action}`}
    >
      <div className="plan-header-row">
        <div>
          <p className="kicker">Sparring risk</p>
          {daysLabel ? <h3>{daysLabel}</h3> : <h3>Hard sparring</h3>}
        </div>
        {riskBandLabel ? (
          <span
            className={`sparring-risk-chip sparring-risk-${advisory.risk_band}`}
            aria-label={`Injury risk ${riskBandLabel}`}
          >
            <span className="sparring-risk-dot" aria-hidden="true" />
            <span>Injury risk: {riskBandLabel}</span>
            {explanation ? <WhyTooltip title={explanation.title} body={explanation.body} /> : null}
          </span>
        ) : null}
      </div>
      {directive ? <p className="sparring-advisory-suggestion">{directive}</p> : null}
      <p className="muted sparring-advisory-disclaimer">{advisory.disclaimer}</p>
    </section>
  );
}

function downloadArtifact(text: string, filename: string) {
  if (!text.trim()) {
    return;
  }
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function safeIssueList(value: unknown): ValidatorIssue[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is ValidatorIssue => Boolean(item) && typeof item === "object");
}

function issueTitle(code: string) {
  return ISSUE_TITLES[code] || humanizeStatus(code || "review issue");
}

function joinContextBits(bits: Array<string | null | undefined>) {
  return bits.filter((bit): bit is string => Boolean(bit && bit.trim())).join(" | ");
}

function normalizeIssueText(value: unknown) {
  return typeof value === "string" && value ? value.replace(/_/g, " ") : null;
}

function formatIssueContext(issue: ValidatorIssue) {
  const equipment =
    Array.isArray(issue.required_equipment) && issue.required_equipment.length
      ? `Needs ${issue.required_equipment.map((item) => String(item).replace(/_/g, " ")).join(", ")}`
      : null;

  return joinContextBits([
    typeof issue.phase === "string" && issue.phase ? issue.phase : null,
    typeof issue.week_index === "number" ? `Week ${issue.week_index}` : null,
    typeof issue.session_index === "number" ? `Session ${issue.session_index}` : null,
    normalizeIssueText(issue.requirement),
    normalizeIssueText(issue.restriction),
    equipment,
  ]);
}

function buildReviewIssue(issue: ValidatorIssue, severity: "error" | "warning"): ReviewIssue {
  const code = typeof issue.code === "string" ? issue.code : "review_issue";
  const message =
    typeof issue.message === "string" && issue.message.trim()
      ? issue.message.trim()
      : issueTitle(code);
  const snippet =
    typeof issue.line === "string" && issue.line.trim() ? issue.line.trim() : undefined;

  return {
    code,
    title: issueTitle(code),
    message,
    severity,
    context: formatIssueContext(issue) || undefined,
    snippet,
  };
}

function resolveWarningBuckets(report: Record<string, unknown> | null | undefined) {
  const warnings = safeIssueList(report?.warnings);
  const explicitBlockingWarnings = safeIssueList(report?.blocking_warnings);

  if (explicitBlockingWarnings.length) {
    return {
      blockingWarnings: explicitBlockingWarnings.filter((issue) =>
        BLOCKING_WARNING_CODES.has(String(issue.code || "")),
      ),
    };
  }

  return {
    blockingWarnings: warnings.filter((issue) =>
      BLOCKING_WARNING_CODES.has(String(issue.code || "")),
    ),
  };
}

function pluralize(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

export function hasBlockedTriageStubText(...texts: Array<string | null | undefined>): boolean {
  const combined = texts
    .map((text) => (typeof text === "string" ? text.trim() : ""))
    .filter(Boolean)
    .join("\n");
  return TRIAGE_BLOCKED_STUB_MARKERS.some((marker) => combined.includes(marker));
}

export function isProtectedTriageResumePendingState(input: {
  isTriageBlocked: boolean;
  stage2Status?: string | null;
  containsBlockedTriageStub: boolean;
  athletePlanText: string;
  finalPlanText?: string | null;
}): boolean {
  const normalizedStage2Status = (input.stage2Status || "").trim().toLowerCase();
  const hasEmptyAthletePlanWithFinalStub =
    !input.athletePlanText.trim() && hasBlockedTriageStubText(input.finalPlanText);
  return (
    input.isTriageBlocked ||
    normalizedStage2Status === "triage_resume_approved" ||
    normalizedStage2Status === "triage_blocked" ||
    input.containsBlockedTriageStub ||
    hasEmptyAthletePlanWithFinalStub
  );
}

export function isResumableTriageMode(modeOrStatus?: string | null): boolean {
  const normalized = String(modeOrStatus || "").trim().toLowerCase();
  return normalized === "needs_review" || normalized === "restricted_rehab_only";
}

export function buildReviewSummary(
  report: Record<string, unknown> | null | undefined,
  stage2Status: string,
  options?: {
    hasBlockedTriageStubText?: boolean;
  },
) {
  const normalizedStage2Status = String(stage2Status || "").trim().toLowerCase();
  const errors = safeIssueList(report?.errors).map((issue) => buildReviewIssue(issue, "error"));
  const { blockingWarnings } = resolveWarningBuckets(report);
  const blocking = blockingWarnings.map((issue) => buildReviewIssue(issue, "warning"));
  const blockingCount = blocking.length;
  const isPublishableFromReport = errors.length === 0 && blocking.length === 0;
  const isExplicitlyNonPublishableStatus = NON_PUBLISHABLE_STAGE2_STATUSES.has(normalizedStage2Status);
  const isBlockedTriageStub = Boolean(options?.hasBlockedTriageStubText);
  const isPublishable =
    !isExplicitlyNonPublishableStatus && !isBlockedTriageStub && isPublishableFromReport;

  const summary = {
    errors,
    blocking,
    blockingCount,
    isPublishable,
  };

  if (errors.length + blocking.length === 0) {
    return {
      ...summary,
      hasIssues: false,
      headline:
        normalizedStage2Status === "triage_resume_approved"
          ? "Resume approved — regeneration pending. A regenerated final result is required before release."
          : stage2Status === "stage2_failed"
          ? "Stage 2 held this plan, but no detailed validator reasons were saved in the report."
          : "No validator issues were saved for this plan.",
      guidance:
        normalizedStage2Status === "triage_resume_approved"
          ? "Keep this plan blocked until Stage 2 regeneration completes and a real final result replaces the triage stub."
          : stage2Status === "stage2_failed"
          ? "Open the latest model output and retry prompt below to see what still needs work."
          : "This usually means the plan is held for workflow reasons rather than a specific validator issue.",
    };
  }

  const summaryParts = [
    errors.length ? pluralize(errors.length, "blocking error") : null,
    blockingCount ? pluralize(blockingCount, "blocking issue") : null,
  ].filter((part): part is string => Boolean(part));

  if (isPublishable) {
    return {
      ...summary,
      hasIssues: false,
      headline: "This plan is ready to release.",
      guidance: "No hard blockers remain. Approval is now just a release decision.",
    };
  }

  return {
    ...summary,
    hasIssues: true,
    headline: `${summaryParts.join(" and ")} are currently holding this Stage 2 plan.`,
    guidance:
      isBlockedTriageStub
        ? "This plan still contains triage placeholder text and cannot be released to the athlete."
        : errors.length > 0
        ? "Fix the hard blockers first."
        : "These blockers were found on the latest validation pass. You can retry or approve anyway to release.",
  };
}

function ArtifactActions({
  artifactKey,
  text,
  filename,
}: {
  artifactKey: string;
  text: string;
  filename: string;
}) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!copiedKey) {
      return;
    }
    const timeout = window.setTimeout(() => setCopiedKey(null), 1800);
    return () => window.clearTimeout(timeout);
  }, [copiedKey]);

  if (!text.trim()) {
    return null;
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(artifactKey);
    } catch {
      // clipboard write failed; no visible feedback shown
    }
  }

  return (
    <div className="plan-summary-actions">
      <button type="button" className="ghost-button" onClick={handleCopy}>
        {copiedKey === artifactKey ? "Copied" : "Copy text"}
      </button>
      <button type="button" className="ghost-button" onClick={() => downloadArtifact(text, filename)}>
        Download .txt
      </button>
    </div>
  );
}

function QuickCopyButton({ text, artifactKey }: { text: string; artifactKey: string }) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!copiedKey) {
      return;
    }
    const timeout = window.setTimeout(() => setCopiedKey(null), 1800);
    return () => window.clearTimeout(timeout);
  }, [copiedKey]);

  if (!text.trim()) {
    return null;
  }

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(artifactKey);
    } catch {
      // clipboard write failed; no visible feedback shown
    }
  }

  return (
    <button type="button" className="ghost-button" onClick={handleCopy}>
      {copiedKey === artifactKey ? "Copied" : "Copy text"}
    </button>
  );
}

function AdminArtifactSection({
  artifactKey,
  isOpen,
  onToggle,
  kicker,
  title,
  summary,
  description,
  text,
  filename,
}: {
  artifactKey: string;
  isOpen: boolean;
  onToggle: () => void;
  kicker: string;
  title: string;
  summary: string;
  description?: string;
  text: string;
  filename?: string;
}) {
  return (
    <section className={`accordion-item ${isOpen ? "accordion-item-open" : ""}`}>
      <button type="button" className="accordion-trigger" onClick={onToggle} aria-expanded={isOpen}>
        <div className="accordion-trigger-copy">
          <p className="kicker">{kicker}</p>
          <h3>{title}</h3>
          <p className="muted accordion-summary">{summary}</p>
        </div>
        <span className="accordion-chevron" aria-hidden="true">
          {isOpen ? "-" : "+"}
        </span>
      </button>
      {isOpen ? (
        <div className="accordion-panel">
          {description ? <p className="muted">{description}</p> : null}
          {filename ? (
            <ArtifactActions artifactKey={artifactKey} text={text} filename={filename} />
          ) : null}
          <pre className="code-block">{text}</pre>
        </div>
      ) : null}
    </section>
  );
}

export function PlanViewer({
  plan,
  accessToken,
  viewerRole,
  onPlanUpdated,
  onPlanDeleted,
}: {
  plan: PlanDetail;
  accessToken: string | null;
  viewerRole: UserRole;
  onPlanUpdated?: (plan: PlanDetail) => void;
  onPlanDeleted?: () => Promise<void> | void;
}) {
  const router = useRouter();
  const canUseAdminOutputs = canUseAdminPlanControls(viewerRole, Boolean(plan.admin_outputs));
  const isViewerAdmin = isAdminRole(viewerRole);
  const canManagePlan = viewerRole === "admin" || viewerRole === "athlete";
  // Only surface an advisory that carries a real injury-risk band; the rest just
  // restate load tweaks the plan already applied, so they are suppressed.
  const primaryAdvisory = selectInjuryRiskAdvisory(plan.advisories);

  const athletePlanText = plan.outputs.plan_text.trim();
  const hasPublishedPlan = isPlanReleasedToAthlete(plan);
  const hasStructuredAthletePlan =
    shouldRenderStructuredPlan(plan.outputs) && Boolean(plan.outputs.structured_plan);

  const injuryTriage = readInjuryTriage(plan);
  const rawTriageMode = readRawTriageMode(plan);
  const hasResumeApproval = hasTriageResumeApproval(plan);
  const isTriageBlocked = shouldShowTriageBlockedState(
    plan,
    injuryTriage?.mode || rawTriageMode || undefined,
  );
  
  const blockedTitle =
    injuryTriage?.mode === "medical_hold"
      ? "Medical hold"
      : injuryTriage?.mode === "restricted_rehab_only"
        ? "Clearance required"
        : "Planning paused";

  const statusLabel = isTriageBlocked
    ? blockedTitle
    : titleizeToken(plan.status || "generated");

  const stage2Status = isTriageBlocked
    ? "Stage 2 skipped intentionally"
    : titleizeToken(plan.admin_outputs?.stage2_status || "legacy");

  const heroSummary = isTriageBlocked
    ? injuryTriage?.mode === "medical_hold"
      ? "The planner intentionally blocked this intake before finalization because it contains urgent or medically disqualifying signals."
      : "The planner intentionally paused normal release because this intake contains structural injury signals that require clearance."
    : hasPublishedPlan
      ? "This is the validated athlete-facing plan now stored in the app."
      : "This plan is held back from the athlete view until Stage 2 clears review.";

  const handoffText = plan.admin_outputs?.stage2_handoff_text || "";
  const retryText = plan.admin_outputs?.stage2_retry_text || "";
  const draftText = plan.admin_outputs?.draft_plan_text || "No Stage 1 draft.";
  const latestStage2Text = plan.admin_outputs?.final_plan_text || "No Stage 2 output.";
  const coachNotesText = plan.admin_outputs?.coach_notes || "No internal notes.";
  const validatorText = formatStructuredValue(
    plan.admin_outputs?.stage2_validator_report,
    "No validator report.",
  );
  const validatorReport =
    plan.admin_outputs?.stage2_validator_report &&
    typeof plan.admin_outputs.stage2_validator_report === "object"
      ? plan.admin_outputs.stage2_validator_report
      : {};
  const containsBlockedTriageStub = hasBlockedTriageStubText(
    plan.admin_outputs?.final_plan_text,
    plan.admin_outputs?.draft_plan_text,
  );
  const isProtectedTriageResumePending = isProtectedTriageResumePendingState({
    isTriageBlocked,
    stage2Status: plan.admin_outputs?.stage2_status,
    containsBlockedTriageStub,
    athletePlanText,
    finalPlanText: plan.admin_outputs?.final_plan_text,
  });
  const stage2ReviewSummary = buildReviewSummary(
    validatorReport,
    plan.admin_outputs?.stage2_status || "",
    { hasBlockedTriageStubText: containsBlockedTriageStub },
  );
  const planningBriefText = formatStructuredValue(
    plan.admin_outputs?.planning_brief,
    "No planning brief.",
  );
  const payloadText = formatStructuredValue(
    plan.admin_outputs?.stage2_payload,
    "No Stage 2 payload.",
  );
  const reviewPlanText = (plan.admin_outputs?.final_plan_text || "").trim();
  const approvableText =
    plan.admin_outputs?.final_plan_text?.trim() ||
    plan.admin_outputs?.draft_plan_text?.trim() ||
    athletePlanText ||
    "";
  const canApproveForRelease =
    canUseAdminOutputs && !hasPublishedPlan && Boolean(approvableText) && !isProtectedTriageResumePending;
  const canRetryResumeGeneration = canRetryResumeGenerationForPlan({
    isAdmin: canUseAdminOutputs,
    isProtectedTriageResumePending,
    injuryTriageMode: injuryTriage?.mode,
    rawTriageMode,
    planStatus: plan.status,
  });

  const showProtectedResumeAdminReview = shouldShowProtectedResumeAdminReview({
    isTriageBlocked,
    isProtectedTriageResumePending,
    hasResumeApproval,
  });
  
  const canRejectApproval = canUseAdminOutputs;
  const blockedInjuryContext = injuryTriage
    ? buildBlockedInjuryContextSummary({
        triage: injuryTriage,
        injuriesText: plan.latest_intake?.injuries,
        guidedInjuries: [plan.latest_intake?.guided_injury, ...(plan.latest_intake?.guided_injuries ?? [])].filter(
          (injury): injury is { area?: string; notes?: string } => Boolean(injury),
        ),
      })
    : null;
  const approveButtonLabel = stage2ReviewSummary.isPublishable
    ? "Approve for athlete view"
    : "Approve anyway";
  const reviewPanelClassName = `support-panel stage2-review-panel ${
    stage2ReviewSummary.isPublishable ? "" : "support-panel-alert"
  }`.trim();
  const approvalSourceLabel = plan.admin_outputs?.final_plan_text?.trim()
    ? "saved Stage 2 final output"
    : plan.admin_outputs?.draft_plan_text?.trim()
      ? "saved Stage 1 draft"
      : "current plan text";

  const [manualPlanText, setManualPlanText] = useState(plan.admin_outputs?.final_plan_text || "");
  const [manualSubmitPending, setManualSubmitPending] = useState(false);
  const [manualSubmitMessage, setManualSubmitMessage] = useState<string | null>(null);
  const [manualSubmitError, setManualSubmitError] = useState<string | null>(null);
  const [approvePending, setApprovePending] = useState(false);
  const [approveMessage, setApproveMessage] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [resumeReason, setResumeReason] = useState("");
  const [resumePending, setResumePending] = useState(false);
  const [resumeMessage, setResumeMessage] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [rejectPending, setRejectPending] = useState(false);
  const [rejectMessage, setRejectMessage] = useState<string | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [archivePending, setArchivePending] = useState(false);
  const [archiveMessage, setArchiveMessage] = useState<string | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [activePlanId, setActivePlanId] = useState<string | null>(null);
  const [setActivePending, setSetActivePending] = useState(false);
  const [setActiveError, setSetActiveError] = useState<string | null>(null);
  const [planActionPending, setPlanActionPending] = useState<
    "rename" | "archive" | "permanent-delete" | null
  >(null);
  const [planActionMessage, setPlanActionMessage] = useState<string | null>(null);
  const [planActionError, setPlanActionError] = useState<string | null>(null);
  // Plans whose background structured-card poll window has elapsed. We stop
  // polling for these and drop the "enhancing" hint; the template card stays as
  // the final view (no fallback/error notice).
  const [pollExpiredPlans, setPollExpiredPlans] = useState<Record<string, boolean>>({});
  const [stage2RetryInProgress, setStage2RetryInProgress] = useState(false);
  const [stage2RetryJustCompleted, setStage2RetryJustCompleted] = useState<"passed" | "failed" | null>(
    null,
  );
  const [openAdminSection, setOpenAdminSection] = useState(() => {
    if (retryText.trim()) {
      return "retry";
    }
    if ((plan.admin_outputs?.final_plan_text || "").trim()) {
      return "final";
    }
    if (handoffText.trim()) {
      return "handoff";
    }
    return "draft";
  });
  const generationController = useGenerationController({
    token: accessToken,
    storageKey: `unlxck:pending-generation:triage-resume:${plan.plan_id}`,
    createJob: async (clientRequestId) => {
      if (!accessToken) {
        throw new Error("Admin session missing. Please sign in again.");
      }
      return approveAndResumeGeneration(
        accessToken,
        plan.plan_id,
        { reason: resumeReason.trim() },
        clientRequestId,
      );
    },
    onComplete: async ({ planId }) => {
      if (!accessToken) {
        return;
      }

      const resolvedPlanId = planId || plan.plan_id;
      let refreshedPlan = await getPlan(accessToken, resolvedPlanId);

      for (let attempt = 1; attempt < TRIAGE_RESUME_FETCH_ATTEMPTS; attempt += 1) {
        const stillBlocked =
          refreshedPlan.status === "triage_blocked" ||
          refreshedPlan.admin_outputs?.stage2_status === "triage_blocked";
        if (!stillBlocked) {
          break;
        }
        await sleep(TRIAGE_RESUME_FETCH_DELAY_MS * attempt);
        try {
          refreshedPlan = await getPlan(accessToken, resolvedPlanId);
        } catch {
          // Ignore transient fetch failures during the polling window
        }
      }

      onPlanUpdated?.(refreshedPlan);
      setResumeMessage("Approved and resumed successfully.");
      router.refresh();
    },
  });
  const structuredPlanPollExpired = Boolean(pollExpiredPlans[plan.plan_id]);
  const isRecentPlan = isRecentlyCreatedPlan(plan);
  // True while the template card is up and we're still polling for the richer
  // structured card to land. Drives the lightweight "enhancing" hint and the
  // background poll; never holds back the plan content.
  const isAwaitingStructuredUpgrade = shouldAwaitStructuredPlanUpgrade({
    hasPublishedPlan,
    hasStructuredPlan: hasStructuredAthletePlan,
    pollWindowExpired: structuredPlanPollExpired,
    hasAccessToken: Boolean(accessToken),
    isRecentPlan,
    isTriageBlocked,
  });
  // Admin-only: why this published plan is still on the plan_text fallback. Only
  // shown once we are no longer expecting a live upgrade, so a card that is still
  // building does not flash a stale rejection reason.
  const structuredCardDebug = isAwaitingStructuredUpgrade ? null : readStructuredCardDebug(plan);

  useEffect(() => {
    setManualPlanText(plan.admin_outputs?.final_plan_text || "");
  }, [plan.plan_id, plan.admin_outputs?.final_plan_text]);

  // Resolve which plan is the athlete's active one so this page can show the
  // ACTIVE badge / Set active control without duplicating Today's job. A missing
  // active plan is a normal state (no plan set yet), so failures stay silent.
  useEffect(() => {
    if (!accessToken || !canManagePlan) {
      return;
    }
    let cancelled = false;
    getActivePlan(accessToken)
      .then((active) => {
        if (!cancelled) {
          setActivePlanId(active?.plan_id ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setActivePlanId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, canManagePlan, plan.plan_id]);

  useEffect(() => {
    setOpenAdminSection(
      retryText.trim()
        ? "retry"
        : (plan.admin_outputs?.final_plan_text || "").trim()
          ? "final"
          : handoffText.trim()
            ? "handoff"
            : "draft",
    );
  }, [plan.plan_id, handoffText, retryText, plan.admin_outputs?.final_plan_text]);

  // Background upgrade poll: the template card is already on screen, so this just
  // watches for the richer structured card to finish building server-side and
  // swaps it in. It never blocks the view; when the poll window elapses we simply
  // stop and leave the template card in place. Runs for any open published plan
  // still missing its card (not only recent ones) so an older plan whose card
  // lands later upgrades without a manual reload; the window below bounds the cost.
  useEffect(() => {
    if (
      !shouldPollForStructuredPlanUpgrade({
        hasPublishedPlan,
        hasStructuredPlan: hasStructuredAthletePlan,
        pollWindowExpired: structuredPlanPollExpired,
        hasAccessToken: Boolean(accessToken),
        isTriageBlocked,
      })
    ) {
      return;
    }

    let cancelled = false;

    const pollForStructuredPlan = async () => {
      if (!accessToken) {
        return;
      }
      try {
        const refreshedPlan = await getPlan(accessToken, plan.plan_id);
        // Only swap the view once the actual structured card exists — mirror the
        // exact gate the renderer uses (hasStructuredAthletePlan) so we never call
        // onPlanUpdated for a refresh that would still fall back to plan_text.
        if (
          !cancelled &&
          shouldRenderStructuredPlan(refreshedPlan.outputs) &&
          Boolean(refreshedPlan.outputs.structured_plan)
        ) {
          onPlanUpdated?.(refreshedPlan);
        }
      } catch {
        // Transient fetch failure — the template card stays up and the next tick
        // retries until the structured card lands or the poll window elapses.
      }
    };

    const intervalId = window.setInterval(pollForStructuredPlan, STRUCTURED_PLAN_POLL_INTERVAL_MS);
    const timeoutId = window.setTimeout(() => {
      if (!cancelled) {
        setPollExpiredPlans((prev) => ({ ...prev, [plan.plan_id]: true }));
      }
    }, STRUCTURED_PLAN_UPGRADE_POLL_WINDOW_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [
    accessToken,
    hasPublishedPlan,
    hasStructuredAthletePlan,
    isTriageBlocked,
    onPlanUpdated,
    plan.plan_id,
    structuredPlanPollExpired,
  ]);

  async function handleManualStage2Submit() {
    if (!accessToken) {
      setManualSubmitError("Admin session missing. Please sign in again.");
      return;
    }
    if (!manualPlanText.trim()) {
      setManualSubmitError("Paste the GPT final plan before submitting.");
      return;
    }

    setManualSubmitPending(true);
    setStage2RetryInProgress(true);
    setStage2RetryJustCompleted(null);
    setManualSubmitError(null);
    setManualSubmitMessage(null);

    try {
      const updatedPlan = await submitManualStage2(accessToken, plan.plan_id, {
        final_plan_text: manualPlanText,
      });
      const retryPassed = updatedPlan.status === "ready";
      setStage2RetryJustCompleted(retryPassed ? "passed" : "failed");
      onPlanUpdated?.(updatedPlan);
      setManualSubmitMessage(
        retryPassed
          ? "Manual Stage 2 output passed validation and is now published in the app."
          : "Manual Stage 2 output was saved, but it still needs revision. The retry prompt below is updated.",
      );
    } catch (error) {
      setStage2RetryJustCompleted(null);
      setManualSubmitError(
        error instanceof Error ? error.message : "Unable to submit manual Stage 2 output.",
      );
    } finally {
      setManualSubmitPending(false);
      setStage2RetryInProgress(false);
    }
  }

  async function handleApproveForRelease() {
    if (!accessToken) {
      setApproveError("Admin session missing. Please sign in again.");
      return;
    }
    if (!canApproveForRelease) {
      setApproveError("There is no saved draft or Stage 2 final text available to approve.");
      return;
    }

    setApprovePending(true);
    setApproveError(null);
    setApproveMessage(null);
    setRejectError(null);
    setRejectMessage(null);

    try {
      const updatedPlan = await approvePlanForRelease(accessToken, plan.plan_id);
      onPlanUpdated?.(updatedPlan);
      setApproveMessage(getApprovalSuccessMessage(updatedPlan));
    } catch (error) {
      // Approval persists server-side before any slow post-processing, so a
      // network/timeout failure is often a false negative: the plan may already
      // be released. Re-fetch a few times and treat a now-ready plan as success.
      const recoveredPlan = await resolveApprovalAfterError({
        error,
        fetchPlan: () => getPlan(accessToken, plan.plan_id),
      });
      if (recoveredPlan) {
        onPlanUpdated?.(recoveredPlan);
        setApproveMessage(getApprovalSuccessMessage(recoveredPlan));
        return;
      }
      setApproveError(
        error instanceof Error ? error.message : "Unable to approve this plan for athlete view.",
      );
    } finally {
      setApprovePending(false);
    }
  }

  async function handleApproveAndResumeGeneration() {
    if (!accessToken) {
      setResumeError("Admin session missing. Please sign in again.");
      return;
    }
    if (!canRetryResumeGeneration) {
      setResumeError("This plan cannot be resumed from its current triage state.");
      return;
    }
    if (!resumeReason.trim()) {
      setResumeError("Please enter a short reason before resuming generation.");
      return;
    }
    setResumePending(true);
    generationController.setError(null);
    setResumeError(null);
    setResumeMessage(null);
    try {
      await generationController.startGeneration();
      setResumeReason("");
    } catch (error) {
      setResumeError(error instanceof Error ? error.message : "Unable to approve and resume generation.");
    } finally {
      setResumePending(false);
    }
  }

  useEffect(() => {
    if (generationController.error) {
      setResumeError(generationController.error);
    }
  }, [generationController.error]);

  if (generationController.isGenerating || generationController.hasPendingGeneration) {
    return (
      <PremiumLoadingScreen
        phase={generationController.phase}
        error={generationController.error}
        statusMessage={generationController.statusMessage}
        startedAtMs={generationController.startedAtMs}
      />
    );
  }

  async function handleRejectApproval() {
    if (!accessToken) {
      setRejectError("Admin session missing. Please sign in again.");
      return;
    }

    setRejectPending(true);
    setRejectError(null);
    setRejectMessage(null);
    setApproveError(null);
    setApproveMessage(null);

    try {
      const updatedPlan = await rejectApprovedPlan(accessToken, plan.plan_id);
      onPlanUpdated?.(updatedPlan);
      setRejectMessage(hasPublishedPlan ? "Plan rejected and moved back to review." : "Plan rejected.");
    } catch (error) {
      setRejectError(error instanceof Error ? error.message : "Unable to reject this plan.");
    } finally {
      setRejectPending(false);
    }
  }

  async function handleSetActive() {
    if (!accessToken) {
      setSetActiveError("Session expired. Sign in again.");
      return;
    }
    if (!canSetActivePlan(plan.status)) {
      setSetActiveError("This plan cannot be set active from its current state.");
      return;
    }
    setSetActivePending(true);
    setSetActiveError(null);
    try {
      const active = await setActivePlan(accessToken, plan.plan_id);
      setActivePlanId(active.plan_id);
    } catch (error) {
      setSetActiveError(error instanceof Error ? error.message : "Unable to set this plan active.");
    } finally {
      setSetActivePending(false);
    }
  }

  async function handleArchivePlan() {
    if (!accessToken) {
      setArchiveError("Admin session missing. Please sign in again.");
      return;
    }

    const confirmed = window.confirm(`Archive "${getPlanDisplayName(plan)}"?`);
    if (!confirmed) {
      return;
    }

    setArchivePending(true);
    setArchiveError(null);
    setArchiveMessage(null);

    try {
      const updatedPlan = await archivePlan(accessToken, plan.plan_id);
      onPlanUpdated?.(updatedPlan);
      setArchiveMessage("Plan archived.");
    } catch (error) {
      setArchiveError(error instanceof Error ? error.message : "Unable to archive this plan.");
    } finally {
      setArchivePending(false);
    }
  }

  async function handleRenamePlan() {
    if (!accessToken) {
      setPlanActionError("Session expired. Sign in again.");
      return;
    }

    const currentName = plan.plan_name?.trim() || "";
    const nextName = window.prompt("Rename this plan", currentName || plan.fight_date || "");
    if (nextName == null) {
      return;
    }

    const normalizedName = nextName.trim();
    if (!normalizedName) {
      setPlanActionError("Plan name cannot be empty.");
      return;
    }

    setPlanActionPending("rename");
    setPlanActionError(null);
    setPlanActionMessage(null);

    try {
      const updatedPlan = await renamePlan(accessToken, plan.plan_id, normalizedName);
      onPlanUpdated?.(updatedPlan);
      setPlanActionMessage("Plan renamed.");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unable to rename this plan.";
      if (
        errorMessage.includes("Unable to reach the server") ||
        errorMessage.includes("502") ||
        errorMessage.includes("503") ||
        errorMessage.includes("504")
      ) {
        setPlanActionError("Connection issue. Try again in a minute.");
      } else {
        setPlanActionError(errorMessage);
      }
    } finally {
      setPlanActionPending(null);
    }
  }

  async function handleArchiveOwnPlan() {
    if (!accessToken) {
      setPlanActionError("Session expired. Sign in again.");
      return;
    }

    const confirmed = window.confirm(`Archive "${getPlanDisplayName(plan)}"?`);
    if (!confirmed) {
      return;
    }

    setPlanActionPending("archive");
    setPlanActionError(null);
    setPlanActionMessage(null);

    try {
      await deletePlan(accessToken, plan.plan_id);
      clearCompletedGenerationForDeletedPlan(plan.plan_id);
      await onPlanDeleted?.();
      router.push(viewerRole === "admin" ? "/admin" : "/plans");
      router.refresh();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unable to archive this plan.";
      if (
        errorMessage.includes("Unable to reach the server") ||
        errorMessage.includes("502") ||
        errorMessage.includes("503") ||
        errorMessage.includes("504")
      ) {
        setPlanActionError("Connection issue. Try again in a minute.");
      } else {
        setPlanActionError(errorMessage);
      }
    } finally {
      setPlanActionPending(null);
    }
  }

  async function handlePermanentDelete() {
    if (!accessToken) {
      setPlanActionError("Session expired. Sign in again.");
      return;
    }

    const planName = plan.plan_name?.trim() ?? "";
    const isArchived = (plan.status || "").trim().toLowerCase() === "archived";

    // Archived plans are already retired, so skip the type-the-name confirmation
    // and use a single confirm. Live plans still require typing the name.
    if (isArchived) {
      const confirmed = window.confirm(
        `Permanently delete "${getPlanDisplayName(plan)}"? This cannot be undone.`,
      );
      if (!confirmed) {
        return;
      }
    } else {
      if (!planName) {
        setPlanActionError("This plan has no name. Rename it before permanent deletion.");
        return;
      }

      const typed = window.prompt(
        `Permanent delete cannot be undone.\n\nType the plan name to confirm:\n${planName}`,
      );
      if (typed == null) {
        return;
      }
      if (typed.trim() !== planName) {
        setPlanActionError("Confirmation did not match the plan name. Nothing was deleted.");
        return;
      }
    }

    setPlanActionPending("permanent-delete");
    setPlanActionError(null);
    setPlanActionMessage(null);

    try {
      await permanentlyDeletePlan(accessToken, plan.plan_id, isArchived ? undefined : planName);
      clearCompletedGenerationForDeletedPlan(plan.plan_id);
      await onPlanDeleted?.();
      router.push("/admin");
      router.refresh();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unable to delete this plan.";
      if (
        errorMessage.includes("Unable to reach the server") ||
        errorMessage.includes("502") ||
        errorMessage.includes("503") ||
        errorMessage.includes("504")
      ) {
        setPlanActionError("Connection issue. Try again in a minute.");
      } else {
        setPlanActionError(errorMessage);
      }
    } finally {
      setPlanActionPending(null);
    }
  }

  const adminSections = [
    {
      artifactKey: "draft",
      kicker: "Stage 1",
      title: "Draft plan",
      summary: "Original planner output before the final Stage 2 rewrite.",
      text: draftText,
    },
    {
      artifactKey: "final",
      kicker: "Stage 2",
      title: "Latest model output",
      summary: "Most recent saved Stage 2 plan text.",
      text: latestStage2Text,
    },
    {
      artifactKey: "internal-notes",
      kicker: "Internal Notes",
      title: "Coach/internal output",
      summary: "Internal notes saved alongside the current plan.",
      text: coachNotesText,
    },
    {
      artifactKey: "validator",
      kicker: "Validator",
      title: "Latest review report",
      summary: "Structured validator report from the last Stage 2 review.",
      text: validatorText,
    },
    {
      artifactKey: "brief",
      kicker: "Stage 2 Brief",
      title: "Planning brief",
      summary: "Structured brief that Stage 2 used as its planning authority.",
      text: planningBriefText,
    },
    {
      artifactKey: "handoff",
      kicker: "Handoff",
      title: "Stage 2 handoff",
      summary: "Exact handoff prompt generated by the app for manual GPT runs.",
      description:
        "Use this if you want to run a manual Stage 2 pass with the configured finalizer model using the same handoff the app stored.",
      text: handoffText || "No handoff text.",
      filename: buildArtifactFilename(plan, "stage2-handoff"),
    },
    {
      artifactKey: "retry",
      kicker: "Retry",
      title: "Repair prompt",
      summary: "Exact retry prompt to use when the last Stage 2 attempt needs revision.",
      description: "Use this when the validator asked for one more manual repair pass.",
      text: retryText || "No retry prompt.",
      filename: buildArtifactFilename(plan, "stage2-retry"),
    },
    {
      artifactKey: "payload",
      kicker: "Payload",
      title: "Stage 2 package",
      summary: "Internal Stage 2 payload captured for audit and debugging.",
      text: payloadText,
    },
  ];

  return (
    <div className="page">
      <section className="panel">
        <QuickBuildRefinementBanner planId={plan.plan_id} planSource={plan.plan_source ?? null} />
        <div className="section-heading">
          <div>
            <p className="kicker">Plan Detail</p>
            <h1>{getPlanDisplayName(plan)}</h1>
            <p className="muted">{heroSummary}</p>
          </div>
          <div className="status-card">
            <p className="status-label">Status</p>
            <h2 className="plan-summary-title">
              {statusLabel}
              {activePlanId === plan.plan_id ? (
                <span className="badge status-badge-success cm-active-badge">ACTIVE</span>
              ) : null}
            </h2>
            <p className="muted">
              {isTriageBlocked
                ? "Stage 2 was skipped intentionally."
                : `Created ${new Date(plan.created_at).toLocaleString()}`}
            </p>
          </div>
        </div>

        {(plan.status || "").trim().toLowerCase() === "archived" ? (
          <div className="quick-build-refine-banner cm-archived-banner" role="status">
            This plan is archived — view only. Restore it from plan history to set it active again.
          </div>
        ) : null}

        <div className="plan-summary-actions">
          <Link href="/plans" className="ghost-button">
            Back to plans
          </Link>
          {canManagePlan && activePlanId === plan.plan_id ? (
            <Link href="/today" className="cta">
              Open Today
            </Link>
          ) : null}
          {canManagePlan && activePlanId !== plan.plan_id && canSetActivePlan(plan.status) ? (
            <button
              type="button"
              className="cta"
              onClick={handleSetActive}
              disabled={setActivePending}
            >
              {setActivePending ? "Setting active..." : "Set active"}
            </button>
          ) : null}
          {canManagePlan ? (
            <>
              <button
                type="button"
                className="ghost-button"
                onClick={handleRenamePlan}
                disabled={planActionPending !== null}
              >
                {planActionPending === "rename" ? "Renaming..." : "Rename"}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={handleArchiveOwnPlan}
                disabled={planActionPending !== null}
              >
                {planActionPending === "archive" ? "Archiving..." : "Archive"}
              </button>
            </>
          ) : null}
          {isViewerAdmin ? (
            <button
              type="button"
              className="ghost-button danger-button"
              onClick={handlePermanentDelete}
              disabled={planActionPending !== null}
            >
              {planActionPending === "permanent-delete" ? "Deleting..." : "Permanent delete"}
            </button>
          ) : null}
          {isViewerAdmin && plan.athlete_id ? (
            <Link href={`/admin/athletes/${plan.athlete_id}`} className="ghost-button">
              View athlete profile
            </Link>
          ) : null}
        </div>
        {planActionMessage ? <div className="success-banner">{planActionMessage}</div> : null}
        {planActionError ? <div className="error-banner">{planActionError}</div> : null}
        {setActiveError ? <div className="error-banner">{setActiveError}</div> : null}
      </section>

      <div className={`plan-detail-layout${canUseAdminOutputs ? "" : " plan-detail-layout-single"}`}>
        {canUseAdminOutputs ? (
          <aside className="plan-summary-stack">
            <section className="plan-summary-card">
              <div className="plan-summary-header">
                <p className="kicker">Stage 2</p>
                <h2 className="plan-summary-title">Automation status</h2>
              </div>
              <div className="plan-meta-grid">
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Stage 2 status</p>
                  <p className="plan-meta-value">{stage2Status}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Attempts</p>
                  <p className="plan-meta-value">{plan.admin_outputs?.stage2_attempt_count || 0}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Release state</p>
                  <p className="plan-meta-value">
                    {isTriageBlocked
                      ? injuryTriage?.mode === "medical_hold"
                        ? "Blocked"
                        : "Protected"
                      : isProtectedTriageResumePending
                        ? "Blocked / resume pending"
                      : stage2ReviewSummary.isPublishable
                        ? "Ready"
                        : "Held"}
                  </p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Blocking issues</p>
                  <p className="plan-meta-value">
                    {isTriageBlocked
                      ? "—"
                      : stage2ReviewSummary.errors.length + stage2ReviewSummary.blockingCount}
                  </p>
                </article>
              </div>
              {handoffText.trim() ? (
                <>
                  <p className="muted">
                    The exact Stage 2 handoff is already saved for this plan, so you can run a manual Stage 2 pass quickly if you want.
                  </p>
                  <ArtifactActions
                    artifactKey="stage2_handoff_text"
                    text={handoffText}
                    filename={buildArtifactFilename(plan, "stage2-handoff")}
                  />
                </>
              ) : null}
              {retryText.trim() ? (
                <>
                  <p className="muted">A repair prompt is also ready if you want to run the retry step manually.</p>
                  <ArtifactActions
                    artifactKey="stage2_retry_text"
                    text={retryText}
                    filename={buildArtifactFilename(plan, "stage2-retry")}
                  />
                </>
              ) : null}
            </section>
          </aside>
        ) : null}

        <section className="plan-text-panel">
          {/* The validation status/badge is operational metadata. Athletes go
              straight into the camp map (which carries its own header); admins
              and any not-yet-published/triage state still see the status. */}
          {canUseAdminOutputs || !hasPublishedPlan || isTriageBlocked ? (
            <div className="plan-header-row">
              <div>
                <p className="kicker">{canUseAdminOutputs ? "Athlete Plan" : "Your plan"}</p>
                <h2>
                  {isTriageBlocked
                    ? blockedTitle
                    : plan.admin_outputs?.stage2_status === "triage_resume_approved"
                      ? "Resume approved — regeneration pending"
                    : hasPublishedPlan
                      ? "Validated final plan"
                      : "Pending finalization"}
                </h2>
              </div>
              <span
                className={`badge ${
                  isTriageBlocked
                    ? injuryTriage?.mode === "medical_hold"
                      ? "issue-badge-error"
                      : ""
                    : hasPublishedPlan
                      ? "status-badge-success"
                      : "status-badge-neutral"
                }`}
              >
                {isTriageBlocked
                  ? blockedTitle
                  : plan.admin_outputs?.stage2_status === "triage_resume_approved"
                    ? "Resume pending"
                  : hasPublishedPlan
                    ? "Validated"
                    : "Review required"}
              </span>
            </div>
          ) : null}

          {primaryAdvisory ? <SparringAdvisoryCard advisory={primaryAdvisory} /> : null}

          {isTriageBlocked && injuryTriage ? (
            <BlockedPlanDecisionCard
              triage={injuryTriage}
              injuryContext={blockedInjuryContext}
              isAdmin={isViewerAdmin}
            />
          ) : hasPublishedPlan ? (
            <>
              <div className="plan-summary-actions">
                <QuickCopyButton text={athletePlanText} artifactKey="athlete-plan" />
                {canRejectApproval ? (
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={handleRejectApproval}
                    disabled={rejectPending}
                  >
                    {rejectPending ? "Rejecting..." : "Reject approval"}
                  </button>
                ) : null}
                {canUseAdminOutputs ? (
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={handleArchivePlan}
                    disabled={archivePending}
                  >
                    {archivePending ? "Archiving..." : "Archive"}
                  </button>
                ) : null}
              </div>
              {hasStructuredAthletePlan && plan.outputs.structured_plan ? (
                <StructuredPlanRenderer plan={plan.outputs.structured_plan} />
              ) : (
                <>
                  {isAwaitingStructuredUpgrade ? <StructuredPlanUpgradingNotice /> : null}
                  {canUseAdminOutputs && structuredCardDebug ? (
                    <StructuredCardDiagnostic debug={structuredCardDebug} />
                  ) : null}
                  <PlanTextCards text={athletePlanText} />
                </>
              )}
              {rejectMessage ? <div className="success-banner">{rejectMessage}</div> : null}
              {rejectError ? <div className="error-banner">{rejectError}</div> : null}
              {archiveMessage ? <div className="success-banner">{archiveMessage}</div> : null}
              {archiveError ? <div className="error-banner">{archiveError}</div> : null}
            </>
          ) : (
            <div className="plan-review-stack">
              {canUseAdminOutputs ? (
                <>
                  {stage2RetryInProgress ? (
                    <section className="support-panel stage2-retry-banner stage2-retry-in-progress">
                      <div className="form-section-header">
                        <p className="kicker">Stage 2 Retry</p>
                        <h3>Retry in progress</h3>
                      </div>
                      <p className="muted">
                        Validating the submitted plan now. The validator results below are from the previous attempt and will be replaced when this retry completes.
                      </p>
                    </section>
                  ) : null}

                  {stage2RetryJustCompleted ? (
                    <section
                      className={`support-panel stage2-retry-banner ${
                        stage2RetryJustCompleted === "passed"
                          ? "stage2-retry-passed"
                          : "stage2-retry-failed"
                      }`}
                    >
                      <div className="form-section-header">
                        <p className="kicker">
                          Stage 2 Retry — Attempt {plan.admin_outputs?.stage2_attempt_count || 1}
                        </p>
                        <h3>
                          {stage2RetryJustCompleted === "passed"
                            ? "Retry passed — plan published"
                            : "Retry completed — new validation results below"}
                        </h3>
                      </div>
                      <p className="muted">
                        {stage2RetryJustCompleted === "passed"
                          ? "The submitted plan passed validation and has been published to the athlete view."
                          : "The submitted plan was validated. Hard blockers below reflect this latest attempt."}
                      </p>
                    </section>
                  ) : null}

                  <section
                    className={`${reviewPanelClassName}${
                      stage2RetryInProgress ? " stage2-review-panel-stale" : ""
                    }`}
                  >
                    <div className="form-section-header">
                      <p className="kicker">
                        Stage 2 review
                        {plan.admin_outputs?.stage2_attempt_count
                          ? ` — attempt ${plan.admin_outputs.stage2_attempt_count}`
                          : ""}
                        {stage2RetryInProgress ? " (previous attempt)" : ""}
                      </p>
                      <h3>
                        {stage2ReviewSummary.isPublishable
                          ? "Release decision"
                          : "Why this plan is being held"}
                      </h3>
                    </div>

                    <div className="stage2-review-state-row">
                      <span
                        className={`badge ${
                          stage2ReviewSummary.isPublishable
                            ? "status-badge-success"
                            : "issue-badge-error"
                        }`}
                      >
                        {stage2ReviewSummary.isPublishable ? "Ready" : "Held"}
                      </span>
                      <span className="badge issue-badge-error">
                        {stage2ReviewSummary.errors.length + stage2ReviewSummary.blockingCount} blockers
                      </span>
                    </div>

                    <p className="review-summary-text">{stage2ReviewSummary.headline}</p>
                    <p className="muted">{stage2ReviewSummary.guidance}</p>

                    {reviewPlanText ? (
                      <div className="plan-summary-actions">
                        <QuickCopyButton text={reviewPlanText} artifactKey="review-stage2" />
                      </div>
                    ) : null}

                    {stage2ReviewSummary.hasIssues ? (
                      <div className="review-issue-groups">
                        {stage2ReviewSummary.errors.length || stage2ReviewSummary.blocking.length ? (
                          <section className="review-issue-group">
                            <div className="review-issue-group-header">
                              <p className="review-issue-group-title">Blocking issues</p>
                              <span className="badge issue-badge-error">
                                {stage2ReviewSummary.errors.length + stage2ReviewSummary.blockingCount}
                              </span>
                            </div>
                            <div className="review-issue-list">
                              {stage2ReviewSummary.errors.map((issue, index) => (
                                <article key={`${issue.code}-${index}`} className="review-issue-item">
                                  <div className="review-issue-title-row">
                                    <p className="review-issue-title">{issue.title}</p>
                                    <span className="badge issue-badge-error">Error</span>
                                  </div>
                                  <p className="review-issue-message">{issue.message}</p>
                                  {issue.context ? (
                                    <p className="review-issue-context">{issue.context}</p>
                                  ) : null}
                                  {issue.snippet ? (
                                    <p className="review-issue-snippet">Line: {issue.snippet}</p>
                                  ) : null}
                                </article>
                              ))}
                              {stage2ReviewSummary.blocking.map((issue, index) => (
                                <article
                                  key={`${issue.code}-blocking-${index}`}
                                  className="review-issue-item"
                                >
                                  <div className="review-issue-title-row">
                                    <p className="review-issue-title">{issue.title}</p>
                                    <span className="badge issue-badge-error">Blocker</span>
                                  </div>
                                  <p className="review-issue-message">{issue.message}</p>
                                  {issue.context ? (
                                    <p className="review-issue-context">{issue.context}</p>
                                  ) : null}
                                  {issue.snippet ? (
                                    <p className="review-issue-snippet">Line: {issue.snippet}</p>
                                  ) : null}
                                </article>
                              ))}
                            </div>
                          </section>
                        ) : null}

                      </div>
                    ) : null}
                  </section>
                </>
              ) : null}

              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Publishing hold</p>
                  <h3>Plan not yet released</h3>
                </div>
                <p className="muted">
                  The automation flow generated a plan that still needs manual review before it can be shown to the athlete.
                </p>
                {canApproveForRelease ? (
                  <>
                    <p className="muted">
                      Current approval source: {approvalSourceLabel}.{" "}
                      {stage2ReviewSummary.isPublishable
                        ? "Blocking validation is already clear, so approval is just a release decision."
                        : "This plan still has blocking issues, so approval here is an explicit override."}
                    </p>
                    <div className="plan-summary-actions">
                      <button
                        type="button"
                        className={stage2ReviewSummary.isPublishable ? "cta" : "ghost-button"}
                        onClick={handleApproveForRelease}
                        disabled={approvePending}
                      >
                        {approvePending ? "Approving..." : approveButtonLabel}
                      </button>
                      {canUseAdminOutputs ? (
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={handleRejectApproval}
                          disabled={rejectPending}
                        >
                          {rejectPending ? "Rejecting..." : "Reject"}
                        </button>
                      ) : null}
                      {canUseAdminOutputs ? (
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={handleArchivePlan}
                          disabled={archivePending}
                        >
                          {archivePending ? "Archiving..." : "Archive"}
                        </button>
                      ) : null}
                    </div>
                  </>
                ) : null}
                {approveMessage ? <div className="success-banner">{approveMessage}</div> : null}
                {approveError ? <div className="error-banner">{approveError}</div> : null}
                {rejectMessage ? <div className="success-banner">{rejectMessage}</div> : null}
                {rejectError ? <div className="error-banner">{rejectError}</div> : null}
                {archiveMessage ? <div className="success-banner">{archiveMessage}</div> : null}
                {archiveError ? <div className="error-banner">{archiveError}</div> : null}
              </div>
            </div>
          )}
        </section>
      </div>

      {canUseAdminOutputs ? (
        <div id={`admin-review-${plan.plan_id}`} className="admin-review-stack">
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">ADMIN REVIEW</p>
              <h3>{getAdminReviewHeading({ showProtectedResumeAdminReview, hasResumeApproval })}</h3>
            </div>
            {showProtectedResumeAdminReview ? (
              <>
                <p className="muted">
                  {injuryTriage?.mode === "restricted_rehab_only"
                    ? "This intake requires clinician clearance before normal planning can resume. Stage 2 finalization was intentionally skipped."
                    : injuryTriage?.mode === "medical_hold"
                      ? "This intake contains urgent or medically disqualifying signals. No planning should continue until medical review is complete."
                      : "Normal planning is paused for this intake. Stage 2 was skipped intentionally until additional review is complete."}
                </p>
                {canRetryResumeGeneration ? (
                  <div className="support-panel support-panel-alert">
                    <div className="form-section-header">
                      <p className="kicker">Resume generation required</p>
                      <h3>{hasResumeApproval ? "Retry resume generation" : "Approve and resume generation"}</h3>
                    </div>
                
                    <p className="muted">
                      This protected triage plan cannot be approved for athlete release until admin resume generation completes and a real final plan replaces the triage stub.
                    </p>
                
                    <div className="field">
                      <label htmlFor="resume-generation-reason">Reason</label>
                      <input
                        id="resume-generation-reason"
                        type="text"
                        value={resumeReason}
                        onChange={(event) => setResumeReason(event.target.value)}
                        placeholder="Short reason"
                      />
                    </div>
                
                    <div className="plan-summary-actions">
                      <button
                        type="button"
                        className="cta"
                        onClick={handleApproveAndResumeGeneration}
                        disabled={resumePending}
                      >
                        {resumePending ? "Resuming..." : hasResumeApproval ? "Retry resume generation" : "Approve and resume generation"}
                      </button>
                    </div>
                
                    {resumeMessage ? <div className="success-banner">{resumeMessage}</div> : null}
                    {resumeError ? <div className="error-banner">{resumeError}</div> : null}
                  </div>
                ) : hasResumeApproval ? (
                  <div className="support-panel support-panel-alert">
                    <div className="form-section-header">
                      <p className="kicker">Resume unavailable</p>
                      <h3>This plan is not currently resumable</h3>
                    </div>
                    <p className="muted">
                      Resume was approved before, but this plan is not currently in a resumable triage mode. Medical holds or unresolved protected states must stay blocked until the intake is corrected or reviewed.
                    </p>
                    {resumeError ? <div className="error-banner">{resumeError}</div> : null}
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <p className="muted">
                  Paste a manual Stage 2 final plan here. The app will validate it, publish it if it passes, or refresh the retry prompt if it still needs work.
                </p>

                {canApproveForRelease ? (
                  <div className="support-panel">
                    <div className="form-section-header">
                      <p className="kicker">Quick approval</p>
                      <h3>Release the current saved plan</h3>
                    </div>
                    <p className="muted">
                      If the current saved version is good enough, approve it directly for athlete view without rerunning Stage 2. Source: {approvalSourceLabel}.
                    </p>
                    <div className="plan-summary-actions">
                      <button
                        type="button"
                        className={stage2ReviewSummary.isPublishable ? "cta" : "ghost-button"}
                        onClick={handleApproveForRelease}
                        disabled={approvePending}
                      >
                        {approvePending ? "Approving..." : approveButtonLabel}
                      </button>
                    </div>
                  </div>
                ) : null}

                {/* Approval/reject/archive feedback is rendered once, in the
                    primary "Publishing hold" panel above, to avoid showing the
                    same banner in two approval panels at the same time. */}

                <div className="field">
                  <label htmlFor="manual-stage2-final-plan">Final plan text</label>
                  <textarea
                    id="manual-stage2-final-plan"
                    rows={16}
                    value={manualPlanText}
                    onChange={(event) => setManualPlanText(event.target.value)}
                    placeholder="Paste the manual Stage 2 final plan here"
                  />
                </div>

                <div className="plan-summary-actions">
                  <button
                    type="button"
                    className="cta"
                    onClick={handleManualStage2Submit}
                    disabled={manualSubmitPending}
                  >
                    {manualSubmitPending ? "Submitting..." : "Validate and save"}
                  </button>
                </div>

                {manualSubmitMessage ? <div className="success-banner">{manualSubmitMessage}</div> : null}
                {manualSubmitError ? <div className="error-banner">{manualSubmitError}</div> : null}
              </>
            )}
          </section>

          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 2 internals</p>
              <h3>Open one artifact at a time</h3>
            </div>
            <p className="muted">
              Internal notes, planning artifacts, and validator details now stay collapsed until you open the one you need.
            </p>
            <div className="accordion-list">
              {adminSections.map((section) => (
                <AdminArtifactSection
                  key={section.artifactKey}
                  artifactKey={section.artifactKey}
                  isOpen={openAdminSection === section.artifactKey}
                  onToggle={() =>
                    setOpenAdminSection((current) =>
                      current === section.artifactKey ? "" : section.artifactKey,
                    )
                  }
                  kicker={section.kicker}
                  title={section.title}
                  summary={section.summary}
                  description={section.description}
                  text={section.text}
                  filename={section.filename}
                />
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
