"use client";

import { useId, useRef, useState } from "react";
import { ApiError, submitInjuryEpisodeObservation } from "@/lib/api";
import type { InjuryFlagRecord, TodayCommandView } from "@/lib/types";

const SCHEDULE_LABELS = { due: "Rehab due today", recovery_day: "Rest day", already_completed: "Done for today",
  held: "Rehab on hold", deferred: "Rehab moved", unsupported: "No rehab yet" } as const;
const ROUTINE_SCHEDULE_STATES = new Set<string>(["due", "recovery_day", "already_completed"]);
const NEXT_DAY_FORMAT = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "Sat 10 Oct" for an ISO training day; the raw value if it does not parse. */
function formatNextDay(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? day : NEXT_DAY_FORMAT.format(date).replace(",", "");
}

export function EffectiveClinicianClearanceStatus({ clearance }: {
  clearance: TodayCommandView["effective_clinician_clearance"];
}) {
  if (!clearance) return null;
  const label = { rehab_only: "Rehab only", train_no_contact: "Non-contact training", train_contact: "Contact training" }[clearance.level];
  return <div className="today-injury-guidance" role="note" aria-label="Effective clinician clearance">
    <p><strong>Reported clearance: {label}</strong> <small className="muted">· {clearance.level === "train_contact" ? "based on" : "limited by"} {clearance.limited_by.map(injury => injury.label).join(", ")}</small></p>
    {clearance.requires_update ? <p>Scope unclear. Rehab only until clarified.</p> : null}
  </div>;
}

export function InjuryCareStatus({ injury, token, onRefresh }: {
  injury: InjuryFlagRecord; token: string; onRefresh: () => Promise<void>;
}) {
  const [choosing, setChoosing] = useState(false);
  const [rehabLevel, setRehabLevel] = useState<"gentle_recovery" | "loading" | "sport_specific" | "not_cleared">("not_cleared");
  const [trainingLevel, setTrainingLevel] = useState("rehab");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const clearanceEditorId = useId();
  const pendingReport = useRef<{ key: string; id: string } | null>(null);
  async function report() {
    const scopes: Array<"rehab" | "training" | "contact"> = trainingLevel === "contact" ? ["rehab", "training", "contact"] : trainingLevel === "training" ? ["rehab", "training"] : ["rehab"];
    if (!injury.episode_id || busy) return;
    setBusy(true); setError("");
    try {
      const key = `${injury.episode_id}:${scopes.join(",")}:${rehabLevel}`;
      if (pendingReport.current?.key !== key) pendingReport.current = { key, id: crypto.randomUUID() };
      await submitInjuryEpisodeObservation(token, { injury_id: injury.id, injury_episode_id: injury.episode_id,
        event_type: "clinician_clearance_report", scopes, rehabilitation_permission: { schema_version: 1, level: rehabLevel }, report_id: pendingReport.current.id });
      await onRefresh();
      pendingReport.current = null;
      setChoosing(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save your report."); }
    finally { setBusy(false); }
  }
  const clearance = injury.clinician_clearance;
  const scopeLabels: Record<string, string> = {
    rehab: "Rehab only",
    "rehab,training": "Non-contact training",
    "contact,rehab,training": "Contact training",
  };
  const scopeLabel = scopeLabels[[...(clearance?.scopes ?? [])].sort().join(",")]
    ?? "Scope unclear — update required";
  const surface = injury.rehab_decision?.outcome === "wound_care" || Boolean(injury.surface_class && injury.surface_class !== "non_surface");
  const schedule = injury.rehab_decision?.schedule;
  const summary = injury.rehab_decision?.reason_codes.includes("missing_injury_identity")
    ? "Add injury area and type to unlock rehab guidance."
    : injury.rehab_decision?.summary;
  // Routine states say everything in their label, so their backend reason
  // ("You have already logged rehab for this injury today.") is not repeated.
  // Held, deferred and unsupported keep it: it says why.
  const routine = schedule ? ROUTINE_SCHEDULE_STATES.has(schedule.state) : false;
  const scheduleLabel = schedule
    ? schedule.state === "already_completed" && /started session/i.test(schedule.reason)
      ? "In today's session"
      : SCHEDULE_LABELS[schedule.state]
    : "";
  const scheduleReason = !schedule || routine ? ""
    : schedule.reason === injury.rehab_decision?.summary ? summary ?? "" : schedule.reason;
  // A matched routine's summary ("Your rehab is matched…") only restates that
  // there is a schedule; the schedule line carries the state instead.
  const showSummary = Boolean(summary) && !(injury.rehab_decision?.outcome === "prescribed_rehab" && schedule)
    && summary !== scheduleReason;
  return <div className="today-injury-care">
    {injury.rehab_decision ? <div className="today-injury-care-section" role="note" aria-label="Guidance">
    <p className="today-field-label">Guidance</p>
    {showSummary ? <p>{summary}</p> : null}
    {schedule ? <p><strong>{scheduleLabel}</strong>
      {schedule.next_due_day && schedule.state !== "due" ? <span className="muted"> · Next {formatNextDay(schedule.next_due_day)}</span> : null}</p> : null}
    {scheduleReason ? <p className="muted">{scheduleReason}</p> : null}
    {injury.rehab_decision?.prescription?.sources?.length ? <p className="muted">
      {injury.rehab_decision.prescription.sources.map((source, index) => <span key={source}>
        {index ? " · " : ""}<a href={source} target="_blank" rel="noopener noreferrer">Routine guidance{index ? ` ${index + 1}` : ""}</a>
      </span>)}
    </p> : null}
    </div> : null}
    {clearance || (injury.episode_id && !surface) ? <div className="today-injury-care-section today-injury-clearance">
    <div className="today-injury-clearance-head">
      <div>
        <p className="today-field-label">Clinical Clearance <small>Self-reported</small></p>
        <p>{clearance ? `${({ gentle_recovery: "Gentle recovery", loading: "Strengthening / loading", sport_specific: "Sport-specific rehab", not_cleared: "Not sure / not cleared" })[clearance.rehabilitation_permission?.level ?? "not_cleared"]} · ${scopeLabel}` : "Not reported"}</p>
        <p className="today-field-hint">Based on what you say your clinician advised. Unlxck does not issue or verify medical clearance. Update only when their advice changes.</p>
      </div>
    {injury.episode_id && !surface ? <>
      <button type="button" className="today-injury-clearance-toggle" aria-expanded={choosing} aria-controls={clearanceEditorId}
        onClick={() => { if (!choosing) { setRehabLevel(clearance?.rehabilitation_permission?.level ?? "not_cleared"); setTrainingLevel(clearance?.scopes.includes("contact") ? "contact" : clearance?.scopes.includes("training") ? "training" : "rehab"); } setChoosing((current) => !current); }} disabled={busy}>{choosing ? "Hide" : clearance ? "Change clearance" : "Report clearance"}</button>
    </> : null}
    </div>
    {choosing ? <div id={clearanceEditorId} className="today-injury-clearance-editor" role="group" aria-label="What were you cleared for?">
      <p className="today-field-hint">Injury restrictions and safety holds still apply.</p>
      <div className="field">
        <label htmlFor={`${clearanceEditorId}-rehab`}>Rehabilitation level</label>
        <select id={`${clearanceEditorId}-rehab`} value={rehabLevel} disabled={busy} onChange={e => setRehabLevel(e.target.value as typeof rehabLevel)}>
          <option value="gentle_recovery">Gentle recovery</option>
          <option value="loading">Strengthening / loading</option>
          <option value="sport_specific">Sport-specific rehab</option>
          <option value="not_cleared">Not sure / not cleared</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${clearanceEditorId}-training`}>Training level</label>
        <select id={`${clearanceEditorId}-training`} value={trainingLevel} disabled={busy} onChange={e => setTrainingLevel(e.target.value)}>
          <option value="rehab">Rehab only</option>
          <option value="training">Non-contact training</option>
          <option value="contact">Contact training</option>
        </select>
      </div>
      <button type="button" className="secondary-button" disabled={busy} onClick={() => report()}>{busy ? "Saving…" : "Save clearance"}</button>
    </div> : null}
    </div> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}

export function DelayedRehabResponse({ prompt, token, onRefresh }: {
  prompt: NonNullable<TodayCommandView["delayed_rehab_prompts"]>[number];
  token: string; onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [closed, setClosed] = useState(false);
  const [error, setError] = useState("");
  async function answer(response: typeof prompt.options[number]) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await submitInjuryEpisodeObservation(token, { injury_id: prompt.injury_id, injury_episode_id: prompt.injury_episode_id,
        event_type: "delayed_rehab_response", exposure_id: prompt.exposure_id, response });
      setSaved(true);
      await onRefresh();
    } catch (e) {
      // 409: the question is not open (yet or any more), e.g. a Today screen
      // loaded before a day rollover or a deploy. Drop it instead of showing a
      // raw server error; the refresh brings back the correct prompts.
      if (e instanceof ApiError && e.status === 409) {
        setClosed(true);
        await onRefresh().catch(() => {});
      } else {
        setError(e instanceof Error ? e.message : "Could not save your response.");
      }
    }
    finally { setBusy(false); }
  }
  if (closed) return null;
  if (saved) return <p role="status">Saved. Thanks.</p>;
  return <div className="today-injury-guidance" role="group" aria-label={`Next-day response for ${prompt.region}`}>
    <p>How&apos;s your <strong>{prompt.region.toLowerCase()}</strong> after yesterday&apos;s rehab?</p>
    <div className="today-segment-row">
      {prompt.options.map(option => <button key={option} type="button" className="today-segment" disabled={busy} onClick={() => answer(option)}>
        {({ better: "Better", same: "Same", worse: "Worse", not_sure: "Not sure" })[option]}
      </button>)}
    </div>
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}
