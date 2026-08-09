"use client";

import { createContext, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import {
  classifySessionlessDay,
  cleanText,
  formatBlockLoad,
  formatCountdownLabel,
  formatEffort,
  formatMeasured,
  getBlocks,
  getBlockExecutionDisplay,
  getBlockAdjustmentDisplay,
  getActiveNotesExcludingRedFlags,
  getCoachLedContactView,
  getDays,
  getDisplayableRedFlags,
  getFallbackSafetyNotes,
  getRehabOrMobilityBlocks,
  isDeEmphasisedWeightCutSafety,
  planNoteLabel,
  formatSessionObjective,
  formatWeightCutBand,
  getDeterministicNutritionPhases,
  getDeterministicRecoveryPhases,
  getSessionCoachingLines,
  getSessions,
  getStringList,
  getWeeks,
  hasNutrition,
  normalizeSupportPhaseKey,
  nutritionPhaseRows,
  recoveryPhaseView,
  redFlagView,
  resolvedWeekPhase,
  selectBlockMetric,
  shouldShowRest,
  weekLabel,
  type SessionlessDayKind,
} from "@/lib/structured-plan";
import {
  buildCompletionIndex,
  canRetroLog,
  completionForSession,
  completionSessionId,
  dayCompletion,
  getSessionDisplayStatus,
  resolveNextPlanFocusDay,
  resolveOpenPlanWeekNumber,
  resolvePlanProgress,
  weekCompletion,
  weekSessionSummary,
  type Completion,
  type CompletionIndex,
  type SessionDisplayStatus,
} from "@/lib/camp-map";
import {
  OPEN_BLOCK_WEEK_LABELS,
  openBlockWeekDirective,
  openBlockWeekIntent,
  type OpenBlockWeekIntent,
} from "@/lib/open-block";
import {
  isRehabBlock,
  resolveBlockRehabLabel,
  resolveRehabSummaryLabel,
} from "@/lib/rehab-label";
import { useTrainingDay } from "@/lib/use-training-day";
import { describeRelativeDay, formatAppDate, formatAppDateRange } from "@/lib/date-format";
import { resolveFiniteWeekNumber } from "@/lib/plan-format";
import { formatPlanLabel } from "@/lib/plan-labels";
import { GlossaryTooltip } from "@/components/glossary-tooltip";
import { WhyTooltip } from "@/components/why-tooltip";
import { SafetyNote } from "@/components/safety-note";
import { PLAN_SAFETY_NOTE } from "@/lib/safety-copy";
import {
  applySourceSetRange,
  getSourcePrescriptionRangeOverrides,
  stripSafetyOwnedClause,
} from "@/lib/block-display-guardrails";
import type {
  DeterministicNutritionPhase,
  DeterministicRecoveryPhase,
  MindsetAnchor,
  PlanScheduleContext,
  RehabLabelPolicy,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
  TodaySessionCompletionRecord,
} from "@/lib/types";

/** Live logging info CampDayCard resolves per session and hands to SessionCard:
 * the display status (tone + label), the stored row (for RPE/reason lines) and
 * the retro-log hook when the session is still loggable. */
export type SessionCompletionInfo = {
  display: SessionDisplayStatus;
  completion?: TodaySessionCompletionRecord;
  onLog?: () => void;
};

const titleize = formatPlanLabel;

const DECLARED_LIGHT_COMBAT_TITLE = "Technical Combat";
const DECLARED_LIGHT_COMBAT_DESCRIPTION =
  "Pads, drills, movement or other lower-intensity combat work.";

function isDeclaredLightCombatTitle(title: string): boolean {
  return /\blight\s+(?:technical\s+)?combat\b/i.test(title);
}

// A sessionless contact day carries no app S&C. The note must match the day kind.
const HARD_SPARRING_SESSIONLESS_NOTE =
  "No extra S&C today — this is your declared hard-sparring/contact work. Keep freshness the priority.";
const TECHNICAL_COMBAT_TITLE = "Technical Combat";
const TECHNICAL_COMBAT_HELP =
  "Hard sparring is reduced close to competition to lower fatigue and injury risk while keeping timing and skills sharp.";
const TECHNICAL_COMBAT_TAG = "Low load";
const TECHNICAL_COMBAT_RATIONALE =
  "Technical only — no hard sparring. Stay sharp and leave fresh.";
const TECHNICAL_COMBAT_STAGE_RATIONALES: Record<string, string> = {
  "Fight-intensity technical rounds":
    "Realistic exchanges at speed, controlled contact, low total volume.",
  "Technical rhythm only":
    "Light technical rounds. Prioritise timing, flow and clean execution.",
  "Technical touch — pads / shadow":
    "Pads or shadow only. Stay sharp without contact fatigue.",
  "Technical activation — no contact":
    "Brief movement and reactions. Finish feeling fresher than you started.",
};

// Coach-owned contact that coexists with app work on the same day, keyed the same
// way so a technical-only contact block never reads as hard sparring.
const HARD_SPARRING_CONTACT_NOTE =
  "Your declared hard-sparring/contact work today, alongside the app work below. Keep freshness the priority.";

function blockCountLabel(count: number): string {
  return `${count} block${count === 1 ? "" : "s"}`;
}

function blockSummaryMetric(block: StructuredBlock): string | null {
  const metric = selectBlockMetric(block)[0]?.value;
  return metric || formatBlockLoad(block.load) || formatMeasured(block.duration);
}

function CollapsibleSection({
  title,
  detailLabel,
  defaultOpen,
  syncKey,
  className,
  children,
}: {
  title: string;
  detailLabel?: string;
  defaultOpen?: boolean;
  /** When provided and it CHANGES, the open state re-syncs to `defaultOpen`.
   * Used to make the support phase follow the selected week: a new week supplies
   * a new syncKey, so the matching phase opens and the others close, while a
   * manual toggle is preserved until the next week change. Omit to keep the
   * mount-only `defaultOpen` behaviour. */
  syncKey?: string | null;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  // Reset-on-key-change during render (React's recommended pattern): re-open to
  // the new default when the sync key changes, without an effect or a flash.
  const [prevSyncKey, setPrevSyncKey] = useState<string | null | undefined>(syncKey);
  if (syncKey !== undefined && syncKey !== prevSyncKey) {
    setPrevSyncKey(syncKey);
    setOpen(Boolean(defaultOpen));
  }
  const actionTarget = detailLabel || title;
  return (
    <details
      className={`sp-collapse${className ? ` ${className}` : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary">
        <span className="sp-collapse-title">{title}</span>
        <span className="sp-collapse-action">{open ? "Hide" : "Show"} {actionTarget}</span>
      </summary>
      <div className="sp-collapse-body">{children}</div>
    </details>
  );
}

/** Casefold + whitespace/trailing-punctuation normalise for equality checks, so
 * "Mobility and low-noise speed." matches "mobility and low-noise speed". */
function normalizeForDedupe(value: string | null | undefined): string | null {
  const clean = cleanText(value ?? null);
  if (!clean) {
    return null;
  }
  return clean.toLowerCase().replace(/\s+/g, " ").replace(/[.\s]+$/, "");
}

/**
 * Keep the saved planning rationale intact, but remove engine shorthand from
 * the athlete-facing card. Phase labels and timing rules are useful to the
 * generator and admin audit trail; an athlete needs the concise action or
 * rationale that remains after them.
 */
function athleteFacingRationale(value: string | null | undefined): string | null {
  const raw = cleanText(value);
  if (!raw) {
    return null;
  }

  const simplified = raw
    .replace(/^(?:GPP|SPP)(?:\s+|:\s*|[\u2014\u2013-]\s*)/i, "")
    .replace(
      /(?:^|\s)(?:from\s+)?D-\d+\+?\s*(?:onward|and beyond|or later|or closer)\b[^.!?]*(?:[.!?]|$)/gi,
      " ",
    )
    .replace(/\s+for\s+(?:a|an)\s+(?:[a-z-]+\s+){0,2}(?:brawler|boxer|fighter)\.?\s*$/i, ".")
    .replace(/\s{2,}/g, " ")
    .replace(/^[,;:\s]+/, "")
    .trim();

  return simplified ? simplified.charAt(0).toUpperCase() + simplified.slice(1) : null;
}

function TechnicalCombatRationale({ title }: { title?: string }) {
  const rationale =
    (title ? TECHNICAL_COMBAT_STAGE_RATIONALES[title] : undefined) || TECHNICAL_COMBAT_RATIONALE;
  return <p className="sp-today-note">{rationale}</p>;
}

function TechnicalCombatWhyTooltip() {
  return (
    <WhyTooltip
      title={TECHNICAL_COMBAT_TITLE}
      body={TECHNICAL_COMBAT_HELP}
      triggerLabel="?"
    />
  );
}

export function MindsetAnchorCard({
  anchor,
  dedupeContext,
}: {
  anchor?: MindsetAnchor | null;
  /** Text already shown next to this card (the session objective or day
   * description). A Context line that only restates it is dropped so the same
   * sentence never prints twice on one card. */
  dedupeContext?: string | (string | null | undefined)[] | null;
}) {
  const lines = getSessionCoachingLines(anchor).flatMap((line) => {
    const value = line.label === "Context" ? athleteFacingRationale(line.value) : line.value;
    return value ? [{ ...line, value }] : [];
  });
  const dedupeTargets = new Set(
    (Array.isArray(dedupeContext) ? dedupeContext : [dedupeContext])
      .map(normalizeForDedupe)
      .filter((text): text is string => text !== null),
  );
  const shown =
    dedupeTargets.size === 0
      ? lines
      : lines.filter(
          (line) => !(line.label === "Context" && dedupeTargets.has(normalizeForDedupe(line.value)!)),
        );
  if (shown.length === 0) {
    return null;
  }
  const renderLine = (line: { label: string; value: string }) => (
    <li key={line.label}>
      <span className="sp-coaching-label">{line.label}</span>
      <span>{line.value}</span>
    </li>
  );
  return (
    <div className="sp-coaching">
      <ul className="sp-coaching-list">{shown.map(renderLine)}</ul>
    </div>
  );
}

// Once the injury that seeded a plan's rehab work has cleared, that work is no
// longer rehabilitation — it is prophylactic (prehab). The decision is made per
// body region (see web/lib/rehab-label.ts) from the server-derived policy, which
// lives at the top of the render tree; this context relays it to the leaf cards
// that print the tag without drilling it through every intermediate day/session
// component. Null (no provider) keeps the unchanged "Rehab" wording.
const RehabLabelContext = createContext<RehabLabelPolicy | null>(null);
const PlanSourceTextContext = createContext<string | null>(null);
const PlanSafetyTextContext = createContext<string[]>([]);

/** Relays the Rehab/Prehab policy to the block cards below it. Standalone
 * surfaces that render SessionCard directly (Today) mount this themselves;
 * without it every rehab block keeps reading "Rehab". */
export function RehabLabelProvider({
  policy,
  children,
}: {
  policy?: RehabLabelPolicy | null;
  children: ReactNode;
}) {
  return <RehabLabelContext.Provider value={policy ?? null}>{children}</RehabLabelContext.Provider>;
}

/** Tag label for a block: "Rehab"/"Prehab" per live injury region, else the raw type. */
function blockTagLabel(block: StructuredBlock, policy: RehabLabelPolicy | null): string {
  if (isRehabBlock(block)) {
    return resolveBlockRehabLabel(block, policy);
  }
  return titleize(cleanText(block.block_type));
}

export function BlockCard({
  block,
  openWeekIntent,
  sourceCountdown,
}: {
  block: StructuredBlock;
  /** Development-block week intent of an open (renewable) plan. Adds the
   * week-directed instruction (progress / deload) to the card; dated camps
   * never pass it. */
  openWeekIntent?: OpenBlockWeekIntent | null;
  sourceCountdown?: string | null;
}) {
  const rehabLabelPolicy = useContext(RehabLabelContext);
  const sourceText = useContext(PlanSourceTextContext);
  const planSafetyTexts = useContext(PlanSafetyTextContext);
  const title = cleanText(block.display_name) || "Block";
  const sourceOverrides = getSourcePrescriptionRangeOverrides(sourceText, title, sourceCountdown);
  const blockType = cleanText(block.block_type);
  const load = formatBlockLoad(block.load);
  const metrics = applySourceSetRange(selectBlockMetric(block), sourceOverrides.sets);
  const work = formatMeasured(block.work);
  const rest = shouldShowRest(block.rest) ? formatMeasured(block.rest) : null;
  const effort = sourceOverrides.effort || formatEffort(block);
  // The effort card is glossed from the METHOD, not from the word "Effort":
  // EffortMethod covers RPE, RIR, intent, velocity, heart_rate_zone, pace and
  // max_effort_percent, so a fixed RPE definition would mis-explain "intent max"
  // as a 1-10 perceived-exertion score. An unrecognised or missing method falls
  // through to no tooltip rather than to a guess.
  const effortMethod = cleanText(block.effort?.method);
  const { cues, regressions, substitutions } = getBlockExecutionDisplay(block);
  const { progression, stopRules } = getBlockAdjustmentDisplay(block);
  const weekDirective = openBlockWeekDirective(openWeekIntent, block);
  // A week directive owns progression/deload programming for open plans, while
  // block stop criteria are safety instructions and must always remain visible.
  const showProgressionAside = Boolean(progression && !weekDirective);
  const compactStopRule = stopRules.map((rule) => rule.trim().replace(/^stop(?:\s+rule)?\s*:\s*/i, "").trim()).find(Boolean) || null;
  const adjustmentRules = [
    ...(showProgressionAside && progression
      ? [{ label: "Progress" as const, text: progression }]
      : []),
    ...(compactStopRule
      ? [{ label: "Stop rule" as const, text: compactStopRule }]
      : []),
  ];

  const tagLabel = blockType ? blockTagLabel(block, rehabLabelPolicy) : null;

  return (
    <div className="sp-block">
      <div className="sp-block-head">
        <span className="sp-block-title">{title}</span>
        {tagLabel ? (
          <span className="sp-tag">
            {tagLabel}
            {/* Silent for ordinary types (Strength, Conditioning); only the
                Rehab/Prehab/Mobility tags carry a definition. */}
            <GlossaryTooltip term={tagLabel} />
          </span>
        ) : null}
      </div>
      {metrics.length > 0 || work || load || rest || effort ? (
        <div className="sp-block-stats">
          {metrics.map((metric) => (
            <span key={metric.label} className="sp-stat">
              <span className="sp-stat-head">
                <span className="sp-stat-label">{metric.label}</span>
                {/* Volume and Mode are glossed; Duration/Distance/Rounds are
                    plain English and stay unadorned. */}
                <GlossaryTooltip term={metric.label} />
              </span>
              {metric.value}
            </span>
          ))}
          {work ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Work</span>
              {work}
            </span>
          ) : null}
          {load ? (
            <span className="sp-stat">
              <span className="sp-stat-head">
                <span className="sp-stat-label">Load</span>
                <GlossaryTooltip term="Load" />
              </span>
              {load}
            </span>
          ) : null}
          {rest ? (
            <span className="sp-stat">
              <span className="sp-stat-label">Rest</span>
              {rest}
            </span>
          ) : null}
          {effort ? (
            <span className="sp-stat">
              <span className="sp-stat-head">
                <span className="sp-stat-label">Effort</span>
                {/* The value reads "RPE 1.5" / "intent max" with no scale
                    attached, so the gloss explains whichever scale is in play. */}
                <GlossaryTooltip term={effortMethod} />
              </span>
              {effort}
            </span>
          ) : null}
        </div>
      ) : null}
      {weekDirective ? (
        <p className="sp-block-aside sp-week-directive">
          <span className="sp-stat-label">{weekDirective.label}</span>
          {weekDirective.text}
        </p>
      ) : null}
      {cues.length > 0 ? (
        <ul className="sp-cues">
          {cues.map((cue, index) => (
            <li key={`${cue}-${index}`}>{cue}</li>
          ))}
        </ul>
      ) : null}
      {substitutions.length > 0 ? (
        <p className="sp-block-aside">
          <span className="sp-stat-label">Swaps</span>
          {substitutions.join(", ")}
        </p>
      ) : null}
      {regressions.length > 0 ? (
        <p className="sp-block-aside">
          <span className="sp-stat-label">Easier</span>
          {regressions.join(", ")}
        </p>
      ) : null}
      {adjustmentRules.map((rule) => (
        <p key={`${rule.label}:${rule.text}`} className="sp-block-aside">
          <span className="sp-stat-label">{rule.label}</span>
          {/* "Stop rule" is glossed; "Progress" reads plainly on its own. */}
          <GlossaryTooltip term={rule.label} />
          {rule.text}
        </p>
      ))}
    </div>
  );
}

function RehabSummary({ blocks }: { blocks: StructuredBlock[] }) {
  const rehabLabelPolicy = useContext(RehabLabelContext);
  if (blocks.length === 0) {
    return null;
  }
  // Mixed sessions read as "Rehab": one live region is enough to keep the whole
  // list honest, even when the other entries have cleared into prehab. `blocks`
  // also carries mobility work, which the helper ignores.
  const summaryLabel = resolveRehabSummaryLabel(blocks, rehabLabelPolicy);
  return (
    <div className="sp-rehab-summary">
      <p className="sp-eyebrow">
        {summaryLabel} / Mobility
        <GlossaryTooltip term={summaryLabel} />
      </p>
      <ul className="sp-rehab-list">
        {blocks.map((block, index) => {
          const title = cleanText(block.display_name) || "Rehab block";
          const metric = blockSummaryMetric(block);
          return (
            <li key={cleanText(block.block_id) || `${title}-${index}`}>
              <span className="sp-rehab-title">{title}</span>
              {metric ? <span className="sp-rehab-metric">{metric}</span> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SessionCard({
  session,
  day,
  sourceCountdown,
  defaultOpenBlocks,
  showDayContext = true,
  showDayLabels = true,
  completionInfo,
  openWeekIntent,
}: {
  session: StructuredSession;
  day?: StructuredDay;
  /** Countdown used only to reconcile exact source prescription ranges. */
  sourceCountdown?: string | null;
  defaultOpenBlocks?: boolean;
  /** When false, day-level context like warnings/nutrition/mindset is rendered by
   * the parent day card instead, so the same information does not repeat inside
   * every session. */
  showDayContext?: boolean;
  /** When false, the countdown/date labels are omitted because the parent day
   * row already shows them (the plan accordion); standalone surfaces like the
   * Today tab keep the default. */
  showDayLabels?: boolean;
  /** Live logged status for this session (plan viewer only). Absent on
   * surfaces without completion data (e.g. the Today screen's embedded card). */
  completionInfo?: SessionCompletionInfo;
  /** Development-block week intent of an open (renewable) plan, forwarded to
   * every block card. */
  openWeekIntent?: OpenBlockWeekIntent | null;
}) {
  const detailsId = useId();
  const [showDetails, setShowDetails] = useState(Boolean(defaultOpenBlocks));
  const userToggledDetails = useRef(false);

  useEffect(() => {
    if (!userToggledDetails.current) {
      setShowDetails(Boolean(defaultOpenBlocks));
    }
  }, [defaultOpenBlocks]);

  const card = day?.today_card;
  const title =
    cleanText(session.title) ||
    cleanText(card?.headline) ||
    titleize(cleanText(session.session_type) || "Session");
  const isDeclaredLightCombat = isDeclaredLightCombatTitle(title);
  const isTechnicalSession = title === "Technical-only combat";
  const sessionType = cleanText(session.session_type);
  const objective = formatSessionObjective(session.objective);
  const duration = formatMeasured(session.planned_duration);
  const date = cleanText(day?.date);
  const countdown = formatCountdownLabel(day?.countdown_label);
  const warning = showDayContext ? cleanText(card?.primary_warning) : null;
  const nutrition = showDayContext ? cleanText(card?.nutrition_summary) : null;
  const weightCut = showDayContext ? cleanText(card?.weight_cut_warning) : null;
  const blocks = getBlocks(session);
  const rehabBlocks = getRehabOrMobilityBlocks(session);
  const blocksLabel = blockCountLabel(blocks.length);
  const sessionMindset =
    getSessionCoachingLines(session.mindset_anchor).length > 0
      ? session.mindset_anchor
      : showDayContext
        ? card?.mindset_anchor
        : undefined;

  return (
    <article className="sp-session">
      <header className="sp-session-head">
        <div>
          {showDayLabels && (countdown || date) ? (
            <div className="sp-day-labels sp-session-day-labels">
              {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
              {date ? <span className="sp-day-date">{formatAppDate(date)}</span> : null}
            </div>
          ) : null}
          <h3 className="sp-session-title">
            {isDeclaredLightCombat
              ? DECLARED_LIGHT_COMBAT_TITLE
              : isTechnicalSession
                ? TECHNICAL_COMBAT_TITLE
                : title}
            {isTechnicalSession ? <TechnicalCombatWhyTooltip /> : null}
          </h3>
          {/* The objective is the plan's "Why:" line, not a description of the
              work — the blocks below already carry that. Labelling it says so
              outright, so the reason for the session is impossible to miss. */}
          {isDeclaredLightCombat ? (
            <p className="sp-today-note">{DECLARED_LIGHT_COMBAT_DESCRIPTION}</p>
          ) : isTechnicalSession ? (
            <TechnicalCombatRationale />
          ) : objective ? (
            <p className="sp-session-objective">
              <span className="sp-session-why-label">Why</span>
              {objective}
            </p>
          ) : null}
        </div>
        <div className="sp-session-meta">
          {isDeclaredLightCombat ? (
            <span className="sp-tag sp-accent">Light combat</span>
          ) : isTechnicalSession ? (
            <span className="sp-tag sp-accent">{TECHNICAL_COMBAT_TAG}</span>
          ) : sessionType ? (
            <span className="sp-tag">{titleize(sessionType)}</span>
          ) : null}
          {duration ? <span className="sp-tag">{duration}</span> : null}
          {completionInfo?.display.label ? (
            <span className="sp-tag sp-status-tag" data-tone={completionInfo.display.tone}>
              {completionInfo.display.label}
            </span>
          ) : null}
        </div>
      </header>

      {completionInfo?.completion &&
      (completionInfo.completion.session_rpe != null || completionInfo.completion.modification_reason) ? (
        <p className="sp-session-log-meta">
          {completionInfo.completion.session_rpe != null ? (
            <>
              {`RPE ${completionInfo.completion.session_rpe}/10`}
              <GlossaryTooltip term="RPE" />
            </>
          ) : null}
          {completionInfo.completion.session_rpe != null && completionInfo.completion.modification_reason
            ? " · "
            : null}
          {completionInfo.completion.modification_reason
            ? `Reason: ${completionInfo.completion.modification_reason}`
            : null}
        </p>
      ) : null}

      {completionInfo?.onLog ? (
        <button type="button" className="secondary-button sp-log-session" onClick={completionInfo.onLog}>
          Log this session
        </button>
      ) : null}

      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}

      <MindsetAnchorCard
        anchor={sessionMindset}
        dedupeContext={
          isDeclaredLightCombat
            ? DECLARED_LIGHT_COMBAT_DESCRIPTION
            : isTechnicalSession
              ? TECHNICAL_COMBAT_RATIONALE
              : objective
        }
      />
      {/* The rehab/mobility summary is a compact PREVIEW of the inserts shown
          only while the full blocks are collapsed. Once expanded, every rehab
          block renders in full below, so keeping the summary too would print the
          same insert as two separate cards. */}
      {!showDetails ? <RehabSummary blocks={rehabBlocks} /> : null}

      {blocks.length > 0 ? (
        <>
          <button
            type="button"
            className="sp-more-toggle sp-session-toggle"
            aria-expanded={showDetails}
            aria-controls={detailsId}
            aria-label={showDetails ? "Show less session detail" : `Show more session detail: ${blocksLabel}`}
            onClick={() => {
              userToggledDetails.current = true;
              setShowDetails((prev) => !prev);
            }}
          >
            {showDetails ? "Show less" : `Show more (${blocksLabel})`}
          </button>

          {showDetails ? (
            <div id={detailsId} className="sp-blocks">
              {blocks.map((block, index) => (
                <BlockCard
                  key={cleanText(block.block_id) || `block-${index}`}
                  block={block}
                  openWeekIntent={openWeekIntent}
                  sourceCountdown={sourceCountdown}
                />
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

export function TodayCard({ day }: { day: StructuredDay }) {
  const card = day.today_card;
  const headline = cleanText(card?.headline);
  const readiness = cleanText(card?.readiness_status);
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const mindsetLines = getSessionCoachingLines(card?.mindset_anchor);
  if (
    !headline &&
    !readiness &&
    !warning &&
    !nutrition &&
    !weightCut &&
    mindsetLines.length === 0
  ) {
    return null;
  }
  return (
    <div className="sp-today">
      {headline ? <p className="sp-today-headline">{headline}</p> : null}
      {readiness ? (
        <span className="sp-tag">{titleize(readiness)}</span>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard anchor={card?.mindset_anchor} dedupeContext={headline} />
    </div>
  );
}

/**
 * A day with no app sessions. Coach-led / sparring / technical days legitimately
 * carry no app S&C blocks, so they are rendered as a self-contained card derived
 * deterministically from the day data (see classifySessionlessDay) instead of
 * collapsing into "Rest day.". Only a genuine rest day reads as a rest day.
 */
export function SessionlessDayCard({
  day,
  showDayLabels = true,
}: {
  day: StructuredDay;
  /** False inside the plan accordion, where the day row already shows the
   * countdown/date; the Today tab keeps the default. */
  showDayLabels?: boolean;
}) {
  const date = cleanText(day.date);
  const countdown = formatCountdownLabel(day.countdown_label);
  const card = day.today_card;
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const { kind, title, tag, coachLed } = classifySessionlessDay(day);
  const displayTitle =
    kind === "light_combat"
      ? DECLARED_LIGHT_COMBAT_TITLE
      : kind === "technical"
        ? (title === "Technical-only combat" ? TECHNICAL_COMBAT_TITLE : title)
        : title;
  const displayTag = kind === "technical" ? TECHNICAL_COMBAT_TAG : tag;
  const isRest = kind === "rest";

  return (
    <article className={`sp-session sp-day-card sp-day-card-${kind}`}>
      <header className="sp-session-head">
        <div>
          {showDayLabels && (countdown || date) ? (
            <div className="sp-day-labels sp-session-day-labels">
              {countdown ? <span className="sp-countdown sp-accent">{countdown}</span> : null}
              {date ? <span className="sp-day-date">{formatAppDate(date)}</span> : null}
            </div>
          ) : null}
          <h3 className="sp-session-title">
            {displayTitle}
            {kind === "technical" ? <TechnicalCombatWhyTooltip /> : null}
          </h3>
        </div>
        <div className="sp-session-meta">
          {displayTag ? <span className="sp-tag sp-accent">{displayTag}</span> : null}
        </div>
      </header>
      {kind === "light_combat" ? (
        <p className="sp-today-note">{DECLARED_LIGHT_COMBAT_DESCRIPTION}</p>
      ) : kind === "technical" ? (
        <TechnicalCombatRationale title={displayTitle} />
      ) : coachLed ? (
        <p className="sp-today-note">{HARD_SPARRING_SESSIONLESS_NOTE}</p>
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      <MindsetAnchorCard
        anchor={card?.mindset_anchor}
        dedupeContext={[cleanText(card?.headline), displayTitle]}
      />
      {isRest ? <p className="sp-muted">Rest day.</p> : null}
    </article>
  );
}

function LightTechnicalDayContext({
  tag,
}: {
  tag: string | null;
}) {
  return (
    <div className="cm-light-technical">
      <div className="cm-light-technical-head">
        {tag ? <span className="sp-tag sp-accent">{tag}</span> : null}
        <p className="sp-today-headline">{DECLARED_LIGHT_COMBAT_TITLE}</p>
      </div>
      <p className="sp-today-note">{DECLARED_LIGHT_COMBAT_DESCRIPTION}</p>
    </div>
  );
}

/**
 * Coach-owned contact (declared / downgraded sparring) shown above the day's app
 * sessions so the two coexist in one card instead of the sparring day silently
 * disappearing behind the low-RPE app work scheduled on the same day.
 */
function CoachLedDayContext({
  title,
  tag,
  kind,
}: {
  title: string;
  tag: string | null;
  kind: SessionlessDayKind;
}) {
  const isLightCombat = kind === "light_combat";
  const isTechnical = kind === "technical";
  const displayTitle = isLightCombat
    ? DECLARED_LIGHT_COMBAT_TITLE
    : isTechnical
      ? (title === "Technical-only combat" ? TECHNICAL_COMBAT_TITLE : title)
      : title;
  const displayTag = isTechnical ? TECHNICAL_COMBAT_TAG : tag;
  const description = isLightCombat
    ? DECLARED_LIGHT_COMBAT_DESCRIPTION
    : HARD_SPARRING_CONTACT_NOTE;

  return (
    <div className="cm-light-technical cm-coach-led-contact">
      <div className="cm-light-technical-head">
        {displayTag ? <span className="sp-tag sp-accent">{displayTag}</span> : null}
        <p className="sp-today-headline">
          {displayTitle}
          {isTechnical ? <TechnicalCombatWhyTooltip /> : null}
        </p>
      </div>
      {isTechnical ? (
        <TechnicalCombatRationale title={displayTitle} />
      ) : (
        <p className="sp-today-note">{description}</p>
      )}
    </div>
  );
}

export function DaySessionContext({ day }: { day: StructuredDay }) {
  const card = day.today_card;
  const warning = cleanText(card?.primary_warning);
  const nutrition = cleanText(card?.nutrition_summary);
  const weightCut = cleanText(card?.weight_cut_warning);
  const sessionlessDay = classifySessionlessDay(day);
  const lightTechnicalContext = sessionlessDay.kind === "light_combat";
  const coachLedContact = getCoachLedContactView(day);
  const coachLedLightCombat = coachLedContact?.kind === "light_combat";
  const showLightTechnicalContext = lightTechnicalContext && !coachLedLightCombat;
  // Session-level anchors are the most specific coaching cue in this schema, so
  // keep them and suppress the broader day anchor whenever any session owns one.
  // The day anchor remains the fallback when none of the sessions has a usable
  // coaching cue.
  const dayMindset = card?.mindset_anchor;
  const hasSessionMindset = getSessions(day).some(
    (session) => getSessionCoachingLines(session.mindset_anchor).length > 0,
  );
  const hasDayMindset = !hasSessionMindset && getSessionCoachingLines(dayMindset).length > 0;
  // The day mindset's Context often restates a session's objective shown just
  // below it (same sentence, twice on screen); drop it against those.
  const dayObjectives = getSessions(day).map((session) => cleanText(session.objective));
  const hasDayContext = Boolean(
    warning || nutrition || weightCut || showLightTechnicalContext || coachLedContact || hasDayMindset,
  );
  if (!hasDayContext) {
    return null;
  }

  return (
    <div className="cm-day-context">
      {showLightTechnicalContext ? (
        <LightTechnicalDayContext tag={sessionlessDay.tag} />
      ) : null}
      {coachLedContact ? (
        <CoachLedDayContext
          title={coachLedContact.title}
          tag={coachLedContact.tag}
          kind={coachLedContact.kind}
        />
      ) : null}
      {warning ? <p className="sp-warning">{warning}</p> : null}
      {nutrition ? <p className="sp-today-note">{nutrition}</p> : null}
      {weightCut ? <p className="sp-warning">{weightCut}</p> : null}
      {hasDayMindset ? <MindsetAnchorCard anchor={dayMindset} dedupeContext={dayObjectives} /> : null}
    </div>
  );
}

/** Short weekday name from an ISO date string ("2026-06-19" -> "Fri"), or null. */
function weekdayLabel(date: string | null): string | null {
  if (!date) {
    return null;
  }
  const parsed = new Date(`${date.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return weekdays[parsed.getDay()];
}

function openTimelineDayLabel(
  day: StructuredDay,
  weekNumber: number,
  fallbackLabel: string,
): string {
  const date = cleanText(day.date);
  if (date) {
    return formatAppDate(date).split(" ").slice(0, 3).join(" ").toUpperCase();
  }
  const weekday = cleanText(day.weekday)?.toUpperCase();
  return weekday ? `WEEK ${weekNumber} · ${weekday}` : fallbackLabel;
}

/** One row of the week's day timeline: a real plan day (with its original index
 * in the week's day list, which the current/default-open logic is keyed on) or a
 * synthesized gap day that fills a hole in the countdown. */
export type TimelineEntry =
  | { kind: "day"; day: StructuredDay; index: number }
  | { kind: "gap"; dateIso: string; weekday: string | null; countdown: string | null };

const COUNTDOWN_LABEL_RE = /^D-(\d+)$/i;

function parseIsoDay(iso: string | null | undefined): Date | null {
  const clean = cleanText(iso ?? null);
  if (!clean) {
    return null;
  }
  const parsed = new Date(`${clean.slice(0, 10)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const ISO_DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function toLocalIsoDay(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Gap rows between two consecutive plan days. Fails closed: no rows unless
 * both dates parse and sit 2–7 calendar days apart (in-order, sane data), and
 * no countdown number unless both neighbours' labels parse as D-n and descend
 * exactly one per day — a weekday-only rest row beats a wrong number. */
function gapRowsBetween(prev: StructuredDay, next: StructuredDay): TimelineEntry[] {
  const prevDate = parseIsoDay(prev.date);
  const nextDate = parseIsoDay(next.date);
  if (!prevDate || !nextDate) {
    return [];
  }
  const diff = Math.round((nextDate.getTime() - prevDate.getTime()) / 86_400_000);
  if (diff < 2 || diff > 7) {
    return [];
  }
  const prevMatch = formatCountdownLabel(prev.countdown_label)?.match(COUNTDOWN_LABEL_RE);
  const nextMatch = formatCountdownLabel(next.countdown_label)?.match(COUNTDOWN_LABEL_RE);
  const prevN = prevMatch ? Number(prevMatch[1]) : null;
  const nextN = nextMatch ? Number(nextMatch[1]) : null;
  const countdownConsistent = prevN != null && nextN != null && prevN - diff === nextN;
  const rows: TimelineEntry[] = [];
  for (let offset = 1; offset < diff; offset += 1) {
    const gapDate = new Date(prevDate);
    gapDate.setDate(gapDate.getDate() + offset);
    const dateIso = toLocalIsoDay(gapDate);
    rows.push({
      kind: "gap",
      dateIso,
      weekday: weekdayLabel(dateIso),
      countdown: countdownConsistent ? `D-${prevN! - offset}` : null,
    });
  }
  return rows;
}

/** The selected week's days with rest rows filling intra-week date holes, so
 * the countdown reads continuous (D-10, D-9, D-8…) instead of skipping. Open
 * (weekday-only) plans carry no dates, so gap fill is disabled there. */
export function buildDayTimeline(days: StructuredDay[], enabled: boolean): TimelineEntry[] {
  const timeline: TimelineEntry[] = [];
  days.forEach((day, index) => {
    if (enabled && index > 0) {
      timeline.push(...gapRowsBetween(days[index - 1], day));
    }
    timeline.push({ kind: "day", day, index });
  });
  return timeline;
}

/** A plan day that is genuinely just rest — no sessions, classified as rest,
 * and no day-card context worth expanding — so it can render as a compact
 * non-interactive rest row identical to the synthesized gap rows. */
function isPlainRestDay(day: StructuredDay): boolean {
  if (getSessions(day).length > 0 || classifySessionlessDay(day).kind !== "rest") {
    return false;
  }
  const card = day.today_card;
  return !(
    cleanText(card?.headline) ||
    cleanText(card?.primary_warning) ||
    cleanText(card?.nutrition_summary) ||
    cleanText(card?.weight_cut_warning) ||
    getSessionCoachingLines(card?.mindset_anchor).length > 0
  );
}

/** Widest countdown at which an unprogrammed day is deliberate taper rest.
 * Inside fight week the session budget caps active work on purpose, so a day
 * with nothing scheduled is a planned rest day rather than missing data. */
const TAPER_REST_MAX_COUNTDOWN = 7;

/** How a synthesized countdown-gap row should read.
 *
 * Further out, a hole in a sparse plan could be rest, coach-led work, or simply
 * undocumented, so it keeps the honest "No planned session". Inside fight week
 * the plan's own budgets deliberately leave days unprogrammed, so the day is
 * named as the taper rest it is and given the reason — an athlete opening the
 * app on D-2 should read intent, not a blank. */
function gapDayLabel(countdown: string | null): { label: string; reason: string | null } {
  const match = cleanText(countdown)?.match(COUNTDOWN_LABEL_RE);
  const daysOut = match ? Number(match[1]) : null;
  if (daysOut != null && daysOut > 0 && daysOut <= TAPER_REST_MAX_COUNTDOWN) {
    return {
      label: "Taper rest",
      reason: "Planned rest — protecting freshness for fight day.",
    };
  }
  return { label: "No planned session", reason: null };
}

/** Compact non-interactive rest row: same columns as a day summary (countdown,
 * weekday, optional current marker) with a right-aligned label where the session
 * count would sit. Deliberately a div, not a <details> — there is nothing to
 * expand, so it must not advertise an affordance.
 *
 * `label` distinguishes the sources: a backend-classified rest day reads
 * "Rest", while a synthesized countdown-gap row reads either "Taper rest" with
 * a reason (inside fight week, where the empty day is deliberate) or the honest
 * "No planned session" — it must not assert rest the data can't back. */
function RestDayRow({
  countdown,
  weekday,
  label = "Rest",
  reason = null,
  isCurrent,
  currentLabel = "Today",
}: {
  countdown: string | null;
  weekday: string | null;
  label?: string;
  reason?: string | null;
  isCurrent?: boolean;
  currentLabel?: string;
}) {
  const fightWeekSessionless = /^D-[0-7]$/i.test(countdown ?? "");
  return (
    <div
      className={`sp-week cm-day cm-rest-day${fightWeekSessionless ? " cm-fight-week-sessionless" : ""}${isCurrent ? " cm-day-current" : ""}`}
    >
      <span className="cm-day-head">
        {countdown ? (
          <span className={`sp-countdown cm-day-countdown${isCurrent ? " sp-accent" : ""}`}>
            {countdown}
          </span>
        ) : null}
        {weekday ? <span className="sp-week-title cm-day-title">{weekday}</span> : null}
        {isCurrent ? <span className="cm-day-now">{currentLabel}</span> : null}
        {reason ? <span className="cm-rest-reason">{reason}</span> : null}
      </span>
      <span className="cm-rest-label">{label}</span>
    </div>
  );
}

function CompletionTag({ completion }: { completion: Completion }) {
  if (completion.total === 0) {
    return null;
  }
  const done = completion.done >= completion.total && completion.total > 0;
  // "Done" is a positive, completed state — give it a calm success tone rather
  // than the brand red, which we keep reserved for current action / risk. The
  // bare fraction keeps the closed row to one line; screen readers still get
  // the full meaning.
  return (
    <span className={`cm-day-count${done ? " cm-day-count-done" : ""}`}>
      {done ? "✓ " : ""}
      {completion.done}/{completion.total}
      <span className="sr-only"> sessions done</span>
    </span>
  );
}

/**
 * One day of the selected week, as a collapsible card. Collapsed by default
 * except the current/selected day so the athlete lands on what matters today;
 * the current day's session blocks are expanded too. Session-less days reuse the
 * deterministic coach-led / rest classification.
 */
export function CampDayCard({
  day,
  displayDate,
  fallbackLabel,
  openOngoing = false,
  weekNumber = 1,
  isCurrent,
  currentLabel = "Today",
  defaultOpen,
  completionIndex,
  currentTrainingDayIso,
  onLogSession,
}: {
  day: StructuredDay;
  /** Truthful calendar date for a recurring weekday match. The stored projected
   * date remains untouched for completion and logging identity. */
  displayDate?: string | null;
  fallbackLabel?: string;
  openOngoing?: boolean;
  weekNumber?: number;
  isCurrent?: boolean;
  /** Badge text for the highlighted day — "Today" normally, "Next session" once
   * the view has advanced past a logged today's session. */
  currentLabel?: string;
  defaultOpen?: boolean;
  /** Live completion rows keyed by training_day|session_id. When present the
   * session cards show real done/modified/skipped/missed status. */
  completionIndex?: CompletionIndex;
  /** Server-authoritative athlete-local day (drives Missed + the retro window). */
  currentTrainingDayIso?: string | null;
  /** Opens the retro-log form for a past, still-loggable session. */
  onLogSession?: (day: StructuredDay, session: StructuredSession, sessionId: string) => void;
}) {
  const [open, setOpen] = useState<boolean>(Boolean(defaultOpen));
  const userToggledOpen = useRef(false);

  useEffect(() => {
    if (!userToggledOpen.current) {
      setOpen(Boolean(defaultOpen));
    }
  }, [defaultOpen]);

  const sessions = getSessions(day);
  const storedDate = cleanText(day.date);
  const date = cleanText(displayDate) || storedDate;
  const weekday = weekdayLabel(date);
  const countdown = formatCountdownLabel(day.countdown_label);
  const timelineLabel = openOngoing
    ? openTimelineDayLabel(
        displayDate ? { ...day, date: displayDate } : day,
        weekNumber,
        fallbackLabel || `Week ${weekNumber} training day`,
      )
    : weekday || date || fallbackLabel || "Training day";
  const weekIntent = openOngoing ? openBlockWeekIntent(weekNumber) : null;
  const completion = dayCompletion(day, completionIndex);
  const dayIso = storedDate ? storedDate.slice(0, 10) : null;

  const completionInfoFor = (session: StructuredSession): SessionCompletionInfo | undefined => {
    if (!completionIndex) {
      return undefined;
    }
    const record = completionForSession(completionIndex, day, session);
    const sessionId = completionSessionId(day, session);
    // A session with no completion identity (id-less secondary) stays neutral.
    if (!sessionId) {
      return undefined;
    }
    const display = getSessionDisplayStatus(record, dayIso, currentTrainingDayIso ?? null);
    const terminal = display.state === "done" || display.state === "modified" || display.state === "skipped";
    const canLog =
      Boolean(onLogSession) && !terminal && canRetroLog(dayIso, currentTrainingDayIso ?? null);
    return {
      display,
      completion: record,
      onLog: canLog ? () => onLogSession?.(day, session, sessionId) : undefined,
    };
  };

  return (
    <details
      className={`sp-week cm-day${isCurrent ? " cm-day-current" : ""}`}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary
        className="sp-week-summary cm-day-summary"
        onClick={() => {
          userToggledOpen.current = true;
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            userToggledOpen.current = true;
          }
        }}
      >
        <span className="cm-day-head">
          {countdown ? (
            <span className={`sp-countdown cm-day-countdown${isCurrent ? " sp-accent" : ""}`}>
              {countdown}
            </span>
          ) : null}
          <span className="sp-week-title cm-day-title">{timelineLabel}</span>
          {isCurrent ? <span className="cm-day-now">{currentLabel}</span> : null}
        </span>

        <span className="cm-day-meta">
          <CompletionTag completion={completion} />
        </span>
      </summary>

      <div className="sp-week-body">
        {sessions.length > 0 ? <DaySessionContext day={day} /> : null}

        {sessions.length > 0 ? (
          <div className="sp-sessions">
            {sessions.map((session, index) => (
              <SessionCard
                key={cleanText(session.session_id) || `session-${index}`}
                session={session}
                day={index === 0 ? day : undefined}
                sourceCountdown={day.countdown_label}
                defaultOpenBlocks={isCurrent}
                showDayContext={false}
                showDayLabels={false}
                completionInfo={completionInfoFor(session)}
                openWeekIntent={weekIntent}
              />
            ))}
          </div>
        ) : (
          <SessionlessDayCard day={day} showDayLabels={false} />
        )}
      </div>
    </details>
  );
}

function getSafetyPriorityTexts(plan: StructuredPlan): string[] {
  const rules = getDisplayableRedFlags(plan);
  if (rules.length > 0) {
    return rules.flatMap((rule) =>
      [cleanText(rule.display_text), cleanText(rule.action)].filter(
        (text): text is string => text !== null,
      ),
    );
  }
  return getFallbackSafetyNotes(plan)
    .map((note) => cleanText(note.text))
    .filter((text): text is string => text !== null);
}

// Plan-level "active notes": the short, always-on reminders (weight cut,
// injury, nutrition, general non-negotiables) that live outside any week. Kept
// as a standalone card near the top so this context is not lost in the
// structured view the way it would be if it only existed in the raw text.
export function ActiveNotesCard({ plan }: { plan: StructuredPlan }) {
  // Drop any note that just restates a red-flag rule — the Red Flags card is the
  // single home for stop/report rules, so Active Notes stays context-only.
  const safetyPriorityTexts = getSafetyPriorityTexts(plan);
  const notes = getActiveNotesExcludingRedFlags(plan).flatMap((note) => {
    const text = stripSafetyOwnedClause(cleanText(note.text) || "", safetyPriorityTexts);
    return text ? [{ ...note, text }] : [];
  });
  // Collapsed by default so the plan opens short: the title + count stay visible
  // and the detail is one tap away.
  const [open, setOpen] = useState(false);
  if (notes.length === 0) {
    return null;
  }
  return (
    <details
      className="sp-collapse sp-active-notes"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary">
        <span className="sp-collapse-title">Active notes</span>
        <span className="sp-collapse-action">
          {open ? "Hide" : "Show"} ({notes.length})
        </span>
      </summary>
      <div className="sp-collapse-body">
        <ul className="sp-note-list">
          {notes.map((note, index) => (
            <li key={`${note.category}-${index}`} className={`sp-note sp-note-${note.category}`}>
              <span className="sp-note-label">{planNoteLabel(note)}</span>
              <span className="sp-note-text">{note.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

/** Map a severity label ("Red", "Amber", "High", "Low"…) to a tone class so the
 *  badge colour carries the meaning. Unknown severities stay neutral. */
function severityToneClass(label: string | null): string {
  if (!label) {
    return "";
  }
  const l = label.toLowerCase();
  if (/\b(red|high|critical|severe)\b/.test(l)) {
    return "sp-sev-red";
  }
  if (/\b(amber|orange|moderate|medium|elevated)\b/.test(l)) {
    return "sp-sev-amber";
  }
  if (/\b(green|low|mild|minor)\b/.test(l)) {
    return "sp-sev-green";
  }
  return "";
}

export function RedFlagsCard({ plan }: { plan: StructuredPlan }) {
  const rules = getDisplayableRedFlags(plan);
  const fallbackNotes = rules.length === 0 ? getFallbackSafetyNotes(plan) : [];
  const hasStopRules = rules.length > 0 || fallbackNotes.length > 0;
  // Collapsed by default to keep the plan short; the "stop & report" title stays
  // on screen so the rules are always one tap away.
  const [open, setOpen] = useState(false);
  // The safety/medical disclaimer is folded in here (it used to be a separate
  // banner) so safety lives in one block. The body therefore always renders the
  // disclaimer, with the stop/report rules above it when present.
  return (
    <details
      className="sp-collapse sp-redflags"
      aria-label="Red flags and safety actions"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="sp-collapse-summary sp-redflags-summary">
        <span className="sp-redflags-summary-text">
          <span className="sp-eyebrow">Safety priority</span>
          <span className="sp-collapse-title">Red flags - stop &amp; report</span>
        </span>
        <span className="sp-collapse-action">{open ? "Hide" : "Show"}</span>
      </summary>
      <div className="sp-collapse-body">
      {hasStopRules ? (
      <ul className="sp-redflag-list">
        {rules.length > 0 ? rules.map((rule, index) => {
          const { text, action, severityLabel } = redFlagView(rule);
          // A weight-cut symptom rule is always shown, but its secondary text is
          // softened when cut risk is EXPLICITLY below moderate so it does not
          // lead. An explicit red/critical/high severity is never softened (the
          // severity is passed so it overrides), and the severity badge itself
          // always stays full-strength (see the CSS — only text is muted).
          const deEmphasised = isDeEmphasisedWeightCutSafety(plan, text, rule.severity as string);
          return (
            <li
              key={cleanText(rule.rule_id) || `flag-${index}`}
              className={`sp-redflag${deEmphasised ? " sp-redflag-deemphasised" : ""}`}
            >
              <div className="sp-redflag-head">
                <span className="sp-redflag-kicker">Stop signal</span>
                {severityLabel ? (
                  <span
                    className={`sp-tag sp-redflag-badge ${severityToneClass(severityLabel)}`.trim()}
                  >
                    {severityLabel}
                  </span>
                ) : null}
              </div>
              {text ? <span className="sp-redflag-text">{text}</span> : null}
              {action ? <p className="sp-muted">{action}</p> : null}
            </li>
          );
        }) : fallbackNotes.map((note, index) => {
          const deEmphasised = isDeEmphasisedWeightCutSafety(plan, note.text);
          return (
          <li
            key={`${note.category}-${index}`}
            className={`sp-redflag${deEmphasised ? " sp-redflag-deemphasised" : ""}`}
          >
            <div className="sp-redflag-head">
              <span className="sp-redflag-kicker">Safety note</span>
              <span className="sp-tag sp-redflag-badge">{planNoteLabel(note)}</span>
            </div>
            <span className="sp-redflag-text">{note.text}</span>
          </li>
          );
        })}
      </ul>
      ) : null}
      <SafetyNote tone="warning" showRedFlags>{PLAN_SAFETY_NOTE}</SafetyNote>
      </div>
    </details>
  );
}

/** Athlete-safe deterministic weight-cut line: risk band + supervision only. */
function DeterministicWeightCutLine({
  weightCut,
}: {
  weightCut: { band: string; supervisionRequired: boolean } | null;
}) {
  if (!weightCut) {
    return null;
  }
  return (
    <p className="sp-warning">
      <span className="sp-tag">{titleize(weightCut.band)} weight-cut risk</span>
      {weightCut.supervisionRequired ? " — qualified supervision required." : ""}
    </p>
  );
}

/** Plan nutrition prose (the legacy LLM/string fields) — fallback only. */
function NutritionProse({ plan }: { plan: StructuredPlan }) {
  const nutrition = plan.nutrition;
  const rows: Array<{
    label: string;
    value: string | null;
    wide?: boolean;
    wideMobile?: boolean;
  }> = [
    { label: "Summary", value: cleanText(nutrition?.summary) },
    { label: "Daily", value: cleanText(nutrition?.daily_focus) },
    { label: "Training days", value: cleanText(nutrition?.training_day_guidance) },
    { label: "Fight week", value: cleanText(nutrition?.fight_week_guidance) },
  ].filter((row) => row.value);
  const weightCut = cleanText(nutrition?.weight_cut_warning?.display_text);
  const cutRisk = cleanText(nutrition?.weight_cut_warning?.risk_level);
  const needsSupport = nutrition?.weight_cut_warning?.requires_professional_support === true;
  return (
    <>
      <ul className="sp-kv-list">
        {rows.map((row) => (
          <li key={row.label}>
            <span className="sp-kv-label">{row.label}</span>
            <span>{row.value}</span>
          </li>
        ))}
      </ul>
      {weightCut ? (
        <p className="sp-warning">
          {cutRisk && cutRisk !== "none" ? (
            <>
              <span className="sp-tag">{titleize(cutRisk)} risk</span>{" "}
            </>
          ) : null}
          {weightCut}
          {needsSupport ? " — qualified supervision required." : ""}
        </p>
      ) : null}
    </>
  );
}

type NutritionPhaseItem = {
  phase: string;
  phaseKey: string | null;
  rows: { label: string; value: string }[];
  weightCut: { band: string; supervisionRequired: boolean } | null;
};

type RecoveryPhaseItem = {
  phase: string;
  phaseKey: string | null;
  view: ReturnType<typeof recoveryPhaseView>;
  lists: { label: string; items: string[] }[];
};

/** Index of the support phase matching the viewed week (else the first phase),
 * so nutrition/recovery open on the phase the athlete is actually looking at. */
function resolveActiveSupportPhaseIndex(
  items: { phaseKey: string | null }[],
  activePhaseKey: string | null,
): number {
  if (activePhaseKey) {
    const match = items.findIndex((item) => item.phaseKey === activePhaseKey);
    if (match >= 0) {
      return match;
    }
  }
  return 0;
}

function getNutritionPhaseItems(plan: StructuredPlan): NutritionPhaseItem[] {
  return getDeterministicNutritionPhases(plan)
    .map(({ phase, entry }: { phase: string; entry: DeterministicNutritionPhase }) => {
      const rows = nutritionPhaseRows(entry);
      const weightCut = formatWeightCutBand(entry.weight_cut);
      if (rows.length === 0 && !weightCut) {
        return null;
      }
      return { phase, phaseKey: normalizeSupportPhaseKey(phase), rows, weightCut };
    })
    .filter((item): item is NutritionPhaseItem => item !== null);
}

function getRecoveryPhaseItems(plan: StructuredPlan): RecoveryPhaseItem[] {
  return getDeterministicRecoveryPhases(plan)
    .map(({ phase, entry }: { phase: string; entry: DeterministicRecoveryPhase }) => {
      const view = recoveryPhaseView(entry);
      const lists: { label: string; items: string[] }[] = [
        { label: "Core", items: view.coreStrategies },
        { label: "Phase focus", items: view.phaseFocus },
        { label: "Fatigue", items: view.fatigue },
        { label: "Age", items: view.ageAdjustments },
      ].filter((group) => group.items.length > 0);
      if (!view.sleep && lists.length === 0 && !view.weightCut) {
        return null;
      }
      return { phase, phaseKey: normalizeSupportPhaseKey(phase), view, lists };
    })
    .filter((item): item is RecoveryPhaseItem => item !== null);
}

function NutritionPhaseCard({
  item,
  defaultOpen,
  syncKey,
  displayLabel,
}: {
  item: NutritionPhaseItem;
  defaultOpen?: boolean;
  syncKey?: string | null;
  displayLabel?: string;
}) {
  const phaseLabel = displayLabel || titleize(item.phase);
  return (
    <section className="sp-card sp-support-card sp-nutrition">
      <div className="sp-support-head">
        <p className="sp-eyebrow">Nutrition</p>
        <span className="sp-tag">{phaseLabel}</span>
      </div>
      <CollapsibleSection
        title={phaseLabel}
        detailLabel={`${phaseLabel} nutrition`}
        defaultOpen={defaultOpen}
        syncKey={syncKey}
        className="sp-nutrition-phase"
      >
        <ul className="sp-kv-list">
          {item.rows.map((row) => (
            <li key={row.label}>
              <span className="sp-kv-label">{row.label}</span>
              <span>{row.value}</span>
            </li>
          ))}
        </ul>
        <DeterministicWeightCutLine weightCut={item.weightCut} />
      </CollapsibleSection>
    </section>
  );
}

function RecoveryPhaseCard({
  item,
  defaultOpen,
  syncKey,
  displayLabel,
}: {
  item: RecoveryPhaseItem;
  defaultOpen?: boolean;
  syncKey?: string | null;
  displayLabel?: string;
}) {
  const phaseLabel = displayLabel || titleize(item.phase);
  return (
    <section className="sp-card sp-support-card sp-recovery">
      <div className="sp-support-head">
        <p className="sp-eyebrow">Recovery</p>
        <span className="sp-tag">{phaseLabel}</span>
      </div>
      <CollapsibleSection
        title={phaseLabel}
        detailLabel={`${phaseLabel} recovery`}
        defaultOpen={defaultOpen}
        syncKey={syncKey}
        className="sp-recovery-phase"
      >
        <ul className="sp-kv-list">
          {item.view.sleep ? (
            <li>
              <span className="sp-kv-label">Sleep</span>
              <span>{item.view.sleep}</span>
            </li>
          ) : null}
          {item.lists.map((group) => (
            <li key={group.label}>
              <span className="sp-kv-label">{group.label}</span>
              <span>{group.items.join("; ")}</span>
            </li>
          ))}
        </ul>
        <DeterministicWeightCutLine weightCut={item.view.weightCut} />
      </CollapsibleSection>
    </section>
  );
}

// Owns the full nutrition details. Deterministic Stage 1 macros/hydration/fuel
// timing win when present; the legacy prose fields are the fallback only. Never
// renders coach_gated (it is stripped server-side before reaching the frontend).
export function NutritionCard({
  plan,
  activePhaseKey = null,
  openOngoing = false,
}: {
  plan: StructuredPlan;
  /** Normalized phase key of the week the athlete is viewing. The matching
   * phase opens by default so a taper/SPP week does not land on expanded GPP. */
  activePhaseKey?: string | null;
  openOngoing?: boolean;
}) {
  const items = getNutritionPhaseItems(plan);
  if (items.length === 0 && !hasNutrition(plan)) {
    return null;
  }
  if (items.length === 0) {
    return (
      <section className="sp-card sp-nutrition">
        <p className="sp-eyebrow">Nutrition</p>
        <NutritionProse plan={plan} />
      </section>
    );
  }
  const openIndex = resolveActiveSupportPhaseIndex(items, activePhaseKey);
  const visibleItems = openOngoing ? items.slice(openIndex, openIndex + 1) : items;
  return (
    <div className="sp-phase-support-grid">
      {visibleItems.map((item, index) => (
        <NutritionPhaseCard
          key={item.phase}
          item={item}
          defaultOpen={openOngoing || index === openIndex}
          syncKey={activePhaseKey ?? ""}
          displayLabel={openOngoing ? "Current block" : undefined}
        />
      ))}
    </div>
  );
}

// Owns recovery detail (sleep / fatigue / phase focus / core actions). Renders
// deterministic Stage 1 recovery; never coach_gated. Stop/modify/report
// thresholds stay with RedFlagsCard, so this card does not repeat them.
export function RecoveryCard({
  plan,
  activePhaseKey = null,
  openOngoing = false,
}: {
  plan: StructuredPlan;
  activePhaseKey?: string | null;
  openOngoing?: boolean;
}) {
  const items = getRecoveryPhaseItems(plan);
  if (items.length === 0) {
    return null;
  }
  const openIndex = resolveActiveSupportPhaseIndex(items, activePhaseKey);
  const visibleItems = openOngoing ? items.slice(openIndex, openIndex + 1) : items;
  return (
    <div className="sp-phase-support-grid">
      {visibleItems.map((item, index) => (
        <RecoveryPhaseCard
          key={item.phase}
          item={item}
          defaultOpen={openOngoing || index === openIndex}
          syncKey={activePhaseKey ?? ""}
          displayLabel={openOngoing ? "Current block" : undefined}
        />
      ))}
    </div>
  );
}

/** Threshold at which the week rail switches from "share the width evenly" to
 * "hold a readable width and scroll". Up to this many weeks fit the strip
 * without scrolling; beyond it the rail shows ~this many per viewport. */
const WEEK_STRIP_FIT_LIMIT = 4;

/** Horizontal scroll offset that centres a week card within the rail, clamped so
 * the first cards never scroll past the start. Pure for direct testing — jsdom
 * reports zero element geometry, so the centring math is verified here rather
 * than through a rendered layout. */
export function weekStripCenterOffset(
  stripWidth: number,
  pillOffset: number,
  pillWidth: number,
): number {
  return Math.max(0, pillOffset - (stripWidth - pillWidth) / 2);
}

/** Progression rail of week cards used to pick the week. Up to four weeks share
 * the strip width evenly (no scroll); five or more hold a readable ~quarter
 * width and the rail scrolls with snap, auto-centring the active week. */
function WeekStrip({
  weeks,
  selectedPos,
  currentPos,
  onSelect,
  completionIndex,
  openOngoing,
}: {
  weeks: StructuredWeek[];
  selectedPos: number;
  currentPos: number | null;
  onSelect: (pos: number) => void;
  completionIndex?: CompletionIndex;
  openOngoing: boolean;
}) {
  const stripRef = useRef<HTMLElement>(null);
  const scrollable = weeks.length > WEEK_STRIP_FIT_LIMIT;
  // Centre on the week being viewed. `selectedPos` (the parent's `safePos`)
  // already defaults to the current week until the athlete picks another, so it
  // covers "land on now" on mount AND re-centres each manual selection — whereas
  // preferring `currentPos` would pin the target and never move when a different
  // week is tapped, leaving that card half cut off.
  const activePos = selectedPos;

  // Bring the active week into view when the rail scrolls. Adjusts only the
  // horizontal scroll of the strip itself (never scrollIntoView, which could
  // jump the whole page vertically). No-ops when the rail is not scrollable or
  // has no layout yet (SSR / jsdom report zero widths).
  useEffect(() => {
    const strip = stripRef.current;
    if (!strip || strip.scrollWidth <= strip.clientWidth) {
      return;
    }
    const pill = strip.querySelector<HTMLElement>(`[data-week-pos="${activePos}"]`);
    if (!pill) {
      return;
    }
    strip.scrollLeft = weekStripCenterOffset(strip.clientWidth, pill.offsetLeft, pill.clientWidth);
  }, [activePos, weeks.length]);

  return (
    <nav
      ref={stripRef}
      className="cm-week-strip"
      data-scroll={scrollable ? "true" : undefined}
      aria-label={openOngoing ? "Training block weeks" : "Camp weeks"}
    >
      {weeks.map((week, pos) => {
        const completion = weekCompletion(week, completionIndex);
        const phase = openOngoing
          ? OPEN_BLOCK_WEEK_LABELS[pos] || `Week ${pos + 1}`
          : resolvedWeekPhase(week);
        const index =
          typeof week.week_index === "number" && Number.isFinite(week.week_index)
            ? week.week_index
            : pos + 1;
        const selected = pos === selectedPos;
        const current = pos === currentPos;
        const phaseLabel = phase ? titleize(phase) : null;
        return (
          <button
            key={cleanText(week.week_id) || `week-${pos}`}
            type="button"
            data-week-pos={pos}
            className={`cm-week-pill${selected ? " cm-week-pill-selected" : ""}${
              current ? " cm-week-pill-current" : ""
            }`}
            aria-current={current ? "step" : undefined}
            aria-pressed={selected}
            onClick={() => onSelect(pos)}
          >
            <span className="cm-week-pill-head">
              <span className="cm-week-pill-index">W{index}</span>
              {current ? <span className="cm-week-pill-dot" aria-hidden="true" /> : null}
            </span>
            {phaseLabel ? (
              <span className="cm-week-pill-phase" title={phaseLabel}>
                {phaseLabel}
              </span>
            ) : null}
            {completion.total > 0 ? (
              <span className="cm-week-pill-completion">
                {completion.done}/{completion.total}
                <span className="sr-only"> sessions completed</span>
              </span>
            ) : null}
            {current ? <span className="sr-only">Current week</span> : null}
          </button>
        );
      })}
    </nav>
  );
}

/** The selected week's countdown/dates, work sources and app completion.
 *  The week goal is already shown in the heading via weekLabel, and the phase is
 *  already visible in the week pill, so this overview avoids repeating it. */
function WeekOverview({
  week,
  weekNumber,
  completionIndex,
  openOngoing,
  scheduleContext,
}: {
  week: StructuredWeek;
  /** 1-based position of the viewed week; drives the open-plan week intent. */
  weekNumber: number;
  completionIndex?: CompletionIndex;
  openOngoing: boolean;
  scheduleContext?: PlanScheduleContext | null;
}) {
  const completion = weekCompletion(week, completionIndex);
  const sessionSummary = weekSessionSummary(week);
  const countdownStart = formatCountdownLabel(week.countdown_start);
  const countdownEnd = formatCountdownLabel(week.countdown_end);
  const countdownRange =
    countdownStart && countdownEnd
      ? `${countdownStart} → ${countdownEnd}`
      : countdownStart || countdownEnd;
  const startDate = cleanText(week.start_date);
  const endDate = cleanText(week.end_date);
  const dateRange =
    startDate && endDate
      ? formatAppDateRange(startDate, endDate)
      : startDate || endDate
        ? formatAppDate(startDate || endDate)
        : null;

  const rows = [
    { label: "Countdown", value: countdownRange },
    { label: "Dates", value: dateRange, wide: true },
    {
      label: "App sessions",
      value: sessionSummary.appSessions > 0 ? `${sessionSummary.appSessions}` : null,
    },
    {
      label: "Coach/gym days",
      value: sessionSummary.coachLedSessions > 0 ? `${sessionSummary.coachLedSessions}` : null,
    },
    {
      label: "App completed",
      value: completion.total > 0 ? `${completion.done}/${completion.total}` : null,
      wideMobile: true,
    },
  ].filter((row) => Boolean(row.value));
  const baseHeading = weekLabel(week);
  const openWeekNumber = resolveFiniteWeekNumber(
    week.week_index,
    scheduleContext?.current_week_number,
  );
  const openWeekHeading = baseHeading.replace(
    /^Week(?:\s+\d+)?/i,
    `Week ${openWeekNumber} of 4`,
  );
  const heading = openOngoing
    ? `Block ${scheduleContext?.block_number ?? 1} · ${openWeekHeading}`
    : `Week ${weekNumber}`;
  const weekIntent = openOngoing ? openBlockWeekIntent(weekNumber) : null;

  return (
    <section className="sp-card cm-week-overview">
      <div className="cm-week-overview-head">
        <p className="sp-eyebrow">Week overview</p>
        <h2 className="sp-redflags-title">{heading}</h2>
      </div>

      {weekIntent ? (
        <p className="sp-block-purpose cm-week-intent">
          <span className="sp-tag sp-accent">{weekIntent.label}</span>
          {weekIntent.summary}
        </p>
      ) : null}

      {rows.length > 0 ? (
        <div className="sp-block-stats cm-week-overview-stats">
          {rows.map((row) => (
            <span
              key={row.label}
              className="sp-stat"
              data-wide={row.wide ? "" : undefined}
              data-wide-mobile={row.wideMobile ? "" : undefined}
            >
              <span className="sp-stat-label">{row.label}</span>
              {row.value}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function StructuredPlanRenderer({
  plan,
  openOngoing = false,
  today,
  createdAt,
  focusDay,
  currentDayLabel = "Today",
  completions,
  currentTrainingDayIso,
  scheduleContext,
  onLogSession,
  isAdmin = false,
  rehabLabelPolicy,
}: {
  plan: StructuredPlan;
  /** Renewable four-week plan without a scheduled fight date. */
  openOngoing?: boolean;
  today?: Date;
  /** Plan creation timestamp. For an open plan without a server projection it
   * anchors which week of the renewable block is current (the Monday of the week
   * the plan starts training in, mirroring the backend timeline). Not
   * rendered. */
  createdAt?: string | null;
  /** Accepted for compatibility with callers, but not rendered on this plan view. */
  planStatus?: string | null;
  /** Optional advance target: the next scheduled session's day, passed once
   * today is already logged. It moves ONLY the opened week + day highlight, never
   * the truthful current week marker. Omit it for the normal calendar view. */
  focusDay?: Date;
  /** Badge text for the highlighted day. Callers pass "Next session" alongside
   * `focusDay` so the advanced day is not mislabelled "Today". */
  currentDayLabel?: string;
  /** Live completion rows from /api/plans/{id}/completions. When present the
   * day cards colour every session from real logging instead of the static
   * generation-time statuses. */
  completions?: readonly TodaySessionCompletionRecord[] | null;
  /** Server-authoritative athlete-local training day (YYYY-MM-DD). */
  currentTrainingDayIso?: string | null;
  /** Server-derived timing projection. Open plans use it for block identity and
   * fail-closed legacy messaging; dated camps keep their existing D-X spine. */
  scheduleContext?: PlanScheduleContext | null;
  /** Opens the retro-log flow for a past, still-loggable session. */
  onLogSession?: (day: StructuredDay, session: StructuredSession, sessionId: string) => void;
  /** Whether the viewer is an admin. The raw "Original plan text" dump is an
   * internal artefact and is hidden from athletes; it still appears for admins,
   * and for anyone in the fail-closed "schedule unavailable" state where the
   * on-screen message directs the athlete to the raw plan below. */
  isAdmin?: boolean;
  /** Server-derived per-region Rehab/Prehab policy (PlanDetail.rehab_label_policy).
   * Rehab blocks whose target region is no longer injured render as "Prehab".
   * Omitted → every rehab block keeps reading "Rehab". */
  rehabLabelPolicy?: RehabLabelPolicy | null;
}) {
  const weeks = getWeeks(plan);
  const completionIndex = useMemo(
    () => (completions ? buildCompletionIndex(completions) : undefined),
    [completions],
  );

  // Resolve "today" through the shared 03:00 training-day rollover so Plan Detail
  // and the Today tab can never disagree on the current day.
  const mountedDay = useTrainingDay();
  const serverTrainingDay = useMemo(() => {
    const iso = cleanText(currentTrainingDayIso) || cleanText(scheduleContext?.current_training_day);
    if (!iso) {
      return undefined;
    }
    const parsed = new Date(`${iso.slice(0, 10)}T12:00:00`);
    return Number.isNaN(parsed.getTime()) ? undefined : parsed;
  }, [currentTrainingDayIso, scheduleContext?.current_training_day]);
  const calendarDay = today ?? serverTrainingDay ?? mountedDay;

  // Weekday-only open plans need to know which week of the renewable block is
  // current; dated camps ignore the hint (they resolve by calendar date).
  const openWeekNumber = openOngoing
    ? resolveOpenPlanWeekNumber(plan, calendarDay ?? null, {
        currentWeekNumber: scheduleContext?.current_week_number,
        anchorDate: scheduleContext?.anchor_date,
        createdAt,
      })
    : null;

  // The real calendar training day owns the truthful current week marker.
  // `focusDay` only advances the opened week/day highlight.
  const calendarProgress = resolvePlanProgress(plan, calendarDay, {
    openWeekNumber,
    allowDatedWeekdayMatch: openOngoing,
  });
  const resolvedFocusDay = focusDay
    ? resolveNextPlanFocusDay(plan, calendarDay, focusDay, {
        openWeekNumber,
        allowDatedWeekdayMatch: openOngoing,
      })
    : undefined;
  const focusProgress = resolvedFocusDay
    ? resolvePlanProgress(plan, resolvedFocusDay, {
        openWeekNumber,
        allowDatedWeekdayMatch: openOngoing,
      })
    : calendarProgress;
  // The calendar owns the truthful active week while today is inside the camp.
  // Just before a dated camp starts, there is no calendar match yet; in that
  // case the already-resolved next-session focus supplies the actionable week
  // for the red live marker. Manual week selection never changes this value.
  const activeWeekPos =
    calendarProgress.currentWeekPos ?? focusProgress.currentWeekPos;

  // `selectedPos` holds ONLY an explicit manual week choice; while it is null the
  // view auto-follows the plan's current week via the fallback in `effectivePos`
  // below (so no effect is needed to sync it, and there is no render loop).
  const [selectedPos, setSelectedPos] = useState<number | null>(null);

  // A stable identity for the current plan's week structure. When the component
  // is handed a different plan without remounting — e.g. the plan viewer swaps an
  // adapted text plan for the richer structured payload — a retained manual
  // `selectedPos` could point at a week index from the OLD structure. Reset it
  // DURING render (React's recommended "reset state on prop change" pattern):
  // this drops the stale selection before anything renders, so the wrong week is
  // never briefly shown, with no extra effect/render pass.
  const weekSignature = useMemo(
    () =>
      `${weeks.length}:` +
      weeks
        .map((week) => cleanText(week.week_id) || cleanText(week.start_date) || "")
        .join("|"),
    [weeks],
  );
  const [prevWeekSignature, setPrevWeekSignature] = useState(weekSignature);
  if (weekSignature !== prevWeekSignature) {
    setPrevWeekSignature(weekSignature);
    setSelectedPos(null);
  }

  const handleSelectWeek = (pos: number) => {
    setSelectedPos(pos);
  };

  const effectivePos = selectedPos ?? focusProgress.currentWeekPos ?? 0;
  const safePos = effectivePos >= 0 && effectivePos < weeks.length ? effectivePos : 0;
  const selectedWeek = weeks[safePos];

  const progressionNotes = cleanText(plan.progression_notes);
  const rawFallback = cleanText(plan.raw_markdown_fallback);
  const safetyOwnershipTexts = useMemo(
    () => [
      ...getSafetyPriorityTexts(plan),
      ...getActiveNotesExcludingRedFlags(plan)
        .map((note) => cleanText(note.text))
        .filter((text): text is string => text !== null),
    ],
    [plan],
  );
  // The raw plan dump is internal: athletes see the structured cards only. It
  // stays for admins, and for the fail-closed schedule-unavailable state whose
  // message tells the athlete to read the original plan below.
  const scheduleUnavailable =
    openOngoing && scheduleContext?.projection_status === "unavailable";
  const showRawFallback = Boolean(rawFallback) && (isAdmin || scheduleUnavailable);
  const hasNutritionSupport = getNutritionPhaseItems(plan).length > 0 || hasNutrition(plan);
  const hasRecoverySupport = getRecoveryPhaseItems(plan).length > 0;
  const dayList = useMemo(() => (selectedWeek ? getDays(selectedWeek) : []), [selectedWeek]);
  const dayTimeline = useMemo(
    () => buildDayTimeline(dayList, !openOngoing),
    [dayList, openOngoing],
  );
  // Calendar day a synthesized gap row should highlight. Gap days never exist
  // in the plan, so focusProgress can't mark them — compare dates directly.
  // Only in the normal (non-advanced) view, though: once the plan advances to a
  // future "Next session" (focusDay set), that future session card owns the
  // marker, so gap rows stay plain instead of stamping today with a label that
  // belongs to a different day.
  const restCurrentIso = focusDay
    ? null
    : (cleanText(currentTrainingDayIso)?.slice(0, 10) ??
      cleanText(scheduleContext?.current_training_day)?.slice(0, 10) ??
      (calendarDay ? toLocalIsoDay(calendarDay) : null));
  // Open the support phase that matches the week the athlete is viewing.
  const activeSupportPhaseKey = normalizeSupportPhaseKey(resolvedWeekPhase(selectedWeek));
  // A block that starts on a future Monday — an open plan generated late enough
  // in the week to join the next one — has no current day to mark. Say when it
  // starts rather than showing a plain week with no "Today" anywhere on it and
  // leaving the athlete to guess whether the plan is live.
  //
  // The block starts on the server's anchor (the Monday the week runs from), not
  // on the first day that happens to carry a session: a block anchored to Mon 03
  // Aug whose first session is Thursday still starts on the Monday, and saying
  // "starts Thu 06 Aug" would contradict the week it is shown above. The
  // earliest scheduled day is only a fallback for a payload with no anchor.
  const blockStartsOn = useMemo(() => {
    if (!openOngoing || activeWeekPos !== null) {
      return null;
    }
    const todayIso =
      cleanText(currentTrainingDayIso)?.slice(0, 10) ??
      cleanText(scheduleContext?.current_training_day)?.slice(0, 10) ??
      (calendarDay ? toLocalIsoDay(calendarDay) : null);
    if (!todayIso) {
      return null;
    }
    const anchorIso = cleanText(scheduleContext?.anchor_date)?.slice(0, 10);
    const startIso =
      anchorIso && ISO_DAY_PATTERN.test(anchorIso)
        ? anchorIso
        : weeks
            .flatMap((week) => getDays(week))
            .map((day) => cleanText(day.date)?.slice(0, 10))
            .filter((iso): iso is string => typeof iso === "string" && ISO_DAY_PATTERN.test(iso))
            .sort()[0];
    return startIso && startIso > todayIso
      ? { iso: startIso, relative: describeRelativeDay(startIso, todayIso) }
      : null;
  }, [
    openOngoing,
    activeWeekPos,
    currentTrainingDayIso,
    scheduleContext?.current_training_day,
    scheduleContext?.anchor_date,
    calendarDay,
    weeks,
  ]);

  return (
    <RehabLabelProvider policy={rehabLabelPolicy}>
    <PlanSourceTextContext.Provider value={rawFallback}>
    <PlanSafetyTextContext.Provider value={safetyOwnershipTexts}>
    <div className="sp-root cm-root">
      {weeks.length > 0 ? (
        <>
          {openOngoing && scheduleContext?.projection_status === "unavailable" ? (
            <section className="sp-card cm-schedule-unavailable" role="status">
              <p className="sp-eyebrow">Schedule unavailable</p>
              <p className="sp-block-purpose">
                This legacy plan could not be matched safely to weekdays. Use the original plan
                below until the schedule is rebuilt.
              </p>
            </section>
          ) : null}
          <WeekStrip
            weeks={weeks}
            selectedPos={safePos}
            currentPos={activeWeekPos}
            onSelect={handleSelectWeek}
            completionIndex={completionIndex}
            openOngoing={openOngoing}
          />

          {selectedWeek ? (
            <WeekOverview
              week={selectedWeek}
              weekNumber={safePos + 1}
              completionIndex={completionIndex}
              openOngoing={openOngoing}
              scheduleContext={scheduleContext}
            />
          ) : null}

          <div className="cm-guardrails">
            <ActiveNotesCard plan={plan} />
            <RedFlagsCard plan={plan} />
          </div>

          {blockStartsOn ? (
            <p className="sp-today-note cm-block-start" role="status">
              {`Plan starts ${formatAppDate(blockStartsOn.iso)}`}
              {blockStartsOn.relative ? ` · ${blockStartsOn.relative.toLowerCase()}` : ""}
            </p>
          ) : null}

          <div className="sp-weeks cm-days">
            {dayList.length > 0 ? (
              dayTimeline.map((entry) => {
                if (entry.kind === "gap") {
                  const gapLabel = gapDayLabel(entry.countdown);
                  return (
                    <RestDayRow
                      key={`rest-${entry.dateIso}`}
                      countdown={entry.countdown}
                      weekday={entry.weekday}
                      label={gapLabel.label}
                      reason={gapLabel.reason}
                      isCurrent={entry.dateIso === restCurrentIso}
                      currentLabel={currentDayLabel}
                    />
                  );
                }
                const { day, index } = entry;
                // Dated days match on the calendar date. A weekday-only (open
                // plan) match carries no date, so it is identified by week/day
                // position instead — only while the matched week is the one
                // being viewed.
                const isCurrent =
                  focusProgress.currentDayDate != null
                    ? cleanText(day.date)?.slice(0, 10) === focusProgress.currentDayDate
                    : focusProgress.currentWeekPos === safePos &&
                      focusProgress.currentDayPos === index &&
                      focusProgress.currentDayPos != null;

                // A pure rest day renders identically to a synthesized gap row,
                // so real and filled-in rest days read as one continuous line.
                if (!openOngoing && isPlainRestDay(day)) {
                  const restDate = cleanText(day.date);
                  return (
                    <RestDayRow
                      key={restDate || `day-${index}`}
                      countdown={formatCountdownLabel(day.countdown_label)}
                      weekday={weekdayLabel(restDate)}
                      label="Rest"
                      isCurrent={isCurrent}
                      currentLabel={currentDayLabel}
                    />
                  );
                }

                return (
                  <CampDayCard
                    key={cleanText(day.date) || `day-${index}`}
                    day={day}
                    displayDate={
                      isCurrent && focusProgress.matchType === "weekday"
                        ? focusProgress.trainingDayISO
                        : null
                    }
                    fallbackLabel={`Training day ${index + 1}`}
                    openOngoing={openOngoing}
                    weekNumber={safePos + 1}
                    isCurrent={isCurrent}
                    currentLabel={currentDayLabel}
                    defaultOpen={isCurrent || (focusProgress.currentWeekPos == null && index === 0)}
                    completionIndex={completionIndex}
                    currentTrainingDayIso={currentTrainingDayIso}
                    onLogSession={onLogSession}
                  />
                );
              })
            ) : (
              <p className="sp-muted">No days scheduled this week.</p>
            )}
          </div>
        </>
      ) : null}

      {progressionNotes ? (
        <CollapsibleSection
          title="Progression notes"
          detailLabel="notes"
          className="sp-progression"
        >
          <p className="sp-block-purpose">{progressionNotes}</p>
        </CollapsibleSection>
      ) : null}

      {hasRecoverySupport ? (
        <CollapsibleSection
          title="Recovery"
          detailLabel="recovery"
          className="cm-support-section"
        >
          <RecoveryCard
            plan={plan}
            activePhaseKey={activeSupportPhaseKey}
            openOngoing={openOngoing}
          />
        </CollapsibleSection>
      ) : null}

      {hasNutritionSupport ? (
        <CollapsibleSection
          title="Nutrition"
          detailLabel="nutrition"
          className="cm-support-section"
        >
          <NutritionCard
            plan={plan}
            activePhaseKey={activeSupportPhaseKey}
            openOngoing={openOngoing}
          />
        </CollapsibleSection>
      ) : null}

      {showRawFallback ? (
        <details className="sp-collapse cm-raw-fallback">
          <summary className="sp-collapse-summary">
            <span className="sp-collapse-title">Original plan text</span>
            <span className="sp-collapse-action">Show original</span>
          </summary>
          <div className="sp-collapse-body">
            <pre className="cm-raw-pre">{rawFallback}</pre>
          </div>
        </details>
      ) : null}
    </div>
    </PlanSafetyTextContext.Provider>
    </PlanSourceTextContext.Provider>
    </RehabLabelProvider>
  );
}
