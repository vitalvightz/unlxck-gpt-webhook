"use client";

import { useState } from "react";
import type { InjuryFlagRecord } from "@/lib/types";
import { InjuryChevron, InjuryDetailSheet } from "./injury-detail-sheet";

const STAGES = ["calm", "restore", "load", "dynamic", "return"] as const;
const LABELS: Record<string, string> = { calm: "Calm", restore: "Restore", load: "Load", dynamic: "Dynamic", return: "Return" };
const REQUIREMENTS: Record<string, string> = {
  no_unresolved_setback: "Injury response", complete_history: "Complete rehab history",
  completed_reviewed_exposure: "Current-stage rehab", during_session_response: "Response after rehab",
  next_day_response: "Next-day response", functional_checkpoint: "Permission and exercise suitability",
};
const REASONS: Record<string, string> = {
  rehabilitation_loading_not_reported: "Report what your clinician has permitted in Clearance & restrictions.",
  achilles_midportion_not_confirmed: "Confirm the Achilles location in your injury details. This exercise is for midportion problems only.",
  injury_loading_safety_hold: "Your current injury restrictions take priority over loading permission.",
  current_report_worse: "Your latest injury response was worse. Follow the current conservative guidance.",
  unresolved_historical_negative_response: "A previous worsening response is still holding progression.",
  history_truncated: "Your full rehab history is unavailable. Progression stays on hold.",
  reviewed_target_content_unavailable: "No suitable reviewed exercise is available for the next stage.",
  target_stage_not_activated: "The next stage is not available in Unlxck yet.",
  no_clinical_criteria_declared: "This progression has not been activated in Unlxck.",
  transition_closed_by_profile: "This stage is not available for this injury profile.",
  no_reviewed_stage_exposure: "Record completion of your current-stage rehab first.",
  no_defined_dose_completed: "No completed current-stage prescription is recorded yet.",
  no_reviewed_response_group: "An injury response after current-stage rehab is still needed.",
  during_response_not_reported: "Log your rehab session and answer its injury-response question.",
  next_day_response_not_reported: "Answer the next-day rehab follow-up when it appears in Today.",
  during_response_worse: "Your injury felt worse after rehab. Follow the current conservative guidance.",
  next_day_response_worse: "Your injury felt worse the next day. Follow the current conservative guidance.",
};

export function RehabProgressStatus({ decision }: { decision: NonNullable<InjuryFlagRecord["rehab_decision"]> }) {
  const [open, setOpen] = useState(false);
  const stage = decision.stage;
  if (!stage || !STAGES.includes(stage)) return null;
  const current = STAGES.indexOf(stage);
  const next = decision.progression?.next_transition;
  const unavailable = next && (!next.target_stage_live || next.status === "closed");
  return <>
    <div className="injury-progress">
      <div><p className="injury-progress-label">Rehab stage</p><strong>{LABELS[stage]}</strong></div>
      <div className="injury-progress-next">
        {next ? <span>Next: {LABELS[next.to_stage] ?? "Not available"}{unavailable ? " · Closed" : ""}</span> : null}
        <ol aria-label="Rehabilitation stages">{STAGES.map((value, index) =>
          <li key={value} aria-current={value === stage ? "step" : undefined} data-complete={index <= current}>
            <span className="sr-only">{LABELS[value]}{value === stage ? ", current stage" : ""}</span>
          </li>)}</ol>
      </div>
    </div>
    {next ? <button type="button" className="injury-detail-link injury-progress-link" onClick={() => setOpen(true)}
      aria-haspopup="dialog">Progression requirements<InjuryChevron /></button> : null}
    {open && next ? <InjuryDetailSheet title="Progression requirements" onClose={() => setOpen(false)}>
      <div className="injury-sheet-body">
        <p className="injury-sheet-lead">{LABELS[stage]} → {LABELS[next.to_stage] ?? "Next stage"}</p>
        <p className="muted">{unavailable ? "This next stage is closed. Reported permission does not open it."
          : "Your rehab engine checks these before changing your stage."}</p>
        {!unavailable ? <ul className="injury-requirements">{(next.requirements ?? []).map(item => <li key={item.requirement_id}>
          <div><strong>{REQUIREMENTS[item.kind] ?? "Progression check"}</strong>
            <span>{item.status === "pass" ? "Complete" : item.status === "fail" ? "On hold" : "Not yet confirmed"}</span></div>
          {item.status !== "pass" ? <p>{REASONS[item.reason_code] ?? "This check is not yet satisfied. Continue the current injury guidance."}</p> : null}
        </li>)}</ul> : null}
        {(next.reason_codes ?? []).filter(code => !(next.requirements ?? []).some(item => item.reason_code === code)).map(code =>
          <p key={code}>{REASONS[code] ?? "Progression remains on hold. Continue your current permitted work."}</p>)}
      </div>
    </InjuryDetailSheet> : null}
  </>;
}

/** The stage at a glance for an injury's summary row: "Restore", the
 * five-step meter, and where it goes next. Null when there is no stage. */
export function RehabStageMeter({ decision }: { decision: InjuryFlagRecord["rehab_decision"] }) {
  const stage = decision?.stage;
  if (!stage || !STAGES.includes(stage)) return null;
  const current = STAGES.indexOf(stage);
  const next = decision.progression?.next_transition;
  const unavailable = next && (!next.target_stage_live || next.status === "closed");
  return <span className="injury-stage-meter">
    <span className="injury-stage-meter-steps" aria-hidden="true">
      {STAGES.map((value, index) => <span key={value} data-complete={index <= current} />)}
    </span>
    <span className="injury-stage-meter-text">
      <span className="sr-only">Rehab stage {current + 1} of {STAGES.length}. </span>
      {next ? <>Next: {LABELS[next.to_stage] ?? "Not available"}{unavailable ? " · Closed" : ""}</> : `Stage ${current + 1} of ${STAGES.length}`}
    </span>
  </span>;
}

export function rehabStageLabel(decision: InjuryFlagRecord["rehab_decision"]): string | null {
  const stage = decision?.stage;
  return stage && STAGES.includes(stage) ? LABELS[stage] : null;
}
