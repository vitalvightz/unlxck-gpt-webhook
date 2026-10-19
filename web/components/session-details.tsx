"use client";

import { useEffect, useId, useRef, useState } from "react";
import { getSessionDetails } from "@/lib/api";
import type { SessionDetailBlock, SessionDetails as Details } from "@/lib/api-schema.generated";
import { formatAppDate } from "@/lib/date-format";
import { sessionStatusLabel } from "@/lib/history";
import { EXERCISE_LOG_REASON_LABELS } from "@/lib/exercise-log";
import type { ExerciseLogReason } from "@/lib/types";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import { detailMeasurements } from "@/lib/session-details";
import { sessionTypes, sportLabel } from "@/lib/training-disciplines";
import type { TrainingHistorySession } from "@/lib/training-history";
import styles from "./session-details.module.css";

export type SessionDetailsCache = Map<string, Promise<Details>>;
const OUTCOMES = { as_prescribed: "Completed as prescribed", modified: "Modified", skipped: "Skipped",
  done_as_shown: "Done as shown", changed: "Changed", stopped: "Stopped" };

function Measurements({ values }: { values: Record<string, unknown> }) {
  const items = detailMeasurements(values);
  return items.length ? <dl className={styles.measurements}>{items.map(item => <div key={item.label}>
    <dt>{item.label}</dt><dd>{item.value}</dd>
  </div>)}</dl> : <p className={styles.quiet}>No values recorded.</p>;
}

function TrainingBlock({ block, index }: { block: SessionDetailBlock; index: number }) {
  const rehab = block.kind !== "exercise";
  const actuals = detailMeasurements(block.actual).length > 0;
  const quantified = block.completed_dose?.completion_state === "quantified";
  return <li className={styles.block}>
    <div className={styles.blockHeading}><span className={styles.number}>{String(index + 1).padStart(2, "0")}</span>
      <h4>{block.name}</h4></div>
    <p className={styles.outcome}>{block.kind === "guidance" ? "Guidance · " : ""}{block.status ? OUTCOMES[block.status] : "Completion not recorded"}</p>
    <div className={styles.comparison}>
      <section aria-label={`Prescribed: ${block.name}`}><h5>{block.kind === "guidance" ? "Saved guidance" : "Prescribed"}</h5><Measurements values={block.prescribed} /></section>
      {block.kind !== "guidance" ? <section aria-label={`Performance: ${block.name}`}><h5>{rehab ? "Confirmed completed dose" : "Reported"}</h5>
        {rehab ? quantified ? <Measurements values={block.completed_dose!} /> : <p className={styles.quiet}>{block.status === "skipped" ? "Skipped. No completed dose recorded." : "Completed amount unknown."}</p>
          : actuals ? <><Measurements values={block.actual} /><p className={styles.quiet}>{block.status === "as_prescribed" ? "Other prescribed values confirmed as completed." : "Other performed values are unknown."}</p></>
          : <p className={styles.quiet}>{block.status === "as_prescribed" ? "Confirmed completed as prescribed. No separate values logged." : block.status === "skipped" ? "Skipped. No performance values logged." : "Performed values unknown."}</p>}
      </section> : null}
    </div>
    {block.reason ? <p className={styles.note}>{EXERCISE_LOG_REASON_LABELS[block.reason as ExerciseLogReason] || block.reason}</p> : null}
    {block.notes ? <p className={styles.note}>{block.notes}</p> : null}
    {block.responses.map((response, i) => <div key={i} className={styles.response} aria-label="Recorded rehab response">
      <span>Recorded response for the rehab work</span>
      {response.during_response !== "not_reported" ? <p>During: {response.during_response.replaceAll("_", " ")}</p> : null}
      {response.stopped_due_to_symptoms != null ? <p>{response.stopped_due_to_symptoms ? "Reduced or stopped because of symptoms." : "No reduction or stop reported."}</p> : null}
      {response.pain_during != null ? <p>Pain during: {typeof response.pain_during === "number" ? `${response.pain_during}/10` : "Not sure"}</p> : null}
      {response.pain_immediate_after != null ? <p>Pain after: {typeof response.pain_immediate_after === "number" ? `${response.pain_immediate_after}/10` : "Not sure"}</p> : null}
      {response.next_day_response !== "not_yet_known" ? <p>Next day: {response.next_day_response.replaceAll("_", " ")}</p> : null}
      {response.worsening_reported != null ? <p>Worsening reported: {response.worsening_reported ? "Yes" : "No"}</p> : null}
    </div>)}
  </li>;
}

/** Native modal supplies focus containment, inert background and Escape handling. */
export function SessionDetails({ row, token, cache, onDismiss }: {
  row: TrainingHistorySession; token: string; cache: SessionDetailsCache; onDismiss: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const [details, setDetails] = useState<Details | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal();
    element.querySelector<HTMLButtonElement>("button")?.focus();
    const release = lockOverlayScroll();
    return () => { element.close(); release(); previous?.focus(); };
  }, []);
  useEffect(() => {
    let cancelled = false;
    const key = `${row.source}:${row.id}`;
    let request = cache.get(key);
    if (!request) {
      request = getSessionDetails(token, row.source, row.id);
      cache.set(key, request);
    }
    void request.then(result => { if (!cancelled) setDetails(result); }).catch(() => {
      if (cache.get(key) === request) cache.delete(key);
      if (!cancelled) setError(true);
    });
    return () => { cancelled = true; };
  }, [row.id, row.source, token, cache, attempt]);
  const record = details?.session;
  return <dialog ref={dialog} className={styles.dialog} aria-labelledby={heading}
    onCancel={event => { event.preventDefault(); onDismiss(); }}
    onClick={event => { if (event.target === event.currentTarget) {
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onDismiss();
    } }}>
    <header className={styles.header}><div><p className={styles.eyebrow}>Session details</p>
      <h2 id={heading}>{record?.title || row.title}</h2><p className={styles.quiet}>{formatAppDate(record?.training_day || row.training_day)}</p></div>
      <button type="button" className={styles.close} aria-label="Close session details" onClick={onDismiss}>×</button></header>
    <div className={styles.body} tabIndex={0} role="region" aria-label="Session record">
      {!details && !error ? <p role="status">Loading session details…</p> : null}
      {error ? <div role="alert"><p>Unable to load session details. Try again.</p><button type="button" className="secondary-button" onClick={() => { setError(false); setAttempt(value => value + 1); }}>Retry</button></div> : null}
      {details && record ? <>
        <div className={styles.meta}><span>{sessionStatusLabel(record.status)}</span><span>{record.source === "external" ? "Added by you" : "Unlxck"}</span>
          {record.duration_minutes != null ? <span>{record.duration_minutes} min recorded</span> : null}
          {record.session_rpe != null ? <span>RPE {record.session_rpe}/10</span> : null}
          {record.effort ? <span>Effort: {record.effort}</span> : null}</div>
        {record.source === "external" ? <section className={styles.section}><h3>Training recorded</h3>
          <dl className={styles.measurements}>
            {record.activity ? <div><dt>Activity</dt><dd>{record.activity}</dd></div> : null}
            {record.sport ? <div><dt>Sport</dt><dd>{sportLabel(record.sport)}</dd></div> : null}
            {record.session_type ? <div><dt>Session type</dt><dd>{sessionTypes(record.sport).find(item => item.id === record.session_type)?.label || record.session_type.replaceAll("_", " ")}</dd></div> : null}
          </dl><p className={styles.quiet}>Exercise-level records weren’t captured for manually logged training.</p>
          {details.sparring ? <><h3>Sparring report</h3><p>{details.sparring.rounds_completed} rounds{details.sparring.round_seconds != null ? ` · ${details.sparring.round_seconds} sec` : ""} · {details.sparring.intensity}</p>
            {details.sparring.head_contact ? <p>Head contact: {details.sparring.head_contact}</p> : null}
            {details.sparring.rocked != null ? <p>Rocked: {details.sparring.rocked ? "Yes" : "No"}</p> : null}
            {details.sparring.notes ? <p className={styles.note}>{details.sparring.notes}</p> : null}</> : null}
        </section> : <section className={styles.section}><h3>Exercises & training blocks</h3>
          {details.prescription_source === "exercise_logs" ? <p className={styles.quiet}>Saved exercise logs only. The full prescription and original block order are unavailable.</p> : null}
          {details.blocks.length ? <ol className={styles.blocks}>{details.blocks.map((block, index) => <TrainingBlock key={index} block={block} index={index} />)}</ol> : null}
        </section>}
        {details.message ? <p className={styles.quiet}>{details.message}</p> : null}
        {record.pain_after != null || record.notes || record.modification_reason || record.takeaway ? <section className={styles.section}><h3>Session feedback</h3>
          {record.pain_after != null ? <p>Pain after: {record.pain_after}/10</p> : null}
          {record.modification_reason ? <p className={styles.note}>Modification: {record.modification_reason}</p> : null}
          {record.notes ? <p className={styles.note}>{record.notes}</p> : null}
          {record.takeaway ? <p className={styles.note}>Takeaway: {record.takeaway}</p> : null}</section> : null}
      </> : null}
    </div>
  </dialog>;
}
