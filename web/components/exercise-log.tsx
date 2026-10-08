"use client";

import { createContext, useContext, useId, useMemo, useState, type ReactNode } from "react";

import {
  EXERCISE_LOG_REASONS,
  EXERCISE_LOG_REASON_LABELS,
  EXERCISE_LOG_STATUS_LABELS,
  backoffLoadFor,
  buildLogEntry,
  draftFromLog,
  hasLoggableNumbers,
  isLoggableBlock,
  lastLoadFor,
  lastPerformanceFor,
  performanceSummary,
  progressionLoadFor,
  logFieldsForBlock,
  logSummary,
  loggedValues,
  withLastLoad,
  type LogDraft,
} from "@/lib/exercise-log";
import { cleanText } from "@/lib/structured-plan";
import type {
  ExerciseLogReason,
  ExerciseLogRecord,
  ExerciseLogRequest,
  ExerciseRecentLoad,
  StructuredBlock,
} from "@/lib/types";

/**
 * In-session logging for the exercise rows. The surface that owns the session
 * (Today) provides this once the session is started; everywhere else there is
 * no provider and the rows render exactly as before.
 */
export type ExerciseLogging = {
  /** Today's saved logs, keyed by block id. */
  logs: Readonly<Record<string, ExerciseLogRecord>>;
  /** Saves (or corrects) one block's log. Rejects with a message to show. */
  save: (request: Omit<ExerciseLogRequest, "plan_id">) => Promise<void>;
  /** Saves several blocks at once (all or none), e.g. what the timer recorded. */
  saveMany?: (
    requests: Omit<ExerciseLogRequest, "plan_id">[],
    options?: { keepExisting?: boolean },
  ) => Promise<void>;
  /** Pain is health data: the reason is only offered with health consent. */
  painReasonAllowed: boolean;
  /** Last weights per exercise, carried into a "done" so it never needs typing. */
  recentLoads?: readonly ExerciseRecentLoad[];
  recentPerformances?: readonly ExerciseLogRecord[];
  allowProgression?: boolean;
  /** Where a failed one-tap save on a collapsed row is reported. */
  onError?: (message: string) => void;
};

const ExerciseLogContext = createContext<ExerciseLogging | null>(null);

export function ExerciseLogProvider({
  logging,
  children,
}: {
  logging: ExerciseLogging | null;
  children: ReactNode;
}) {
  return <ExerciseLogContext.Provider value={logging}>{children}</ExerciseLogContext.Provider>;
}

function useBlockLogging(block: StructuredBlock) {
  const logging = useContext(ExerciseLogContext);
  const blockId = cleanText(block.block_id);
  const fields = useMemo(() => logFieldsForBlock(block), [block]);
  if (!logging || !blockId || !isLoggableBlock(block)) {
    return null;
  }
  return { logging, blockId, fields, log: logging.logs[blockId] ?? null };
}

/** Last time's weight as a draft-able log, or null when there is none. */
function withLastLoadRecord(
  block: StructuredBlock,
  recentLoads: readonly ExerciseRecentLoad[] | undefined,
): ExerciseLogRecord | null {
  const load = lastLoadFor(block, recentLoads);
  return load ? ({ actual: { load } } as ExerciseLogRecord) : null;
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "Could not save. Try again.";
}

/**
 * The tick at the start of a row: one tap logs the exercise as written without
 * opening it. Once logged it shows the outcome, and a tap opens the row to
 * change it.
 */
export function ExerciseLogTick({
  block,
  onOpen,
}: {
  block: StructuredBlock;
  /** Opens the row, where a saved log is changed. */
  onOpen: () => void;
}) {
  const state = useBlockLogging(block);
  const [saving, setSaving] = useState(false);
  if (!state) {
    return null;
  }
  const { logging, blockId, log } = state;
  const name = cleanText(block.display_name) || "exercise";

  async function markDone() {
    setSaving(true);
    try {
      await logging.save({
        block_id: blockId,
        ...withLastLoad(block, { status: "as_prescribed" }, logging.recentLoads, logging.recentPerformances),
      });
    } catch (caught) {
      logging.onError?.(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <button
      type="button"
      className="ex-log-tick"
      data-status={log?.status}
      disabled={saving}
      aria-label={
        log ? `${name}: ${EXERCISE_LOG_STATUS_LABELS[log.status].toLowerCase()}. Change` : `Mark ${name} done as written`
      }
      onClick={() => (log ? onOpen() : void markDone())}
    />
  );
}

/** The numbers behind a saved log on a collapsed row: "80 kg", "Changed · 3 sets". */
export function ExerciseLogBadge({ block }: { block: StructuredBlock }) {
  const state = useBlockLogging(block);
  if (!state?.log) {
    return null;
  }
  const summary = logSummary(state.fields, state.log);
  // The tick already says "done"; a line is only worth it when there is more.
  if (state.log.status === "as_prescribed" && summary === EXERCISE_LOG_STATUS_LABELS.as_prescribed) {
    return null;
  }
  return (
    <span className="ex-row-log" data-status={state.log.status}>
      {summary}
    </span>
  );
}

function ReasonChips({
  selected,
  painAllowed,
  skipped = false,
  disabled,
  onSelect,
}: {
  selected: ExerciseLogReason | null;
  painAllowed: boolean;
  /** Nobody skips an exercise because they felt strong. */
  skipped?: boolean;
  disabled: boolean;
  onSelect: (reason: ExerciseLogReason | null) => void;
}) {
  const reasons = EXERCISE_LOG_REASONS.filter(
    (reason) => (painAllowed || reason !== "pain") && !(skipped && reason === "felt_strong"),
  );
  return (
    <div className="ex-log-reasons" role="group" aria-label="Why? (optional)">
      {reasons.map((reason) => (
        <button
          key={reason}
          type="button"
          className="ex-log-chip"
          aria-pressed={selected === reason}
          disabled={disabled}
          onClick={() => onSelect(selected === reason ? null : reason)}
        >
          {EXERCISE_LOG_REASON_LABELS[reason]}
        </button>
      ))}
    </div>
  );
}

/**
 * The log controls inside an open exercise row. The prescription above it is
 * read-only; this records what was done against it.
 */
export function ExerciseLogPanel({ block }: { block: StructuredBlock }) {
  const state = useBlockLogging(block);
  const fieldId = useId();
  const [editing, setEditing] = useState(false);
  // Re-opens the choices over a saved log, to change its outcome.
  const [choosing, setChoosing] = useState(false);
  const [draft, setDraft] = useState<LogDraft>({});
  const [reason, setReason] = useState<ExerciseLogReason | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Entries far from the prescription that the athlete has been asked to confirm.
  const [confirming, setConfirming] = useState<string[] | null>(null);

  if (!state) {
    return null;
  }
  const { logging, blockId, fields, log } = state;
  const previous = lastPerformanceFor(block, logging.recentPerformances);
  const progression = progressionLoadFor(block, previous, logging.allowProgression === true);
  // Easing off is offered at any readiness; it never needs a progression rule.
  const backoff = progression ? null : backoffLoadFor(block, previous);
  const suggested = progression ?? backoff;
  const entry = buildLogEntry(fields, draft);

  function closeEditor() {
    setEditing(false);
    setChoosing(false);
    setError(null);
    setConfirming(null);
  }

  function openEditor() {
    // A fresh entry starts from last time's weight, so only a change is typed.
    setDraft(
      log ? draftFromLog(fields, log) : draftFromLog(fields, suggested
        ? { actual: { load: suggested } } as ExerciseLogRecord
        : previous?.status === "skipped" || previous?.reason === "pain" ? null : withLastLoadRecord(block, logging.recentLoads)),
    );
    setReason(log?.reason ?? null);
    setError(null);
    setConfirming(null);
    setEditing(true);
  }

  async function save(request: Omit<ExerciseLogRequest, "plan_id" | "block_id">) {
    setSaving(true);
    setError(null);
    try {
      await logging.save({ block_id: blockId, ...request });
      closeEditor();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  function saveNumbers() {
    if (entry.invalid.length > 0) {
      const labels = fields.filter((field) => entry.invalid.includes(field.key)).map((field) => field.label);
      setError(`Check ${labels.join(", ")}.`);
      return;
    }
    if (entry.outliers.length > 0 && confirming?.join("|") !== entry.outliers.join("|")) {
      setError(null);
      setConfirming(entry.outliers);
      return;
    }
    void save({
      status: entry.status,
      actual: entry.actual,
      reason: entry.status === "modified" ? reason : null,
    });
  }

  const alert = error ? (
    <p className="form-error ex-log-error" role="alert">
      {error}
    </p>
  ) : null;

  if (editing) {
    return (
      <div className="ex-log" data-mode="numbers">
        <div className="ex-log-fields" data-count={fields.length}>
          {fields.map((field) => (
            <label key={field.key} className="ex-log-field" htmlFor={`${fieldId}-${field.key}`}>
              <span className="ex-log-field-label">
                {field.label}
                {field.unit ? <span className="ex-log-field-unit"> {field.unit}</span> : null}
              </span>
              <input
                id={`${fieldId}-${field.key}`}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                enterKeyHint="done"
                maxLength={7}
                value={draft[field.key] ?? ""}
                placeholder={field.hint ?? "–"}
                aria-invalid={entry.invalid.includes(field.key) || undefined}
                disabled={saving}
                onChange={(event) => {
                  setDraft((current) => ({ ...current, [field.key]: event.target.value }));
                  setConfirming(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    saveNumbers();
                  }
                }}
              />
            </label>
          ))}
        </div>
        {entry.status === "modified" ? (
          <ReasonChips
            selected={reason}
            painAllowed={logging.painReasonAllowed}
            disabled={saving}
            onSelect={setReason}
          />
        ) : null}
        {confirming ? (
          <p className="ex-log-confirm" role="alert">
            {confirming.join("; ")}?
          </p>
        ) : null}
        {alert}
        <div className="ex-log-bar">
          <button type="button" className="ex-log-link" disabled={saving} onClick={closeEditor}>
            Cancel
          </button>
          <button type="button" className="ex-log-save" disabled={saving} onClick={saveNumbers}>
            {saving ? "Saving…" : confirming ? "Yes, save" : "Save"}
          </button>
        </div>
      </div>
    );
  }

  if (log && !choosing) {
    const values = log.status === "skipped" ? [] : loggedValues(fields, log);
    return (
      <div className="ex-log" data-mode="saved">
        {/* The whole line reopens the log, so it keeps the row's full width. */}
        <button
          type="button"
          className="ex-log-edit"
          disabled={saving}
          aria-label={`${[
            EXERCISE_LOG_STATUS_LABELS[log.status],
            ...values.map((value) => (value.insteadOf ? `${value.text} not ${value.insteadOf}` : value.text)),
            ...(log.reason && log.status !== "skipped" ? [EXERCISE_LOG_REASON_LABELS[log.reason]] : []),
          ].join(", ")}. Change`}
          onClick={() => setChoosing(true)}
        >
          <span className="ex-log-status" data-status={log.status}>
            <span className="ex-log-status-label">{EXERCISE_LOG_STATUS_LABELS[log.status]}</span>
            {values.map((value) => (
              <span key={value.key} className="ex-log-status-value">
                {value.text}
                {value.insteadOf ? <span className="ex-log-instead"> not {value.insteadOf}</span> : null}
              </span>
            ))}
            {log.reason && log.status !== "skipped" ? (
              <span className="ex-log-status-value">{EXERCISE_LOG_REASON_LABELS[log.reason]}</span>
            ) : null}
          </span>
          <svg className="ex-log-edit-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3Z" />
            <path d="m14.5 7.5 3 3" />
          </svg>
        </button>
        {/* A skip saves in one tap; why is a second, optional tap. */}
        {log.status === "skipped" ? (
          <ReasonChips
            selected={log.reason}
            painAllowed={logging.painReasonAllowed}
            skipped
            disabled={saving}
            onSelect={(next) => void save({ status: "skipped", reason: next })}
          />
        ) : null}
        {alert}
      </div>
    );
  }

  return (
    <div className="ex-log" data-mode="idle">
      {previous ? <p className="muted ex-log-previous">
        Last: {performanceSummary(previous)}
        {suggested ? <span className="ex-log-suggestion"> · {backoff ? "Ease to" : "Try"} {suggested.value} {suggested.unit}</span> : null}
      </p> : null}
      <div className="ex-log-choices">
        <button
          type="button"
          className="ex-log-choice ex-log-choice-primary"
          disabled={saving}
          onClick={() => void save(withLastLoad(block, { status: "as_prescribed" }, logging.recentLoads, logging.recentPerformances))}
        >
          Done
        </button>
        {hasLoggableNumbers(fields) ? (
          <button type="button" className="ex-log-choice" disabled={saving} onClick={openEditor}>
            Log numbers
          </button>
        ) : null}
        <button
          type="button"
          className="ex-log-choice"
          disabled={saving}
          onClick={() => void save({ status: "skipped" })}
        >
          Skip
        </button>
        {log ? (
          <button type="button" className="ex-log-link" disabled={saving} onClick={closeEditor}>
            Cancel
          </button>
        ) : null}
      </div>
      {alert}
    </div>
  );
}
