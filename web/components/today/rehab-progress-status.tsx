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
  ankle_uncomplicated_lateral_not_reported: "This starter is for a clinician-described uncomplicated outer ankle sprain. Update the sprain type in Edit injury if you know it; otherwise follow today's guidance.",
  ankle_conflicting_or_unsupported_presentation: "Your ankle details include another sprain type, instability or a concern needing assessment. Loading stays on hold.",
  ankle_loading_severity_not_supported: "This starter is only available for a mild uncomplicated sprain. Follow today's conservative guidance.",
  assessment_observation_missing: "LOAD is on hold: your current records do not establish whether this elbow starter is suitable. Clearance and completed rehab cannot confirm grip, movement and tolerance for this exercise. Continue today's guidance.",
  elbow_function_assessment_incomplete: "LOAD is on hold: your current records do not establish whether this elbow starter is suitable. Clearance and completed rehab cannot confirm grip, movement and tolerance for this exercise. Continue today's guidance.",
  elbow_lateral_applicability_not_confirmed: "Confirm the elbow location in Edit injury. This starter is for outside-of-elbow tendon problems only.",
  elbow_function_or_safety_not_acceptable: "Your reported elbow function or symptoms do not support this starter yet.",
  elbow_later_unsatisfactory_function: "A later assessment reported unsuitable elbow function. An older assessment cannot replace it.",
  elbow_hand_weight_option_not_recommended: "Your clinician has not recommended this exact starter.",
  elbow_conflicting_or_unsupported_presentation: "Your injury details include a different elbow presentation or another concern.",
  elbow_loading_severity_not_supported: "Your current injury severity does not support this starter. Follow today's conservative guidance.",
  assessment_observation_stale_or_future: "Existing suitability evidence is not current for this injury episode. Loading stays on hold; continue today's guidance.",
  assessment_history_incomplete: "Assessment history is unavailable. Loading stays on hold.",
  assessment_medical_or_setback_hold: "A worsening response or medical concern is holding progression.",
  rehabilitation_loading_not_reported: "Confirm what rehabilitation loading your clinician has permitted in Clearance & restrictions.",
  achilles_midportion_not_confirmed: "Confirm the Achilles location in your injury details. This exercise is for midportion problems only.",
  injury_loading_safety_hold: "Your current injury restrictions take priority over loading permission.",
  current_report_worse: "Your latest injury response was worse. Follow the current conservative guidance.",
  unresolved_historical_negative_response: "A previous worsening response is still holding progression.",
  unresolved_injury_checkin_setback: "A recent injury worsening report is still holding loading. Continue your current rehab and follow clinician advice.",
  incomplete_prior_rehab_evidence: "Your previous rehab record is incomplete. Loading stays on hold while its evidence is unresolved.",
  prior_stage_work_not_required_for_reported_permission: "Prior rehab logs are not required when reported clinician permission supports this stage.",
  prior_restore_not_required_for_reported_permission: "Prior RESTORE logs are not required for this starter when you report clinician loading permission.",
  no_prior_rehab_response_to_resolve: "You have no previous rehab response to resolve. No favourable response has been assumed.",
  history_truncated: "Your full rehab history is unavailable. Progression stays on hold.",
  reviewed_target_content_unavailable: "No approved next-stage exercise matches your current injury and equipment.",
  target_equipment_unavailable: "The approved exercise needs equipment you have not reported. Update your equipment access if you have that setup; otherwise continue your current rehab.",
  target_adverse_response_unresolved: "A worsening response to the approved loading exercise is still holding it. Continue your current rehab and follow clinician advice.",
  target_stage_not_activated: "The next stage is not available in Unlxck yet.",
  no_clinical_criteria_declared: "This progression has not been activated in Unlxck.",
  transition_closed_by_profile: "This stage is not available for this injury profile.",
  no_reviewed_stage_exposure: "Complete your current rehabilitation exercise in Today.",
  no_defined_dose_completed: "No completed current-stage prescription is recorded yet.",
  no_reviewed_response_group: "An injury response after current-stage rehab is still needed.",
  during_response_not_reported: "Log your rehab session and answer its injury-response question.",
  next_day_response_not_reported: "Answer the next-day rehab follow-up when it appears in Today.",
  next_day_response_not_yet_known: "Waiting for your next-day rehab response. Use the injury response in Today after yesterday's rehab, before starting today's work.",
  next_day_response_not_sure: "Your next-day response is uncertain. Continue the current permitted rehab; this response cannot support loading yet.",
  during_response_not_sure: "Your response after rehab is uncertain. Continue the current permitted rehab.",
  inconsistent_response_group: "The responses for your last rehab session are incomplete or disagree. Loading stays on hold until its next-day responses are saved.",
  fail_stopped_due_to_symptoms: "Stopped rehab or worsening symptoms are still holding loading. Follow your current injury guidance.",
  fail_during_response_worse: "Your injury felt worse after rehab. Follow the current conservative guidance.",
  fail_next_day_response_worse: "Your injury felt worse the next day. Follow the current conservative guidance.",
  fail_worsening_reported: "A recent worsening response is still holding loading. Follow your current injury guidance.",
  shoulder_nontraumatic_cuff_not_reported: "Confirm what your clinician described in Edit injury. This starter is for non-traumatic rotator cuff tendinopathy without a tear.",
  shoulder_conflicting_or_unsupported_presentation: "Your shoulder details include another presentation or a concern needing assessment. Follow your current restrictions.",
  shoulder_loading_severity_not_supported: "Your current injury severity does not support this shoulder starter.",
  during_response_worse: "Your injury felt worse after rehab. Follow the current conservative guidance.",
  next_day_response_worse: "Your injury felt worse the next day. Follow the current conservative guidance.",
};

type RehabDecision = NonNullable<InjuryFlagRecord["rehab_decision"]>;

/** Presentation only. Availability and eligibility always come from the engine. */
export function rehabNextStep(decision: RehabDecision): string | null {
  const next = decision.progression?.next_transition;
  if (!next) return null;
  const codes = [...next.reason_codes, ...(next.requirements ?? [])
    .filter(item => !["pass", "not_applicable"].includes(item.status)).map(item => item.reason_code)];
  const safety = codes.find(code => /worse|worsening|setback|negative|safety_hold|stopped|medical/.test(code) && REASONS[code]);
  // Never present logging/permission requirements as a way to publish content.
  if (!next.target_stage_live) {
    const unavailable = `${(LABELS[next.to_stage] ?? "Next-stage").toUpperCase()} exercises aren’t available for this injury in UNLXCK yet.`;
    return safety ? `Progression is on hold. ${REASONS[safety]} ${unavailable}` : unavailable;
  }
  if (safety) return `Progression is on hold. ${REASONS[safety]}`;
  if (next.status === "closed") return "Progression is on hold for this injury. Follow your current restrictions and today’s permitted rehab.";
  if (next.status === "met") return "Follow the permitted exercise shown in Today.";
  // Specific selector blockers take precedence over its general content message.
  const reason = ["target_equipment_unavailable", "rehabilitation_loading_not_reported"]
    .find(code => codes.includes(code)) ?? codes.find(code => REASONS[code]);
  return reason ? REASONS[reason] : "Continue today’s permitted rehab. The next stage is on hold while its requirements remain unconfirmed.";
}

/** Availability and one next action stay visible; the row opens detailed checks. */
export function RehabProgressStatus({ decision, statusLine }: {
  decision: RehabDecision;
  statusLine?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const stage = decision.stage;
  if (!stage || !STAGES.includes(stage)) return null;
  const next = decision.progression?.next_transition;
  const unavailable = next && (!next.target_stage_live || next.status === "closed");
  const title = next ? `${LABELS[next.to_stage] ?? "Next stage"} · ${!next.target_stage_live ? "Unavailable in UNLXCK" : next.status === "met" ? "Available" : "On hold"}` : null;
  const nextStep = rehabNextStep(decision);
  if (!title && !statusLine) return null;
  const content = <>
    <span className="injury-progress-main">
      {title ? <span className="injury-progress-title">{title}</span> : null}
      {nextStep ? <span className="injury-progress-status">{nextStep}</span> : null}
      {decision.progression?.entry_basis === "reported_clinician_permission"
        ? <span className="injury-progress-status">Permitted rehab based on clinician advice you reported.</span> : null}
      {statusLine ? <span className="injury-progress-status injury-progress-schedule">{statusLine}</span> : null}
    </span>
    {next ? <InjuryChevron /> : null}
  </>;
  return <>
    {next ? <button type="button" className="injury-progress" aria-haspopup="dialog"
      aria-label={`${title}${nextStep ? `. ${nextStep}` : ""}${statusLine ? `. ${statusLine}` : ""}. Progression requirements`}
      onClick={() => setOpen(true)}>{content}</button>
      : <div className="injury-progress">{content}</div>}
    {open && next ? <InjuryDetailSheet title="Progression requirements" onClose={() => setOpen(false)}>
      <div className="injury-sheet-body">
        <p className="injury-sheet-lead">{LABELS[stage]} → {LABELS[next.to_stage] ?? "Next stage"}</p>
        <p className="muted">{unavailable ? nextStep
          : "These checks keep your rehab within your reported permissions and current injury response."}</p>
        {!unavailable ? <ul className="injury-requirements">{(next.requirements ?? []).filter((item, index, items) =>
          item.status === "pass" || !REASONS[item.reason_code] || !items.slice(0, index).some(previous =>
            previous.status !== "pass" && REASONS[previous.reason_code] === REASONS[item.reason_code])
        ).map(item => <li key={item.requirement_id}>
          <div><strong>{REQUIREMENTS[item.kind] ?? "Progression check"}</strong>
            <span>{item.status === "pass" ? "Complete" : item.status === "not_applicable" ? "Not required for this entry" : item.status === "fail" ? "On hold" : "Not yet confirmed"}</span></div>
          {item.status !== "pass" ? <p>{REASONS[item.reason_code] ?? "This check is not yet satisfied. Continue the current injury guidance."}</p> : null}
        </li>)}</ul> : null}
        {!unavailable ? (next.reason_codes ?? []).filter(code => !(next.requirements ?? []).some(item => item.reason_code === code)).map(code =>
          <p key={code}>{REASONS[code] ?? "Progression remains on hold. Continue your current permitted work."}</p>) : null}
      </div>
    </InjuryDetailSheet> : null}
  </>;
}

/** The stage at a glance for an injury's summary row: "Restore", the
 * five-step meter, and where it goes next. Null when there is no stage. */
export function RehabStageMeter({ decision }: { decision: InjuryFlagRecord["rehab_decision"] }) {
  const stage = decision?.stage;
  if (!decision || !stage || !STAGES.includes(stage)) return null;
  const current = STAGES.indexOf(stage);
  const next = decision.progression?.next_transition;
  return <span className="injury-stage-meter">
    <span className="injury-stage-meter-steps" aria-hidden="true">
      {STAGES.map((value, index) => <span key={value} data-complete={index <= current}
        data-current={index === current || undefined} />)}
    </span>
    <span className="injury-stage-meter-text">
      <span className="sr-only">Current rehab stage: {LABELS[stage]}. CALM → RESTORE → LOAD → DYNAMIC → RETURN. Future stages depend on published exercises and eligibility. </span>
      {next ? rehabNextStep(decision) : `Stage ${current + 1} of ${STAGES.length} · Future availability varies by injury`}
    </span>
  </span>;
}

export function rehabStageLabel(decision: InjuryFlagRecord["rehab_decision"]): string | null {
  const stage = decision?.stage;
  return stage && STAGES.includes(stage) ? LABELS[stage] : null;
}
