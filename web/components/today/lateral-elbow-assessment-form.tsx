"use client";

import { useId, useRef, useState } from "react";
import { submitInjuryEpisodeObservation } from "@/lib/api";
import type { LateralElbowProgressionAssessment, LateralElbowProgressionInput } from "@/lib/api-schema.generated";
import type { InjuryFlagRecord } from "@/lib/types";

const JUDGMENTS = [["unknown", "Not assessed / unsure"], ["acceptable", "Suitable for this exercise"], ["not_acceptable", "Not suitable"]] as const;
const FIELDS = [
  ["subtype", "Clinician-assessed location", [["unknown", "Not sure"], ["lateral", "Outside of elbow"], ["medial", "Inside of elbow"], ["posterior", "Back of elbow"]]],
  ["course", "Clinician-described presentation", [["unknown", "Not sure"], ["subacute", "Subacute"], ["chronic", "Chronic"], ["acute_traumatic", "Acute / traumatic"]]],
  ["safety_screen", "Other injury concerns or restrictions", [["unknown", "Not assessed / unsure"], ["clear", "Clinician excluded concerns for this exercise"], ["concern", "A concern or restriction remains"]]],
  ["pain_irritability", "Pain and irritability", JUDGMENTS],
  ["elbow_wrist_motion", "Elbow and wrist movement", JUDGMENTS],
  ["grip_function", "Grip during an everyday task", JUDGMENTS],
  ["wrist_extension_tolerance", "Supported wrist extension with an empty hand", JUDGMENTS],
  ["option_recommended", "Clinician recommended this exact starter", [["unknown", "Not sure"], ["yes", "Yes"], ["no", "No"]]],
] as const;

/** Occasional clinician-assessment report, never another daily check-in. */
export function LateralElbowAssessmentForm({ injury, token, onRefresh }: {
  injury: InjuryFlagRecord; token: string; onRefresh: () => Promise<void>;
}) {
  const id = useId();
  const pending = useRef<{ fingerprint: string; id: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  if (!injury.episode_id || !["left", "right"].includes(injury.side ?? "")) return null;

  async function save(form: HTMLFormElement) {
    setBusy(true); setError(""); setMessage("");
    try {
      const data = new FormData(form);
      const assessed = new Date(String(data.get("assessed_at")));
      if (Number.isNaN(assessed.getTime())) throw new Error("Enter when your clinician assessed this elbow.");
      if (assessed.getTime() > Date.now() || assessed.getTime() < new Date(injury.created_at).getTime())
        throw new Error("Use an assessment time within this injury episode, up to now.");
      const payload = Object.fromEntries(FIELDS.map(([name]) => [name, String(data.get(name) ?? "unknown")])) as LateralElbowProgressionInput;
      payload.option_recommended = data.get("option_recommended") === "unknown" ? null : data.get("option_recommended") === "yes";
      payload.grip_task = payload.grip_function === "unknown" ? "unknown" : "daily_grip_task";
      payload.wrist_extension_task = payload.wrist_extension_tolerance === "unknown" ? "unknown" : "supported_hand_weight";
      const assessment: LateralElbowProgressionAssessment = {
        assessment_kind: "lateral_elbow_progression_v1", protocol_version: 1, schema_version: 1,
        side: injury.side!, assessed_at: assessed.toISOString(), assessor: "clinician_physio", payload,
      };
      const fingerprint = JSON.stringify([injury.id, injury.episode_id, assessment]);
      if (pending.current?.fingerprint !== fingerprint) pending.current = { fingerprint, id: crypto.randomUUID() };
      await submitInjuryEpisodeObservation(token, { injury_id: injury.id, injury_episode_id: injury.episode_id!,
        event_type: "rehab_progression_assessment", report_id: pending.current.id, assessment });
      setMessage("Assessment report saved. Progression requirements updated.");
      await onRefresh(); pending.current = null;
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save assessment."); }
    finally { setBusy(false); }
  }

  return <details className="injury-guidance-sources injury-elbow-assessment">
    <summary>Report clinician rehab assessment</summary>
    <form onSubmit={e => { e.preventDefault(); void save(e.currentTarget); }}>
      <div className="injury-sheet-body">
        <p>Report what your clinician or physio assessed, only when it changes. Leave anything they did not assess as unsure.</p>
        <p className="injury-sheet-note">Starter: supported wrist extension, empty hand, 10 slow repetitions, maximum once daily. This is self-reported, not independently verified.</p>
        <fieldset disabled={busy} className="injury-elbow-fields">
          <label className="field" htmlFor={`${id}-time`}><span>When was the assessment?</span>
            <input id={`${id}-time`} name="assessed_at" type="datetime-local" required /></label>
          {FIELDS.map(([name, label, choices]) => <label className="field" key={name} htmlFor={`${id}-${name}`}>
            <span>{label}</span><select id={`${id}-${name}`} name={name} defaultValue="unknown">
              {choices.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </label>)}
        </fieldset>
        {message ? <p role="status">{message}</p> : null}
        {error ? <p role="alert">{error}</p> : null}
        <button className="injury-sheet-save" type="submit" disabled={busy}>{busy ? "Saving…" : "Save assessment report"}</button>
      </div>
    </form>
  </details>;
}
