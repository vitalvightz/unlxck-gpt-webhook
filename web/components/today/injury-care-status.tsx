"use client";

import { useRef, useState } from "react";
import { submitInjuryEpisodeObservation } from "@/lib/api";
import type { InjuryFlagRecord, TodayCommandView } from "@/lib/types";

export function EffectiveClinicianClearanceStatus({ clearance }: {
  clearance: TodayCommandView["effective_clinician_clearance"];
}) {
  if (!clearance) return null;
  const label = { rehab_only: "Rehab only", train_no_contact: "Train, no hard sparring", train_contact: "Train + hard sparring" }[clearance.level];
  return <div className="today-injury-guidance" role="note" aria-label="Effective clinician clearance">
    <p><strong>Reported clearance: {label}</strong> <small className="muted">· {clearance.level === "train_contact" ? "based on" : "limited by"} {clearance.limited_by.map(injury => injury.label).join(", ")}</small></p>
    {clearance.requires_update ? <p>Scope unclear. Rehab only until clarified.</p> : null}
  </div>;
}

export function InjuryCareStatus({ injury, token, onRefresh }: {
  injury: InjuryFlagRecord; token: string; onRefresh: () => Promise<void>;
}) {
  const [choosing, setChoosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pendingReport = useRef<{ key: string; id: string } | null>(null);
  async function report(scopes: Array<"rehab" | "training" | "contact">) {
    if (!injury.episode_id || busy) return;
    setBusy(true); setError("");
    try {
      const key = `${injury.episode_id}:${scopes.join(",")}`;
      if (pendingReport.current?.key !== key) pendingReport.current = { key, id: crypto.randomUUID() };
      await submitInjuryEpisodeObservation(token, { injury_id: injury.id, injury_episode_id: injury.episode_id,
        event_type: "clinician_clearance_report", scopes, report_id: pendingReport.current.id });
      await onRefresh();
      pendingReport.current = null;
      setChoosing(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save your report."); }
    finally { setBusy(false); }
  }
  const clearance = injury.clinician_clearance;
  const scopeLabels: Record<string, string> = {
    rehab: "Rehab only",
    "rehab,training": "Train, no hard sparring",
    "contact,rehab,training": "Train + hard sparring",
  };
  const scopeLabel = scopeLabels[[...(clearance?.scopes ?? [])].sort().join(",")]
    ?? "Scope unclear — update required";
  const surface = injury.rehab_decision?.outcome === "wound_care" || Boolean(injury.surface_class && injury.surface_class !== "non_surface");
  const schedule = injury.rehab_decision?.schedule;
  const labels = { due: "Rehab due", recovery_day: "Recovery day", already_completed: "Today's allocation used",
    held: "Rehab held", deferred: "Rehab deferred", unsupported: "Guidance unavailable" };
  return <div className="today-injury-guidance" role="note">
    {injury.rehab_decision && schedule?.reason !== injury.rehab_decision.summary ? <p>{injury.rehab_decision.summary}</p> : null}
    {schedule ? <p><strong>{labels[schedule.state]}</strong> · {schedule.reason}
      {schedule.next_due_day && schedule.state !== "due" ? <> Next due: {schedule.next_due_day}.</> : null}</p> : null}
    {injury.rehab_decision?.prescription?.sources?.length ? <p className="muted">
      {injury.rehab_decision.prescription.sources.map((source, index) => <span key={source}>
        {index ? " · " : ""}<a href={source} target="_blank" rel="noopener noreferrer">Routine guidance{index ? ` ${index + 1}` : ""}</a>
      </span>)}
    </p> : null}
    {clearance || (injury.episode_id && !surface) ? <div className="today-injury-clearance-row">
      {clearance ? <p className="muted">Your clearance: {scopeLabel}</p> : null}
      {injury.episode_id && !surface ? <button type="button" className="gi-change-btn" onClick={() => setChoosing(!choosing)} disabled={busy}>{clearance ? "Change clearance" : "Add clinician clearance"}</button> : null}
    </div> : null}
    {injury.episode_id && !surface ? <>
      {choosing ? <div role="group" aria-label="What were you cleared for?">
        <p>What were you cleared for? <small className="muted">Self-reported. Red flags and safety holds still apply; doesn&apos;t advance rehab.</small></p>
        <div className="today-segment-row">
          <button type="button" className="today-segment" disabled={busy} onClick={() => report(["rehab"])}>Rehab only</button>
          <button type="button" className="today-segment" disabled={busy} onClick={() => report(["rehab", "training"])}>Train, no hard sparring</button>
          <button type="button" className="today-segment" disabled={busy} onClick={() => report(["rehab", "training", "contact"])}>Train + hard sparring</button>
        </div>
      </div> : null}
    </> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}

export function DelayedRehabResponse({ prompt, token, onRefresh }: {
  prompt: NonNullable<TodayCommandView["delayed_rehab_prompts"]>[number];
  token: string; onRefresh: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  async function answer(response: typeof prompt.options[number]) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await submitInjuryEpisodeObservation(token, { injury_id: prompt.injury_id, injury_episode_id: prompt.injury_episode_id,
        event_type: "delayed_rehab_response", exposure_id: prompt.exposure_id, response });
      setSaved(true);
      await onRefresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save your response."); }
    finally { setBusy(false); }
  }
  if (saved) return <p role="status">Next-day response saved.</p>;
  return <div className="today-injury-guidance" role="group" aria-label={`Next-day response for ${prompt.region}`}>
    <p>{prompt.question} <strong>{prompt.region}</strong></p>
    <div className="today-segment-row">
      {prompt.options.map(option => <button key={option} type="button" className="today-segment" disabled={busy} onClick={() => answer(option)}>
        {({ better: "Better", same: "Same", worse: "Worse", not_sure: "Not sure" })[option]}
      </button>)}
    </div>
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}
