"use client";

import { createContext, useContext, useId, useMemo, useState, type ReactNode } from "react";

import {
  EXERCISE_LOG_REASONS,
  EXERCISE_LOG_REASON_LABELS,
  buildLogEntry,
  draftFromLog,
  hasLoggableNumbers,
  isLoggableBlock,
  logFieldsForBlock,
  logSummary,
  loggedValues,
  type LogDraft,
  type LogField,
} from "@/lib/exercise-log";
import { cleanText } from "@/lib/structured-plan";
import type {
  ExerciseLogReason,
  ExerciseLogRecord,
  ExerciseLogRequest,
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
  /** Pain is health data: the reason is only offered with health consent. */
  painReasonAllowed: boolean;
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

/** The saved outcome on a collapsed row: "Done · 80 kg", "Changed · 3 sets", "Skipped". */
export function ExerciseLogBadge({ block }: { block: StructuredBlock }) {
  const state = useBlockLogging(block);
  if (!state?.log) {
    return null;
  }
  return (
    <span className="ex-row-log" data-status={state.log.status}>
      {logSummary(state.fields, state.log)}
    </span>
  );
}

function ReasonChips({
  selected,
  painAllowed,
  disabled,
  onSelect,
}: {
  selected: ExerciseLogReason | null;
  painAllowed: boolean;
  disabled: boolean;
  onSelect: (reason: ExerciseLogReason | null) => void;
}) {
  const legendId = useId();
  const reasons = EXERCISE_LOG_REASONS.filter((reason) => painAllowed || reason !== "pain");
  return (
    <div className="ex-log-reason">
      <p className="sp-stat-label" id={legendId}>
        Why? (optional)
      </p>
      <div className="feedback-chips" role="group" aria-labelledby={legendId}>
        {reasons.map((reason) => (
          <button
            key={reason}
            type="button"
            className={selected === reason ? "feedback-chip is-selected" : "feedback-chip"}
            aria-pressed={selected === reason}
            disabled={disabled}
            onClick={() => onSelect(selected === reason ? null : reason)}
          >
            {EXERCISE_LOG_REASON_LABELS[reason]}
          </button>
        ))}
      </div>
    </div>
  );
}

function SavedLog({
  fields,
  log,
  disabled,
  onEdit,
}: {
  fields: LogField[];
  log: ExerciseLogRecord;
  disabled: boolean;
  onEdit: () => void;
}) {
  const values = log.status === "skipped" ? [] : loggedValues(fields, log);
  const heading =
    log.status === "skipped" ? "Skipped" : log.status === "modified" ? "You changed it" : "Done as written";
  return (
    <>
      <div className="ex-log-result">
        <p className="ex-log-status" data-status={log.status}>
          {heading}
          {log.reason ? <span className="ex-log-status-reason"> · {EXERCISE_LOG_REASON_LABELS[log.reason]}</span> : null}
        </p>
        <button type="button" className="ex-log-edit" disabled={disabled} onClick={onEdit}>
          Edit
        </button>
      </div>
      {values.length > 0 ? (
        <dl className="ex-log-values">
          {values.map((value) => (
            <div key={value.key} className="ex-log-value" data-changed={value.insteadOf ? "true" : undefined}>
              <dt className="sp-stat-label">{value.label}</dt>
              <dd>
                {value.value}
                {value.insteadOf ? <span className="ex-log-instead"> not {value.insteadOf}</span> : null}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </>
  );
}

/**
 * The log controls inside an open exercise row. The prescription above it is
 * read-only; this records what was done against it.
 */
export function ExerciseLogPanel({ block }: { block: StructuredBlock }) {
  const state = useBlockLogging(block);
  const fieldId = useId();
  // "choose" re-opens the three choices over a saved log, to change its outcome.
  const [mode, setMode] = useState<"idle" | "choose" | "numbers" | "skip">("idle");
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
  const entry = buildLogEntry(fields, draft);

  function close() {
    setMode("idle");
    setError(null);
    setConfirming(null);
  }

  function open(next: "numbers" | "skip") {
    setDraft(next === "numbers" ? draftFromLog(fields, log) : {});
    setReason(log?.reason ?? null);
    setError(null);
    setConfirming(null);
    setMode(next);
  }

  async function save(request: Omit<ExerciseLogRequest, "plan_id" | "block_id">) {
    setSaving(true);
    setError(null);
    try {
      await logging.save({ block_id: blockId, ...request });
      close();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save. Try again.");
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

  if (mode === "numbers") {
    return (
      <div className="ex-log" data-mode="numbers">
        <p className="ex-log-title">What you did</p>
        <p className="ex-log-help">Only fill in what was different. Empty means as written.</p>
        <div className="ex-log-fields">
          {fields.map((field) => (
            <label key={field.key} className="ex-log-field" htmlFor={`${fieldId}-${field.key}`}>
              <span className="sp-stat-label">
                {field.label}
                {field.unit ? ` (${field.unit})` : ""}
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
            {confirming.join("; ")}. Save it if that is right.
          </p>
        ) : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="ex-log-actions">
          <button type="button" className="ghost-button" disabled={saving} onClick={close}>
            Cancel
          </button>
          <button type="button" className="cta" disabled={saving} onClick={saveNumbers}>
            {saving ? "Saving…" : confirming ? "Yes, save" : "Save"}
          </button>
        </div>
      </div>
    );
  }

  if (mode === "skip") {
    return (
      <div className="ex-log" data-mode="skip">
        <p className="ex-log-title">Skip this exercise</p>
        <ReasonChips
          selected={reason}
          painAllowed={logging.painReasonAllowed}
          disabled={saving}
          onSelect={setReason}
        />
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="ex-log-actions">
          <button type="button" className="ghost-button" disabled={saving} onClick={close}>
            Cancel
          </button>
          <button
            type="button"
            className="cta"
            disabled={saving}
            onClick={() => void save({ status: "skipped", reason })}
          >
            {saving ? "Saving…" : "Save skip"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="ex-log" data-mode="idle" data-logged={log ? "true" : undefined}>
      {log && mode !== "choose" ? (
        <SavedLog fields={fields} log={log} disabled={saving} onEdit={() => setMode("choose")} />
      ) : (
        <>
          <p className="ex-log-title">{log ? "Change this log" : "Log it"}</p>
          <div className="ex-log-choices">
            <button
              type="button"
              className="ex-log-choice ex-log-choice-primary"
              disabled={saving}
              onClick={() => void save({ status: "as_prescribed" })}
            >
              {saving ? "Saving…" : "Done as written"}
            </button>
            {hasLoggableNumbers(fields) ? (
              <button type="button" className="ex-log-choice" disabled={saving} onClick={() => open("numbers")}>
                Log numbers
              </button>
            ) : null}
            <button type="button" className="ex-log-choice" disabled={saving} onClick={() => open("skip")}>
              Skipped
            </button>
            {log ? (
              <button type="button" className="ex-log-edit" disabled={saving} onClick={close}>
                Cancel
              </button>
            ) : null}
          </div>
        </>
      )}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
